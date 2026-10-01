"""Expense orchestration (Master Architecture v2.0 §29–31, §63).

Accrual: Dr Beban (per baris) / Cr Utang Usaha (AP).
Pembayaran: Dr Utang Usaha / Cr Bank/Kas.

Semua lewat posting layer (post_entry) — immutable, balanced, idempotent.
Koreksi = reversal, bukan delete.
"""
from django.db import transaction
from django.utils import timezone

from ..models.expense import Expense, ExpenseLine, ExpensePayment
from ..models.journal import JournalEntry
from ..utils import convert_to_sar
from . import accounts as coa
from .errors import FinanceError
from .posting import native, get_period_for_date, post_entry, reverse_entry


def _sar(amount, currency, rate):
    return int(round(convert_to_sar(amount, currency, float(rate))))


def _live_entries(source_type, source_id):
    return list(JournalEntry.objects.for_source(source_type, source_id).live())


def _txn(expense, amount):
    """Nominal asli baris beban non-SAR."""
    if expense.currency == 'SAR':
        return {}
    return {'currency': expense.currency, 'amount_txn': int(amount)}


def resolve_vendor(vendor):
    """Vendor dari nama (dibuat bila belum ada), objek Vendor, atau None."""
    from ..models.client import client_name_key
    from ..models.vendor import Vendor
    if vendor is None or isinstance(vendor, Vendor):
        return vendor
    name = str(vendor).strip()
    if not name:
        return None
    return Vendor.objects.filter(name_key=client_name_key(name)).first() or Vendor.objects.create(name=name)


def _check_service_line(line, branch):
    """Biaya vendor hanya untuk baris Services yang dijual cabang ini (B12/B13)."""
    if line.kind != line.KIND_SERVICE or line.voided_at is not None:
        raise FinanceError('Biaya vendor hanya bisa ditautkan ke baris Services yang masih berlaku.')
    if line.invoice.branch_id != branch.pk:
        raise FinanceError(
            f'Baris Services {line.invoice.invoice_number} #{line.line_no} dijual cabang lain; '
            'biaya vendornya dicatat di cabang itu.'
        )


@transaction.atomic
def record_expense(*, branch, expense_date, lines, created_by, vendor=None,
                   description='', currency='SAR', exchange_rate=1, note='',
                   proof=None, pay_now=None):
    """Buat Expense (POSTED) + baris + jurnal accrual. Optional bayar penuh langsung.
    lines: iterable {category, ledger_account?, description?, amount, service_line?}
    vendor: nama vendor (dibuat bila belum ada), objek Vendor, atau None.
    pay_now: None atau {account (MoneyAccount), payment_date?, reference?}
    """
    lines = list(lines)
    if not lines:
        raise FinanceError('Expense butuh minimal satu baris')
    get_period_for_date(expense_date)
    total = sum(int(l['amount']) for l in lines)
    for l in lines:
        if l.get('service_line') is not None:
            _check_service_line(l['service_line'], branch)
    expense = Expense.objects.create(
        expense_number=Expense.generate_number(),
        branch=branch, expense_date=expense_date, vendor=resolve_vendor(vendor),
        description=description, currency=currency,
        status=Expense.STATUS_POSTED,
        note=note, proof=proof, created_by=created_by,
    )
    for l in lines:
        amt = int(l['amount'])
        ExpenseLine.objects.create(
            expense=expense, category=l['category'],
            ledger_account=l.get('ledger_account'),
            service_line=l.get('service_line'),
            description=l.get('description', ''),
            amount=amt, amount_sar=_sar(amt, currency, exchange_rate),
        )

    _post_accrual(expense, created_by)

    if pay_now is not None:
        add_expense_payment(
            expense,
            amount=total, currency=currency, exchange_rate=exchange_rate,
            payment_date=pay_now.get('payment_date') or expense_date,
            account=pay_now.get('account'),
            reference=pay_now.get('reference', ''),
            created_by=created_by,
        )
    return expense


