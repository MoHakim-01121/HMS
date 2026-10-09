"""Expense views — list, detail, record, pay, void.

Mirrors the shape of payment_views.py: server-rendered Inertia pages, a
create-with-lines endpoint, and an action endpoint per lifecycle step. See
hw/finance/expense_service.py for the actual posting logic — views only
parse the request and translate FinanceError into a flash message.
"""
import json

from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect

from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, operating_branches, scope
from ..models.expense import Expense, ExpenseCategory
from ..models.journal import JournalEntry
from ..models.vendor import Vendor
from ..finance import expense_service
from ..finance.errors import FinanceError
from ..permissions import require_perm
from ..utils import CURRENCIES
from .helpers import (
    serialize_journal_entry, _parse_date, _to_float, _is_mobile,
    pagination_props, csv_export_response, money_account_choices, resolve_money_account,
)

_account_choices = money_account_choices
_resolve_account = resolve_money_account


def _service_line_label(line):
    return (f"{line.invoice.invoice_number} #{line.line_no} {line.description} "
            f"· {line.quantity} pax · {line.invoice.customer_name}")


def _service_line_choices(branches):
    """Baris Services yang masih berlaku dari cabang-cabang `branches`, untuk
    menautkan biaya vendornya."""
    from ..models import InvoiceLine
    lines = (
        InvoiceLine.objects.filter(kind=InvoiceLine.KIND_SERVICE, voided_at__isnull=True,
                                   invoice__branch__in=branches)
        .exclude(invoice__status='void')
        .select_related('invoice__client').order_by('-invoice__issued_date', 'invoice_id', 'line_no')[:200]
    )
    return [{'value': str(l.pk), 'label': _service_line_label(l), 'branch': l.invoice.branch_id} for l in lines]


# What _expense_props reads, fetched once for a page of expenses.
_PROPS_PREFETCH = ('lines__category', 'lines__service_line__invoice__client', 'payments__source_account')


def _expense_props(e):
    return {
        'id': e.pk,
        'expense_number': e.expense_number,
        'branch': e.branch_id,
        'branch_name': e.branch.name if e.branch_id else None,
        'expense_date': e.expense_date.isoformat() if e.expense_date else None,
        'vendor': e.vendor.name if e.vendor_id else '',
        'description': e.description,
        'currency': e.currency,
        'total_amount': e.total_amount,
        'total_amount_sar': e.total_amount_sar,
        'paid_sar': e.paid_sar,
        'outstanding_sar': e.outstanding_sar,
        # Lifecycle, and for a posted expense its payment state (derived).
        'status': e.display_status,
        'status_display': e.display_status_label,
        'note': e.note,
        'proof_url': e.proof.url if e.proof else None,
        'created_by': e.created_by.username if e.created_by else None,
        'created_at': e.created_at.isoformat(),
        'lines': [{
            'id': l.pk, 'category': l.category_id, 'category_name': l.category.name,
            'description': l.description, 'amount': l.amount, 'amount_sar': l.amount_sar,
            'service_line': _service_line_label(l.service_line) if l.service_line_id else None,
        } for l in e.lines.all()],
        'payments': [{
            'id': p.pk,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'amount': p.amount, 'currency': p.currency, 'amount_sar': p.amount_sar,
            'account_name': str(p.source_account) if p.source_account else None,
            'reference': p.reference, 'status': p.status,
            'status_display': p.get_status_display(),
        } for p in e.payments.all()],
    }


def _visible(request):
    """Expenses of the branches the user covers."""
    return scope(Expense.objects.all(), request.user)


@require_perm('expenses', 'view')
def expense_list(request):
    expenses = _visible(request).select_related('branch', 'created_by', 'vendor')

    branch = request.GET.get('branch')
    if branch:
        expenses = expenses.filter(branch_id=branch)
    status = request.GET.get('status')
    expenses = expenses.prefetch_related(*_PROPS_PREFETCH).order_by('-expense_date', '-created_at')
    if status:
        # Paid / partially paid are derived from the payments.
        expenses = [e for e in expenses if e.display_status == status]

    paginator = Paginator(expenses, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_expenses = list(page_obj)

    all_expenses = list(_visible(request).exclude(status=Expense.STATUS_VOIDED).prefetch_related('lines', 'payments'))
    stats = {
        'total': len(all_expenses),
        'total_sar': sum(e.total_amount_sar for e in all_expenses),
        'outstanding_sar': sum(e.outstanding_sar for e in all_expenses),
        'unpaid_count': sum(1 for e in all_expenses if e.display_status != Expense.STATUS_PAID),
    }

    # Expenses belong to a branch, never to head office; with one branch to
    # choose from the form fills it in and shows no picker.
    branches = list(operating_branches(request.user))
    codes = [b.code for b in branches]
    return inertia_render(request, 'Expense/List', props={
        'expenses': [_expense_props(e) for e in page_expenses],
        'branch_choices': [{'value': b.code, 'label': b.name} for b in branches],
        'category_choices': [{'value': c.code, 'label': c.name} for c in ExpenseCategory.objects.filter(is_active=True)],
        'status_choices': Expense.DISPLAY_CHOICES,
        'vendor_choices': [v.name for v in Vendor.objects.filter(is_active=True).order_by('name')],
        'service_line_choices': _service_line_choices(codes),
        'account_choices': _account_choices(branches=codes),
        'stats': stats,
        'branch_filter': branch or '',
        'status_filter': status or '',
        'pagination': pagination_props(page_obj),
    })


@require_perm('expenses', 'view')
def expense_detail(request, pk):
    expense = get_in_scope_or_404(
        Expense.objects.select_related('branch', 'created_by', 'vendor').prefetch_related(*_PROPS_PREFETCH),
        request.user, pk=pk,
    )
    journal_entries = (
        JournalEntry.objects.for_source('Expense', expense.pk)
        | JournalEntry.objects.for_source('ExpensePayment', list(expense.payments.values_list('pk', flat=True)))
    ).order_by('-entry_date')

    return inertia_render(request, 'Expense/Detail', props={
        'expense': _expense_props(expense),
        'account_choices': _account_choices(expense.branch_id),
        'journal_entries': [
            serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit)
            for e in journal_entries
        ],
    })


