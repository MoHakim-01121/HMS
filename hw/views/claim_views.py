"""Klaim penggantian beban cabang: daftar, buat, detail, aksi, CSV, PDF.

Pusat tidak memakai HMS (jawaban user 2026-10-19): Finance cabang membuat dan
mengajukan klaim, lalu mencatat penolakan Pusat atau menandainya lunas saat
rupiah penggantiannya masuk. Logika di hw/finance/claim_service.py; view hanya
membaca request dan menerjemahkan FinanceError menjadi pesan.
"""
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone

from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, operating_branches, scope
from ..finance import claim_service as svc
from ..finance.errors import FinanceError
from ..models.expense import Expense, ExpenseClaim
from ..models.journal import JournalEntry
from ..permissions import require_perm
from .helpers import (
    _parse_date, csv_export_response, money_account_choices, pagination_props, request_data, resolve_money_account,
    serialize_journal_entry, validate_proof_file,
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
    return out


@require_perm('expenses', 'view')
def claim_list(request):
    from django.db.models import Count, Q
    from .helpers import list_per_page
    status = request.GET.get('status', '')
    qs = _visible(request).select_related('branch', 'created_by', 'decided_by', 'paid_to').annotate(
        n_items=Count('items', filter=Q(items__is_active=True)),
    ).order_by('-created_at', '-id')  # Meta.ordering is dropped by the GROUP BY
    counts = {s: qs.filter(status=s).count() for s, _ in ExpenseClaim.STATUS_CHOICES}
    if status:
        qs = qs.filter(status=status)
    page_obj = Paginator(qs, list_per_page(request)).get_page(request.GET.get('page'))
    branches = list(operating_branches(request.user))
    kpis = {'paid': 0, 'claimed': 0, 'unclaimed': 0}
    for b in branches:
        for k, v in svc.reimbursement_summary(b).items():
            kpis[k] += v
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
    today = date.today()
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
    if request.method == 'POST':
        if branch is None:
            messages.error(request, 'Pilih cabang klaim.')
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
        messages.success(request, f'Klaim {claim.claim_number} dibuat sebagai draft.')
        return redirect('claim_detail', pk=claim.pk)
    expenses = []
    if branch is not None:
        expenses = [_expense_row(e) for e in svc.claimable_expenses(branch, date_from, date_to)
                    .prefetch_related('lines__category')]
    return inertia_render(request, 'Finance/ClaimForm', props={
        'expenses': expenses,
        'total_amount': sum(e['amount'] for e in expenses),
        'filters': {'date_from': date_from.isoformat(), 'date_to': date_to.isoformat(),
                    'branch': branch.pk if branch else ''},
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
        'account_choices': [a for a in money_account_choices(branch=claim.branch_id)
                            if a['currency'] == Expense.CURRENCY and a['kind'] != 'staff'],
        'journal_entries': [serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit)
                            for e in entries],
    })


def _act(request, pk, action):
    claim = get_in_scope_or_404(ExpenseClaim.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('claim_detail', pk=pk)
    data = request_data(request)
    reason = (data.get('reason') or '').strip()
    try:
        if action == 'submit':
            svc.submit_claim(claim, by=request.user)
            messages.success(request, f'{claim.claim_number} diajukan ke Pusat.')
        elif action == 'cancel':
            svc.cancel_claim(claim, by=request.user, note=reason)
            messages.success(request, f'{claim.claim_number} dibatalkan.')
        elif action == 'reject':
            svc.reject_claim(claim, by=request.user, note=reason)
            messages.success(request, f'Penolakan {claim.claim_number} dicatat.')
        elif action == 'pay':
            proof = request.FILES.get('proof')
            error = validate_proof_file(proof) if proof else None
            if error:
                raise FinanceError(error)
            svc.mark_paid(
                claim, account=resolve_money_account(data.get('account')),
                paid_date=_parse_date(data.get('paid_date')) or date.today(), by=request.user,
                reference=(data.get('reference') or '').strip(), proof=proof,
            )
            messages.success(request, f'{claim.claim_number} lunas: penggantian dari Pusat dicatat.')
        elif action == 'unpay':
            if not reason:
                raise FinanceError('Tulis alasan membatalkan pencatatan lunas.')
            svc.unpay_claim(claim, by=request.user, reason=reason)
            messages.success(request, f'Pencatatan lunas {claim.claim_number} dibatalkan.')
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
        'prepared_by': claim.created_by.get_full_name() or claim.created_by.username,
        'printed_at_ts': timezone.localtime(timezone.now()),
    })
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{claim.claim_number}.pdf"'
    return response
