"""Klaim penggantian beban cabang: daftar, buat, detail, aksi, CSV, PDF.

Pusat tidak memakai HMS (jawaban user 2026-10-19): Finance cabang membuat dan
mengajukan klaim, lalu mencatat penolakan Pusat atau menandainya lunas saat
rupiah penggantiannya masuk. Logika di hw/finance/claim_service.py; view hanya
membaca request dan menerjemahkan FinanceError menjadi pesan.
"""

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, operating_branches, scope
from ..finance import claim_service as svc
from ..finance.errors import FinanceError
from ..i18n import tr
from ..models.expense import Expense, ExpenseClaim
from ..models.journal import JournalEntry
from ..permissions import require_perm
from .helpers import (
    _parse_date,
    csv_export_response,
    money_account_choices,
    pagination_props,
    request_data,
    resolve_money_account,
    serialize_journal_entry,
    validate_proof_file,
)


def _visible(request):
    return scope(ExpenseClaim.objects.all(), request.user)


def _expense_row(e):
    lines = list(e.lines.all())
    return {
        'id': e.pk, 'expense_number': e.expense_number,
        'expense_date': e.expense_date.isoformat(),
        'description': e.description or ', '.join(sorted({l.category.name for l in lines})),
        'categories': sorted({l.category.name for l in lines}),
        'amount': sum(l.amount for l in lines), 'amount_sar': sum(l.amount_sar for l in lines),
    }


def _claim_props(c, items=False):
    out = {
        'id': c.pk, 'claim_number': c.claim_number,
        'branch': c.branch_id, 'branch_name': c.branch.name,
        'date_from': c.date_from.isoformat(), 'date_to': c.date_to.isoformat(),
        'status': c.status, 'status_display': c.get_status_display(),
        'total_amount': c.total_amount, 'total_sar': c.total_sar,
        'received_amount': c.received_amount, 'remaining': c.remaining, 'borne_amount': c.borne_amount,
        'received_sar': c.received_sar,
        'credit_used': sum(p.amount for p in c.payments.all() if p.kind == p.KIND_CREDIT and not p.voided_at),
        'paid_by_credit': c.status == c.STATUS_PAID and not c.borne_amount and not any(
            p.kind == p.KIND_TRANSFER and not p.voided_at for p in c.payments.all()),
        'note': c.note, 'decision_note': c.decision_note,
        'paid_date': c.paid_date.isoformat() if c.paid_date else None,
        'paid_to': str(c.paid_to) if c.paid_to_id else None,
        'reference': c.reference,
        'proof_url': c.proof.url if c.proof else None,
        'created_by': c.created_by.get_full_name() or c.created_by.username,
        'created_at': c.created_at.isoformat(),
        'decided_by': (c.decided_by.get_full_name() or c.decided_by.username) if c.decided_by_id else None,
        'item_count': getattr(c, 'n_items', None),
    }
    if items:
        out['items'] = [_expense_row(i.expense) for i in c.items.filter(is_active=True)
                        .select_related('expense').prefetch_related('expense__lines__category')]
        out['item_count'] = len(out['items'])
        out['payments'] = [{
            'id': p.pk, 'kind': p.kind, 'date': p.payment_date.isoformat(), 'account': str(p.account) if p.account_id else None,
            'amount': p.amount, 'excess_amount': p.excess_amount, 'excess_kept': p.excess_kept,
            'reference': p.reference, 'proof_url': p.proof.url if p.proof else None,
        } for p in c.payments.filter(voided_at__isnull=True).select_related('account')]
    return out


@require_perm('expenses', 'view')
def claim_list(request):
    from django.db.models import Count, Q

    from .helpers import list_per_page
    status = request.GET.get('status', '')
    qs = _visible(request).select_related('branch', 'created_by', 'decided_by', 'paid_to').annotate(
        n_items=Count('items', filter=Q(items__is_active=True)),
    ).prefetch_related('payments').order_by('-created_at', '-id')  # Meta.ordering is dropped by the GROUP BY
    counts = {s: qs.filter(status=s).count() for s, _ in ExpenseClaim.STATUS_CHOICES}
    if status:
        qs = qs.filter(status=status)
    page_obj = Paginator(qs, list_per_page(request)).get_page(request.GET.get('page'))
    branches = list(operating_branches(request.user))
    kpis = {'paid': 0, 'claimed': 0, 'unclaimed': 0, 'borne': 0, 'credit': 0}
    for b in branches:
        for k, v in svc.reimbursement_summary(b).items():
            kpis[k] += v
        kpis['credit'] += svc.head_office_credit(b.pk)
    return inertia_render(request, 'Finance/Claims', props={
        'claims': [_claim_props(c) for c in page_obj],
        'kpis': kpis, 'counts': counts,
        'filters': {'status': status, 'per': list_per_page(request)},
        'pagination': pagination_props(page_obj),
    })