@require_perm('expenses', 'create')
def expense_record(request):
    if request.method != 'POST':
        return redirect('expense_list')

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    branches = operating_branches(request.user)
    branch = branches.filter(pk=data.get('branch')).first() if data.get('branch') else None
    if branch is None and not data.get('branch') and branches.count() == 1:
        branch = branches.first()
    if branch is None:
        messages.error(request, 'Pilih cabang pengeluaran — pengeluaran milik cabang, bukan Pusat.')
        return redirect('expense_list')

    expense_date_val = _parse_date(data.get('expense_date')) or date.today()
    currency = (data.get('currency') or 'SAR').upper()
    if currency not in CURRENCIES:
        messages.error(request, f'Mata uang tidak dikenal: {currency}.')
        return redirect('expense_list')
    exchange_rate = _to_float(data.get('exchange_rate'), 1) or 1

    raw_lines = data.get('lines', '')
    try:
        line_rows = json.loads(raw_lines) if isinstance(raw_lines, str) else (raw_lines or [])
    except (json.JSONDecodeError, ValueError):
        line_rows = []

    lines = []
    for row in line_rows:
        amt = _to_float(row.get('amount', 0))
        if not amt or amt <= 0:
            continue
        category = ExpenseCategory.objects.filter(pk=row.get('category'), is_active=True).first()
        if category is None:
            continue
        service_line = None
        if row.get('service_line'):
            from ..models import InvoiceLine
            service_line = InvoiceLine.objects.select_related('invoice').filter(pk=row['service_line']).first()
        lines.append({'category': category, 'description': row.get('description', ''), 'amount': int(amt),
                      'service_line': service_line})

    if not lines:
        messages.error(request, 'Minimal satu baris beban dengan kategori dan nominal harus diisi.')
        return redirect('expense_list')

    pay_now = None
    account_value = data.get('pay_now_account')
    if account_value:
        account = _resolve_account(account_value)
        if account:
            pay_now = {'account': account, 'reference': data.get('pay_now_reference', '')}

    try:
        expense = expense_service.record_expense(
            branch=branch, expense_date=expense_date_val, lines=lines,
            created_by=request.user, vendor=data.get('vendor', ''),
            description=data.get('description', ''), currency=currency,
            exchange_rate=exchange_rate, note=data.get('note', ''),
            pay_now=pay_now,
        )
    except FinanceError as e:
        messages.error(request, str(e))
        return redirect('expense_list')

    messages.success(request, f'Expense {expense.expense_number} berhasil dicatat.')
    return redirect('expense_detail', pk=expense.pk)


@require_perm('expenses', 'edit')
def expense_pay(request, pk):
    expense = get_in_scope_or_404(Expense.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('expense_detail', pk=pk)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    amount = _to_float(data.get('amount'))
    if not amount:
        messages.error(request, 'Jumlah pembayaran harus diisi.')
        return redirect('expense_detail', pk=pk)

    account = _resolve_account(data.get('account'))
    if not account:
        messages.error(request, 'Rekening pembayar harus dipilih.')
        return redirect('expense_detail', pk=pk)
    currency = (data.get('currency') or expense.currency).upper()
    if currency not in CURRENCIES:
        messages.error(request, f'Mata uang tidak dikenal: {currency}.')
        return redirect('expense_detail', pk=pk)

    try:
        expense_service.add_expense_payment(
            expense, amount=amount, payment_date=_parse_date(data.get('payment_date')) or date.today(),
            account=account,
            currency=currency,
            exchange_rate=_to_float(data.get('exchange_rate'), 1) or 1,
            reference=data.get('reference', ''), note=data.get('note', ''),
            created_by=request.user,
        )
        messages.success(request, f'Pembayaran untuk {expense.expense_number} tercatat.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('expense_detail', pk=pk)


@require_perm('expenses', 'delete')
def expense_void(request, pk):
    expense = get_in_scope_or_404(Expense.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('expense_detail', pk=pk)

    try:
        expense_service.void_expense(expense, created_by=request.user)
        messages.success(request, f'Expense {expense.expense_number} di-void.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('expense_detail', pk=pk)


@require_perm('expenses', 'export')
def expense_export_csv(request):
    expenses = _visible(request).select_related('branch').order_by('-expense_date')

    branch = request.GET.get('branch')
    if branch:
        expenses = expenses.filter(branch_id=branch)
    status = request.GET.get('status')
    expenses = expenses.prefetch_related('lines', 'payments').select_related('vendor')
    if status:
        expenses = [e for e in expenses if e.display_status == status]

    headers = [
        'Expense #', 'Branch', 'Date', 'Vendor', 'Description', 'Currency',
        'Total', 'Total SAR', 'Paid SAR', 'Outstanding SAR', 'Status', 'Created At',
    ]
    rows = ([
        e.expense_number, e.branch.name if e.branch_id else '', e.expense_date,
        e.vendor.name if e.vendor_id else '', e.description, e.currency, e.total_amount, e.total_amount_sar,
        e.paid_sar, e.outstanding_sar, e.display_status, e.created_at,
    ] for e in expenses)
    return csv_export_response(f'expenses-{date.today().isoformat()}.csv', headers, rows)
