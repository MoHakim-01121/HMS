"""Expense views: list, detail, submit, approve, reject, pay, void, categories.

The flow (decided 2026-10-11): Finance records an expense in rupiah; Finance,
a Manager or an Admin approves or rejects it; Finance pays it from one of the
branch's IDR accounts. See hw/finance/expense_service.py for the posting —
views only parse the request and translate FinanceError into a message.
"""
import json
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, head_office_only, operating_branches, scope
from ..finance import expense_service
from ..finance.errors import FinanceError
from ..i18n import tr
from ..models.expense import Expense, ExpenseCategory, ExpensePayment
from ..models.journal import JournalEntry
from ..models.vendor import Vendor
from ..permissions import require_perm
from .helpers import (
    _parse_date,
    _to_float,
    csv_export_response,
    money_account_choices,
    pagination_props,
    resolve_money_account,
    serialize_journal_entry,
    validate_proof_file,
)

# What _expense_props reads, fetched once for a page of expenses.
_PROPS_PREFETCH = ('lines__category', 'lines__receipts', 'payments__source_account')


def _expense_props(e):
    payment = e.payment
    return {
        'id': e.pk,
        'expense_number': e.expense_number,
        'branch': e.branch_id,
        'branch_name': e.branch.name if e.branch_id else None,
        'expense_date': e.expense_date.isoformat() if e.expense_date else None,
        'vendor': e.vendor.name if e.vendor_id else '',
        'description': e.description,
        'total_amount': e.total_amount,
        'total_amount_sar': e.total_amount_sar,
        'status': e.status,
        'status_display': e.get_status_display(),
        'note': e.note,
        'proof_url': e.proof.url if e.proof else None,
        'created_by': e.created_by.username if e.created_by_id else None,
        'created_at': e.created_at.isoformat(),
        'decided_by': e.decided_by.username if e.decided_by_id else None,
        'decided_at': e.decided_at.isoformat() if e.decided_at else None,
        'decision_note': e.decision_note,
        'spent_by': (e.spent_by.get_full_name() or e.spent_by.username) if e.spent_by_id else None,
        'paid_with': str(e.paid_with) if e.paid_with_id else None,
        'lines': [{
            'id': l.pk, 'category': l.category_id, 'category_name': l.category.name,
            'description': l.description, 'amount': l.amount, 'amount_sar': l.amount_sar,
            'no_receipt_reason': l.no_receipt_reason,
            'receipts': [{'name': r.name or r.file.name.rsplit('/', 1)[-1], 'url': r.file.url, 'size': r.size}
                         for r in l.receipts.all()],
        } for l in e.lines.all()],
        'payment': {
            'payment_date': payment.payment_date.isoformat(),
            'account_name': str(payment.source_account),
            'amount': payment.amount, 'amount_sar': payment.amount_sar,
            'reference': payment.reference,
        } if payment else None,
    }


def _staff_choices(branches):
    """Who may have spent an expense, per branch, with the rupiah advance
    they hold (token and balance) when they have one."""
    from ..finance.staff_advance import advance_account, balances, branch_holders, display_name
    rows = []
    for b in branches:
        for u in branch_holders(b.code):
            acc = advance_account(u, b.code, Expense.CURRENCY)
            rows.append({'value': str(u.pk), 'label': display_name(u), 'branch': b.code,
                         'advance': acc.token if acc else None,
                         'balance': balances([acc])[acc.pk] if acc else 0})
    return rows


def _visible(request):
    """Expenses of the branches the user covers."""
    return scope(Expense.objects.all(), request.user)


def _data(request):
    try:
        return json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        return request.POST