def _ids(data, key):
    """Ids from a form (repeated field) or from Inertia's JSON (a list)."""
    raw = data.getlist(key) if hasattr(data, 'getlist') else (data.get(key) or [])
    return {int(x) for x in raw if str(x).isdigit()}


def _range(request, data):
    today = timezone.localdate()
    return (_parse_date(data.get('date_from')) or today.replace(day=1),
            _parse_date(data.get('date_to')) or today)


@require_perm('expenses', 'create')
def claim_new(request):
    """GET: pratinjau beban yang bisa diklaim untuk rentang ini. POST: buat
    klaim draft, tanpa beban yang dicentang keluar (`exclude`)."""
    branches = list(operating_branches(request.user))
    data = request_data(request) if request.method == 'POST' else request.GET
    branch = next((b for b in branches if b.pk == data.get('branch')), branches[0] if len(branches) == 1 else None)
    date_from, date_to = _range(request, data)
    all_time = request.method == 'GET' and data.get('span') == 'all'
    if all_time and branch is not None:
        date_from, date_to = svc.claimable_start(branch) or date_from, timezone.localdate()
    if request.method == 'POST':
        if branch is None:
            messages.error(request, tr(request, 'Choose the claiming branch.', 'Pilih cabang klaim.'))
            return redirect('claim_new')
        try:
            claim = svc.create_claim(
                branch=branch, date_from=date_from, date_to=date_to, created_by=request.user,
                exclude_ids=_ids(data, 'exclude'),
                note=(data.get('note') or '').strip(),
            )
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect(f"{request.path}?date_from={date_from}&date_to={date_to}&branch={branch.pk}")
        messages.success(request, tr(request, f'Claim {claim.claim_number} saved as a draft.', f'Klaim {claim.claim_number} dibuat sebagai draft.'))
        return redirect('claim_detail', pk=claim.pk)
    expenses = []
    if branch is not None:
        expenses = [_expense_row(e) for e in svc.claimable_expenses(branch, date_from, date_to)
                    .prefetch_related('lines__category')]
    return inertia_render(request, 'Finance/ClaimForm', props={
        'expenses': expenses,
        'total_amount': sum(e['amount'] for e in expenses),
        'filters': {'date_from': date_from.isoformat(), 'date_to': date_to.isoformat(),
                    'branch': branch.pk if branch else '', 'span': 'all' if all_time else ''},
        'branch_choices': [{'value': b.pk, 'label': b.name} for b in branches],
    })


@require_perm('expenses', 'view')
def claim_detail(request, pk):
    claim = get_in_scope_or_404(
        ExpenseClaim.objects.select_related('branch', 'created_by', 'decided_by', 'paid_to'), request.user, pk=pk,
    )
    entries = JournalEntry.objects.for_source('ExpenseClaim', claim.pk).order_by('-entry_date')
    return inertia_render(request, 'Finance/ClaimDetail', props={
        'claim': _claim_props(claim, items=True),
        'head_office_credit': svc.head_office_credit(claim.branch_id),
        'account_choices': [a for a in money_account_choices(branch=claim.branch_id)
                            if a['currency'] == Expense.CURRENCY and a['kind'] != 'staff'],
        'journal_entries': [serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit)
                            for e in entries],
    })


def _amount(raw):
    """Rupiah from the form, digits only; empty means the whole remainder."""
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    return int(digits) if digits else None