def _post_accrual(expense, created_by):
    br = expense.branch_id
    lines = [
        {'account': ln.account_code, 'debit': ln.amount_sar, 'branch': br,
         'note': ln.description or ln.category.name, **_txn(expense, ln.amount)}
        for ln in expense.lines.all() if ln.amount_sar
    ]
    lines.append({'account': coa.AP, 'credit': expense.total_amount_sar, 'branch': br,
                  **_txn(expense, expense.total_amount)})
    return post_entry(
        entry_type=JournalEntry.TYPE_EXPENSE,
        description=f"Expense {expense.expense_number} — {expense.vendor or expense.description}",
        entry_date=expense.expense_date,
        lines=lines,
        source_type='Expense',
        source_id=expense.pk,
        idempotency_key=f"expense:{expense.expense_number}:accrual",
        created_by=created_by,
    )


@transaction.atomic
def add_expense_payment(expense, *, amount, payment_date, created_by,
                        account=None, currency='SAR',
                        exchange_rate=1, reference='', note=''):
    """Bayar (sebagian/penuh) sebuah Expense: Dr AP / Cr Bank/Kas."""
    if expense.status == Expense.STATUS_VOIDED:
        raise FinanceError('Expense sudah void')
    if account is None:
        raise FinanceError('Pilih rekening atau kas yang membayar.')
    from .bank_ledger import ensure_account_currency
    ensure_account_currency(account, currency)
    if account.branch_id != expense.branch_id:
        raise FinanceError(
            f'Rekening {account} milik cabang lain — expense ini dibayar dari rekening cabangnya sendiri.'
        )

    amt_sar = _sar(amount, currency, exchange_rate)
    if amt_sar > expense.outstanding_sar:
        raise FinanceError(
            f"Pembayaran {amt_sar:,} melebihi sisa utang {expense.outstanding_sar:,}"
        )

    ep = ExpensePayment.objects.create(
        expense=expense, payment_date=payment_date, amount=amount,
        amount_sar=amt_sar,
        source_account=account,
        reference=reference, status=ExpensePayment.STATUS_PAID,
        note=note, created_by=created_by,
    )
    src = ep.source_account
    post_entry(
        entry_type=JournalEntry.TYPE_EXPENSE,
        description=f"Bayar expense {expense.expense_number}",
        entry_date=payment_date,
        lines=[
            {'account': coa.AP, 'debit': amt_sar, 'branch': expense.branch_id},
            {'account': src.ledger_account_id, 'credit': amt_sar, 'branch': src.branch_id,
             **native(src, amount, exchange_rate)},
        ],
        source_type='ExpensePayment',
        source_id=ep.pk,
        idempotency_key=f"expensepayment:{ep.pk}:pay",
        created_by=created_by,
    )
    from .bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=src, direction='out', amount_sar=amt_sar,
        source_type='ExpensePayment', source_id=ep.pk,
        transaction_date=payment_date, currency=currency, amount=amount, reference=reference,
    )
    return ep


@transaction.atomic
def void_expense(expense, *, created_by, date=None):
    """Batalkan Expense: reverse semua jurnal accrual + pembayaran yang hidup,
    set status VOIDED. Baris/pembayaran tidak dihapus (audit)."""
    date = date or timezone.now().date()
    from .bank_ledger import void_bank_transactions
    for ep in expense.payments.filter(status=ExpensePayment.STATUS_PAID):
        for e in _live_entries('ExpensePayment', ep.pk):
            reverse_entry(e, reversal_date=date, created_by=created_by)
        ep.status = ExpensePayment.STATUS_VOID
        ep.save(update_fields=['status'])
        void_bank_transactions('ExpensePayment', ep.pk)
    for e in _live_entries('Expense', expense.pk):
        reverse_entry(e, reversal_date=date, created_by=created_by)
    expense.status = Expense.STATUS_VOIDED
    expense.save(update_fields=['status', 'updated_at'])
    return expense