@require_perm('expenses', 'view')
def expense_list(request):
    """Expense list (Record View HMS canvas): spent in the month, awaiting
    approval and approved not paid (both filter the table), the toolbar and
    the table. The New Expense dialog is unchanged."""
    from .helpers import csv_list, list_per_page, list_period, pct_delta, prev_month_range
    GROUPS = {'submitted': [Expense.STATUS_SUBMITTED], 'approved': [Expense.STATUS_APPROVED],
              'paid': [Expense.STATUS_PAID], 'off': [Expense.STATUS_REJECTED, Expense.STATUS_VOIDED]}
    q = request.GET.get('q', '').strip()
    groups = csv_list(request, 'status', list(GROUPS))
    people = csv_list(request, 'by')
    sort = request.GET.get('sort', '-date')
    date_from, date_to, period = list_period(request)
    today = date.today()
    base = _visible(request).select_related('branch', 'created_by', 'vendor', 'decided_by').prefetch_related(*_PROPS_PREFETCH)
    qs = base
    if q:
        qs = qs.filter(Q(expense_number__icontains=q) | Q(description__icontains=q) | Q(note__icontains=q)
                       | Q(created_by__username__icontains=q) | Q(created_by__first_name__icontains=q)
                       | Q(vendor__name__icontains=q))
    # Waiting and approved-not-paid are not tied to a month.
    if not (groups and set(groups) <= {'submitted', 'approved'}):
        if date_from:
            qs = qs.filter(expense_date__gte=date_from)
        if date_to:
            qs = qs.filter(expense_date__lte=date_to)
    who = lambda e: (e.created_by.get_full_name() or e.created_by.username) if e.created_by_id else ''
    period_rows = list(qs.order_by('expense_date' if sort == 'date' else '-expense_date', '-created_at'))
    counts = {k: sum(1 for e in period_rows if e.status in v) for k, v in GROUPS.items()}
    by_n = {}
    for e in period_rows:
        by_n[who(e)] = by_n.get(who(e), 0) + 1
    rows = [e for e in period_rows
            if (not groups or any(e.status in GROUPS[g] for g in groups)) and (not people or who(e) in people)]
    page_obj = Paginator(rows, list_per_page(request)).get_page(request.GET.get('page'))

    kpis = None
    if period['month']:
        paid = lambda f, l: (scope(ExpensePayment.objects.filter(status=ExpensePayment.STATUS_PAID, payment_date__gte=f, payment_date__lte=l),
                                   request.user, 'expense__branch'))
        spent = paid(date_from, date_to).aggregate(t=Sum('amount'))['t'] or 0
        pf, pl = prev_month_range(date_from)
        prev = paid(pf, pl).aggregate(t=Sum('amount'))['t'] or 0
        by_cat = {}
        for e in base.filter(pk__in=paid(date_from, date_to).values('expense_id')):
            for l in e.lines.all():
                by_cat[l.category.name] = by_cat.get(l.category.name, 0) + int(l.amount)
        top = max(by_cat.items(), key=lambda x: x[1]) if by_cat else None
        waiting = list(base.filter(status=Expense.STATUS_SUBMITTED))
        approved = list(base.filter(status=Expense.STATUS_APPROVED))
        kpis = {
            'spent': spent, 'delta': pct_delta(spent, prev), 'prev_month': pf.strftime('%Y-%m'),
            'top_category': top[0] if top else None,
            'top_share': round(top[1] * 100 / sum(by_cat.values())) if top else None,
            'waiting_count': len(waiting), 'waiting_idr': sum(e.total_amount for e in waiting),
            'waiting_oldest': max(((today - e.created_at.date()).days for e in waiting), default=0),
            'approved_count': len(approved), 'approved_idr': sum(e.total_amount for e in approved),
            'approved_oldest': max(((today - e.decided_at.date()).days for e in approved if e.decided_at), default=0),
        }

    branches = list(operating_branches(request.user))
    years = sorted({d.year for d in _visible(request).dates('expense_date', 'year')} | {today.year})
    return inertia_render(request, 'Expense/List', props={
        'expenses': [{**_expense_props(e), 'recorded_by': who(e)} for e in page_obj],
        'filters': {'q': q, 'status': groups, 'by': people, 'sort': sort, 'per': list_per_page(request), **period},
        'years': years, 'counts': counts,
        'people_counts': [{'name': k, 'count': v} for k, v in sorted(by_n.items()) if k],
        'kpis': kpis,
        'branch_choices': [{'value': b.code, 'label': b.name} for b in branches],
        'staff_choices': _staff_choices(branches),
        'me': request.user.pk,
        'category_choices': [{'value': c.code, 'label': c.name} for c in ExpenseCategory.objects.filter(is_active=True)],
        'vendor_choices': [v.name for v in Vendor.objects.filter(is_active=True).order_by('name')],
        'pagination': pagination_props(page_obj),
    })


@require_perm('expenses', 'view')
def expense_detail(request, pk):
    expense = get_in_scope_or_404(
        Expense.objects.select_related('branch', 'created_by', 'vendor', 'decided_by').prefetch_related(*_PROPS_PREFETCH),
        request.user, pk=pk,
    )
    journal_entries = JournalEntry.objects.for_source(
        'ExpensePayment', list(expense.payments.values_list('pk', flat=True)),
    ).order_by('-entry_date')

    # Paid from one of the branch's rupiah accounts.
    accounts = [a for a in money_account_choices(branch=expense.branch_id) if a['currency'] == Expense.CURRENCY]
    return inertia_render(request, 'Expense/Detail', props={
        'expense': _expense_props(expense),
        'account_choices': accounts,
        'journal_entries': [
            serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit)
            for e in journal_entries
        ],
    })


