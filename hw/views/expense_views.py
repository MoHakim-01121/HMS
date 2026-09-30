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
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models.branch import Branch
from ..models.expense import Expense, ExpenseCategory
from ..models.journal import JournalEntry
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


def _expense_props(e):
    return {
        'id': e.pk,
        'expense_number': e.expense_number,
        'branch': e.branch_id,
        'branch_name': e.branch.name if e.branch_id else None,
        'expense_date': e.expense_date.isoformat() if e.expense_date else None,
        'vendor': e.vendor,
        'description': e.description,
        'currency': e.currency,
        'total_amount': e.total_amount,
        'total_amount_sar': e.total_amount_sar,
        'paid_sar': e.paid_sar,
        'outstanding_sar': e.outstanding_sar,
        'status': e.status,
        'status_display': e.get_status_display(),
        'note': e.note,
        'proof_url': e.proof.url if e.proof else None,
        'created_by': e.created_by.username if e.created_by else None,
        'created_at': e.created_at.isoformat(),
        'lines': [{
            'id': l.pk, 'category': l.category_id, 'category_name': l.category.name,
            'description': l.description, 'amount': l.amount, 'amount_sar': l.amount_sar,
        } for l in e.lines.select_related('category')],
        'payments': [{
            'id': p.pk,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'amount': p.amount, 'currency': p.currency, 'amount_sar': p.amount_sar,
            'account_name': str(p.source_account) if p.source_account else None,
            'reference': p.reference, 'status': p.status,
            'status_display': p.get_status_display(),
        } for p in e.payments.select_related('source_account')],
    }


@require_perm('expenses', 'view')
def expense_list(request):
    expenses = Expense.objects.select_related('branch', 'created_by')

    branch = request.GET.get('branch')
    if branch:
        expenses = expenses.filter(branch_id=branch)
    status = request.GET.get('status')
    if status:
        expenses = expenses.filter(status=status)

    expenses = expenses.order_by('-expense_date', '-created_at')

    paginator = Paginator(expenses, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_expenses = list(page_obj)

    all_expenses = Expense.objects.exclude(status=Expense.STATUS_VOIDED)
    stats = {
        'total': all_expenses.count(),
        'total_sar': sum(e.total_amount_sar for e in all_expenses),
        'outstanding_sar': sum(e.outstanding_sar for e in all_expenses),
        'unpaid_count': all_expenses.exclude(status=Expense.STATUS_PAID).count(),
    }

    return inertia_render(request, 'Expense/List', props={
        'expenses': [_expense_props(e) for e in page_expenses],
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True)],
        'category_choices': [{'value': c.code, 'label': c.name} for c in ExpenseCategory.objects.filter(is_active=True)],
        'status_choices': Expense.STATUS_CHOICES,
        'account_choices': _account_choices(),
        'stats': stats,
        'branch_filter': branch or '',
        'status_filter': status or '',
        'pagination': pagination_props(page_obj),
    })


@require_perm('expenses', 'view')
def expense_detail(request, pk):
    expense = get_object_or_404(
        Expense.objects.select_related('branch', 'created_by', 'period'), pk=pk,
    )
    journal_entries = JournalEntry.objects.filter(
        reference_type__in=['Expense', 'ExpensePayment'],
    ).filter(
        reference_id__in=[expense.pk, *expense.payments.values_list('pk', flat=True)],
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

    branch = Branch.objects.filter(pk=data.get('branch'), is_active=True).first()
    if branch is None:
        messages.error(request, 'Cabang harus dipilih.')
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
        lines.append({'category': category, 'description': row.get('description', ''), 'amount': int(amt)})

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
    expense = get_object_or_404(Expense, pk=pk)
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
    expense = get_object_or_404(Expense, pk=pk)
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
    expenses = Expense.objects.select_related('branch').order_by('-expense_date')

    branch = request.GET.get('branch')
    if branch:
        expenses = expenses.filter(branch_id=branch)
    status = request.GET.get('status')
    if status:
        expenses = expenses.filter(status=status)

    headers = [
        'Expense #', 'Branch', 'Date', 'Vendor', 'Description', 'Currency',
        'Total', 'Total SAR', 'Paid SAR', 'Outstanding SAR', 'Status', 'Created At',
    ]
    rows = ([
        e.expense_number, e.branch.name if e.branch_id else '', e.expense_date,
        e.vendor, e.description, e.currency, e.total_amount, e.total_amount_sar,
        e.paid_sar, e.outstanding_sar, e.status, e.created_at,
    ] for e in expenses)
    return csv_export_response(f'expenses-{date.today().isoformat()}.csv', headers, rows)