def _act(request, pk, action):
    claim = get_in_scope_or_404(ExpenseClaim.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('claim_detail', pk=pk)
    data = request_data(request)
    reason = (data.get('reason') or '').strip()
    try:
        if action == 'submit':
            svc.submit_claim(claim, by=request.user)
            messages.success(request, tr(request, f'{claim.claim_number} submitted to HQ.', f'{claim.claim_number} diajukan ke Pusat.'))
        elif action == 'cancel':
            svc.cancel_claim(claim, by=request.user, note=reason)
            messages.success(request, tr(request, f'{claim.claim_number} cancelled.', f'{claim.claim_number} dibatalkan.'))
        elif action == 'reject':
            svc.reject_claim(claim, by=request.user, note=reason)
            messages.success(request, tr(request, f'Rejection of {claim.claim_number} recorded.', f'Penolakan {claim.claim_number} dicatat.'))
        elif action == 'pay':
            proof = request.FILES.get('proof')
            error = validate_proof_file(proof) if proof else None
            if error:
                raise FinanceError(error)
            svc.mark_paid(
                claim, account=resolve_money_account(data.get('account')),
                paid_date=_parse_date(data.get('paid_date')) or timezone.localdate(), by=request.user,
                reference=(data.get('reference') or '').strip(), proof=proof,
                amount=_amount(data.get('amount')), remainder=data.get('remainder') or None,
                excess_use=data.get('excess_use') or None,
            )
            claim.refresh_from_db()
            latest = claim.payments.filter(voided_at__isnull=True).order_by('-pk').first()
            excess = latest.excess_amount
            if excess and latest.excess_kept:
                messages.success(request, tr(request, f'{claim.claim_number} paid; {excess:,} IDR extra kept as branch funds.', f'{claim.claim_number} lunas; kelebihan {excess:,} IDR menjadi dana tambahan cabang.'))
            elif excess:
                messages.success(request, tr(request, f'{claim.claim_number} paid; {excess:,} IDR extra kept as head office credit.', f'{claim.claim_number} lunas; kelebihan {excess:,} IDR menjadi titipan Pusat.'))
            elif claim.status == ExpenseClaim.STATUS_PARTIAL:
                messages.success(request, tr(request, f'{claim.claim_number}: reimbursement recorded, {claim.remaining:,} IDR still waiting.', f'{claim.claim_number}: penggantian dicatat, {claim.remaining:,} IDR masih menunggu.'))
            else:
                messages.success(request, tr(request, f'{claim.claim_number} paid: reimbursement from HQ recorded.', f'{claim.claim_number} lunas: penggantian dari Pusat dicatat.'))
        elif action == 'close':
            svc.close_remainder(claim, by=request.user, closed_date=timezone.localdate(), note=reason)
            messages.success(request, tr(request, f'{claim.claim_number} closed: the rest is borne by the branch.', f'{claim.claim_number} ditutup: sisanya ditanggung cabang.'))
        elif action == 'unpay':
            if not reason:
                raise FinanceError('Tulis alasan membatalkan pencatatan lunas.')
            svc.unpay_claim(claim, by=request.user, reason=reason)
            messages.success(request, tr(request, f'Payment of {claim.claim_number} undone.', f'Pencatatan lunas {claim.claim_number} dibatalkan.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('claim_detail', pk=pk)


@require_perm('expenses', 'create')
def claim_submit(request, pk):
    return _act(request, pk, 'submit')


@require_perm('expenses', 'create')
def claim_cancel(request, pk):
    return _act(request, pk, 'cancel')


@require_perm('expenses', 'approve')
def claim_reject(request, pk):
    return _act(request, pk, 'reject')


# Booking the rupiah into an account is money work: Finance's `bank` module,
# not the expense approver (a Manager approves expenses but moves no money).
@require_perm('bank', 'edit')
def claim_pay(request, pk):
    return _act(request, pk, 'pay')


@require_perm('bank', 'edit')
def claim_close(request, pk):
    return _act(request, pk, 'close')


@require_perm('bank', 'edit')
def claim_unpay(request, pk):
    return _act(request, pk, 'unpay')


def _items(claim):
    return [_expense_row(i.expense) for i in claim.items.filter(is_active=True)
            .select_related('expense').prefetch_related('expense__lines__category')]


@require_perm('expenses', 'export')
def claim_export_csv(request, pk):
    claim = get_in_scope_or_404(ExpenseClaim.objects.all(), request.user, pk=pk)
    headers = ['Expense #', 'Date', 'Category', 'Description', 'Amount IDR', 'Booked SAR']
    rows = ([r['expense_number'], r['expense_date'], ', '.join(r['categories']), r['description'],
             r['amount'], r['amount_sar']] for r in _items(claim))
    return csv_export_response(f'{claim.claim_number}.csv', headers, rows)


@require_perm('expenses', 'view')
def claim_pdf(request, pk):
    """Lampiran pengajuan ke Pusat: daftar beban dan totalnya."""
    from weasyprint import HTML

    from .pdf import _logo_file_url
    claim = get_in_scope_or_404(ExpenseClaim.objects.select_related('branch', 'created_by'), request.user, pk=pk)
    html = render_to_string('hw/claim/claim_pdf.html', {
        'claim': claim, 'items': _items(claim), 'logo_rel_path': _logo_file_url(),
        'credit_used': claim.payments.filter(kind='credit', voided_at__isnull=True).aggregate(t=Sum('amount'))['t'] or 0,
        'prepared_by': claim.created_by.get_full_name() or claim.created_by.username,
        'printed_at_ts': timezone.localtime(timezone.now()),
    })
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{claim.claim_number}.pdf"'
    return response