@require_perm('expenses', 'create')
def expense_record(request):
    """Finance records an expense in rupiah; it waits for approval."""
    if request.method != 'POST':
        return redirect('expense_list')
    data = _data(request)

    branches = operating_branches(request.user)
    branch = branches.filter(pk=data.get('branch')).first() if data.get('branch') else None
    if branch is None and not data.get('branch') and branches.count() == 1:
        branch = branches.first()
    if branch is None:
        messages.error(request, tr(request, 'Choose the branch — expenses belong to a branch, not HQ.', 'Pilih cabang pengeluaran — pengeluaran milik cabang, bukan Pusat.'))
        return redirect('expense_list')

    proof = request.FILES.get('proof')
    if proof:
        error = validate_proof_file(proof)
        if error:
            messages.error(request, error)
            return redirect('expense_list')

    # Who spent it, and from where: a staff member's advance, or the office.
    from ..finance.staff_advance import branch_holders
    spent_by = None
    if data.get('spent_by'):
        spent_by = branch_holders(branch.pk).filter(pk=data.get('spent_by')).first()
        if spent_by is None:
            messages.error(request, tr(request, 'The staff member who paid is not active in this branch.', 'Staf yang mengeluarkan uangnya tidak aktif di cabang ini.'))
            return redirect('expense_list')
    paid_with = None
    if (data.get('paid_with') or 'office') != 'office':
        paid_with = resolve_money_account(data.get('paid_with'), staff=True)
        if paid_with is None:
            messages.error(request, tr(request, 'The selected advance was not found.', 'Uang muka yang dipilih tidak ditemukan.'))
            return redirect('expense_list')

    raw_lines = data.get('lines', '')
    try:
        line_rows = json.loads(raw_lines) if isinstance(raw_lines, str) else (raw_lines or [])
    except (json.JSONDecodeError, ValueError):
        line_rows = []

    lines = []
    for i, row in enumerate(line_rows):
        amt = _to_float(row.get('amount', 0))
        if not amt or amt <= 0:
            continue
        category = ExpenseCategory.objects.filter(pk=row.get('category'), is_active=True).first()
        if category is None:
            continue
        # A line's receipts arrive as receipts_<row index>; without one it
        # needs a reason the approver can check (unless one proof covers all).
        receipts = request.FILES.getlist(f'receipts_{i}')
        for f in receipts:
            error = validate_proof_file(f)
            if error:
                messages.error(request, f'{f.name}: {error}')
                return redirect('expense_list')
        reason = (row.get('no_receipt_reason') or '').strip()
        if not receipts and not reason and not proof:
            messages.error(request, tr(request, f'Line {len(lines) + 1}: attach the receipt, or say why there is none.', f'Baris {len(lines) + 1}: lampirkan struk, atau tulis kenapa tidak ada struk.'))
            return redirect('expense_list')
        lines.append({'category': category, 'description': row.get('description', ''), 'amount': int(amt),
                      'receipts': receipts, 'no_receipt_reason': '' if receipts else reason})

    if not lines:
        messages.error(request, tr(request, 'Fill in at least one expense line with a category and an amount.', 'Minimal satu baris beban dengan kategori dan nominal harus diisi.'))
        return redirect('expense_list')

    try:
        expense = expense_service.submit_expense(
            branch=branch, expense_date=_parse_date(data.get('expense_date')) or date.today(), lines=lines,
            created_by=request.user, vendor=data.get('vendor', ''),
            description=data.get('description', ''), note=data.get('note', ''), proof=proof,
            spent_by=spent_by or (None if paid_with else request.user), paid_with=paid_with,
        )
    except FinanceError as e:
        messages.error(request, str(e))
        return redirect('expense_list')

    messages.success(request, tr(request, f'Expense {expense.expense_number} recorded, waiting for approval.', f'Beban {expense.expense_number} dicatat, menunggu persetujuan.'))
    return redirect('expense_detail', pk=expense.pk)


def _decide(request, pk, action):
    expense = get_in_scope_or_404(Expense.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('expense_detail', pk=pk)
    data = _data(request)
    try:
        if action == 'approve':
            expense_service.approve_expense(expense, approved_by=request.user)
            messages.success(request, tr(request, f'{expense.expense_number} approved, ready to pay.', f'{expense.expense_number} disetujui, siap dibayar.'))
        elif action == 'reject':
            expense_service.reject_expense(expense, rejected_by=request.user, reason=(data.get('reason') or '').strip())
            messages.success(request, tr(request, f'{expense.expense_number} rejected.', f'{expense.expense_number} ditolak.'))
        elif action == 'pay':
            account = resolve_money_account(data.get('account'))
            expense_service.pay_expense(
                expense, account=account, payment_date=_parse_date(data.get('payment_date')) or date.today(),
                paid_by=request.user, reference=(data.get('reference') or '').strip(),
            )
            messages.success(request, tr(request, f'{expense.expense_number} paid.', f'{expense.expense_number} dibayar.'))
        else:
            expense_service.void_expense(expense, voided_by=request.user, reason=(data.get('reason') or '').strip())
            messages.success(request, tr(request, f'{expense.expense_number} cancelled.', f'{expense.expense_number} dibatalkan.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('expense_detail', pk=pk)


@require_perm('expenses', 'approve')
def expense_approve(request, pk):
    return _decide(request, pk, 'approve')


@require_perm('expenses', 'approve')
def expense_reject(request, pk):
    return _decide(request, pk, 'reject')


@require_perm('expenses', 'edit')
def expense_pay(request, pk):
    return _decide(request, pk, 'pay')


@require_perm('expenses', 'delete')
def expense_void(request, pk):
    return _decide(request, pk, 'void')


@require_perm('expenses', 'export')
def expense_export_csv(request):
    expenses = _visible(request).select_related('branch', 'vendor').order_by('-expense_date')

    branch = request.GET.get('branch')
    if branch:
        expenses = expenses.filter(branch_id=branch)
    status = request.GET.get('status')
    if status:
        expenses = expenses.filter(status=status)
    expenses = expenses.prefetch_related('lines', 'payments')

    headers = [
        'Expense #', 'Branch', 'Date', 'Vendor', 'Description',
        'Total IDR', 'Total SAR', 'Status', 'Paid on', 'Created At',
    ]
    rows = ([
        e.expense_number, e.branch.name if e.branch_id else '', e.expense_date,
        e.vendor.name if e.vendor_id else '', e.description, e.total_amount, e.total_amount_sar,
        e.get_status_display(), e.payment.payment_date if e.payment else '', e.created_at,
    ] for e in expenses)
    return csv_export_response(f'expenses-{date.today().isoformat()}.csv', headers, rows)


# ── Kategori beban (Finance Pusat dan Admin) ─────────────────────────

@require_perm('expenses', 'edit')
@head_office_only
def expense_categories(request):
    """Categories every branch picks from; each has its own ledger account."""
    from ..models.expense import ExpenseLine
    used = dict(ExpenseLine.objects.values('category_id').annotate(n=Count('id')).values_list('category_id', 'n'))
    return inertia_render(request, 'Finance/ExpenseCategories', props={
        'categories': [{
            'code': c.code, 'name': c.name, 'ledger_account': c.ledger_account_id,
            'is_active': c.is_active, 'used': used.get(c.code, 0),
        } for c in ExpenseCategory.objects.select_related('ledger_account').order_by('ledger_account_id')],
    })


@require_perm('expenses', 'edit')
@head_office_only
def expense_category_new(request):
    if request.method == 'POST':
        try:
            cat = expense_service.create_category(_data(request).get('name'))
            messages.success(request, tr(request, f'Category "{cat.name}" added (account {cat.ledger_account_id}).', f'Kategori "{cat.name}" ditambahkan (akun {cat.ledger_account_id}).'))
        except FinanceError as e:
            messages.error(request, str(e))
    return redirect('expense_categories')


@require_perm('expenses', 'edit')
@head_office_only
def expense_category_edit(request, code):
    category = ExpenseCategory.objects.filter(pk=code).select_related('ledger_account').first()
    if category is None or request.method != 'POST':
        return redirect('expense_categories')
    data = _data(request)
    active = data.get('is_active')
    try:
        expense_service.update_category(
            category, name=data.get('name') if 'name' in data else None,
            is_active=None if active in (None, '') else str(active).lower() in ('1', 'true', 'on'),
        )
        messages.success(request, tr(request, f'Category "{category.name}" updated.', f'Kategori "{category.name}" diperbarui.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('expense_categories')
