"""Finance helpers — immutable double-entry journal posting functions.

All functions enforce:
1. Double-entry balance invariant (SUM(lines) = 0)
2. Period lock check (no posting to closed periods)
3. Immutable entries (no UPDATE/DELETE)
4. Complete audit trail via PaymentLog
"""
from decimal import Decimal

from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone

from .models.period import FinancialPeriod
from .models.payment import PaymentRecord, PaymentLog
from .models.journal import (
    JournalEntry, JournalLine, LedgerAccount, Account, AccountType, ACCOUNT_TYPE_MAP,
)
from .models.invoice import Invoice
from .models.choices import Company
from .finance.accounts import resolve_account_code, AR
from .ledger import cash_destination, cash_journal_account


def _account_obj(ref):
    """Terima kode v2, kode enum v1, atau instance LedgerAccount → LedgerAccount."""
    if isinstance(ref, LedgerAccount):
        return ref
    return LedgerAccount.objects.get(pk=resolve_account_code(str(ref)))


class FinanceError(Exception):
    """Base exception for finance operations."""
    pass


class PeriodLockedError(FinanceError):
    """Posting to a locked period."""
    pass


class JournalImbalanceError(FinanceError):
    """Journal entry doesn't balance (debit != credit)."""
    pass


class PaymentAlreadyProcessedError(FinanceError):
    """Payment already confirmed/allocated."""
    pass


class InsufficientAllocationError(FinanceError):
    """Payment amount exceeds invoice remaining."""
    pass


# ── Period helpers ─────────────────────────────────────────────


def get_current_period(company=None):
    """Return the current open period. Raises PeriodLockedError if none open."""
    now = timezone.now().date()
    period = FinancialPeriod.objects.filter(
        date_from__lte=now,
        date_to__gte=now,
        status=FinancialPeriod.STATUS_OPEN,
    ).first()
    if not period:
        raise PeriodLockedError("Tidak ada periode terbuka untuk tanggal saat ini")
    return period


def get_period_for_date(date, company=None):
    """Return the period that contains the given date."""
    period = FinancialPeriod.objects.filter(
        date_from__lte=date,
        date_to__gte=date,
    ).first()
    if not period:
        raise PeriodLockedError(f"Tidak ada periode untuk tanggal {date}")
    return period


def check_period_postable(period):
    """Verify period allows posting."""
    if not period.is_postable:
        raise PeriodLockedError(
            f"Periode {period.name} sudah {period.get_status_display()}, "
            "tidak bisa posting journal entry"
        )


# ── Journal entry creation ─────────────────────────────────────


def _validate_balance(lines):
    """Ensure journal entry balances (SUM = 0)."""
    total = sum(l['amount_sar'] for l in lines)
    if total != 0:
        raise JournalImbalanceError(
            f"Journal entry tidak balance: total = {total:+,} SAR. "
            f"Debit: {sum(l['amount_sar'] for l in lines if l['amount_sar'] > 0):,}, "
            f"Credit: {abs(sum(l['amount_sar'] for l in lines if l['amount_sar'] < 0)):,}"
        )


def create_journal_entry(
    entry_type,
    description,
    entry_date,
    lines,
    company=Company.KONOZ,
    reference_type='',
    reference_id=None,
    created_by=None,
    is_reversal=False,
    reverses=None,
):
    """Adapter lama — delegasi ke hw.finance.posting.post_entry.

    `lines` = list {account: <kode v1/v2>, amount_sar: <signed>, dimensi...}.
    Dipakai penalty_views & confirm_payment sampai dirombak ke posting
    layer (Fase 5). Kode baru panggil post_entry() langsung.
    """
    from .finance.posting import post_entry

    return post_entry(
        entry_type=entry_type,
        description=description,
        entry_date=entry_date,
        lines=lines,
        company=company,
        source_type=reference_type,
        source_id=reference_id,
        created_by=created_by,
        is_reversal=is_reversal,
        reverses=reverses,
    )


def reverse_journal_entry(original_entry, reversal_date, created_by, note=''):
    """Adapter lama — delegasi ke hw.finance.posting.reverse_entry."""
    from .finance.posting import reverse_entry

    return reverse_entry(
        original_entry, reversal_date=reversal_date, created_by=created_by, note=note,
    )


# ── Payment helpers ─────────────────────────────────────────────


@transaction.atomic
def create_payment_record(
    invoice,
    client,
    payment_date,
    amount,
    currency='SAR',
    exchange_rate=1,
    method='',
    bank_name='',
    account_number='',
    reference='',
    note='',
    proof=None,
    created_by=None,
    reservation=None,
    service_item=None,
    received_in='sby',
):
    """Create a PaymentRecord + JournalEntry atomically.

    Lifecycle: pending → confirmed (via confirm_payment)

    `received_in`: kas mana uangnya diterima ('sby'/'jkt'/'pusat') —
    menentukan wallet mengendap dan akun kas di jurnal.
    """
    from .utils import convert_to_sar

    # Calculate SAR
    amount_sar = int(round(convert_to_sar(amount, currency, float(exchange_rate))))

    # Get period
    period = get_period_for_date(payment_date)

    # Create PaymentRecord
    payment = PaymentRecord.objects.create(
        payment_number=PaymentRecord.generate_number(),
        invoice=invoice,
        client=client,
        reservation=reservation,
        service_item=service_item,
        payment_date=payment_date,
        amount=amount,
        currency=currency,
        exchange_rate=exchange_rate,
        amount_sar=amount_sar,
        received_in=received_in if received_in in ('sby', 'jkt', 'pusat') else 'sby',
        method=method,
        bank_name=bank_name,
        account_number=account_number,
        reference=reference,
        note=note,
        proof=proof,
        status=PaymentRecord.STATUS_PENDING,
        company=invoice.company,
        created_by=created_by,
        period=period,
    )

    # Create initial log
    PaymentLog.objects.create(
        payment=payment,
        action=PaymentLog.ACTION_CREATED,
        after_state=_payment_snapshot(payment),
        performed_by=created_by,
        note='Payment record created',
    )

    return payment


@transaction.atomic
def confirm_payment(payment, confirmed_by, note=''):
    """Confirm a pending payment → post JournalEntry lewat posting layer.

    DR Kas (sesuai received_in) / CR Piutang (dipecah per PaymentAllocation
    kalau ada). Idempotent per payment.
    """
    from .finance.posting import post_payment

    if payment.status != PaymentRecord.STATUS_PENDING:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} sudah {payment.get_status_display()}"
        )

    journal = post_payment(payment, created_by=confirmed_by)

    # Update payment status
    old_state = _payment_snapshot(payment)
    payment.status = PaymentRecord.STATUS_CONFIRMED
    payment.confirmed_by = confirmed_by
    payment.confirmed_at = timezone.now()
    payment.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])

    # Create log
    PaymentLog.objects.create(
        payment=payment,
        action=PaymentLog.ACTION_CONFIRMED,
        before_state=old_state,
        after_state=_payment_snapshot(payment),
        performed_by=confirmed_by,
        note=note or f'Confirmed by {confirmed_by}',
    )

    return payment, journal


@transaction.atomic
def allocate_payment(payment, allocation_date, created_by, note=''):
    """Tandai payment ALLOCATED + sinkron status invoice.

    Jurnal (DR Kas / CR Piutang, dipecah per PaymentAllocation) sudah
    diposting di confirm_payment. PaymentAllocation rows sendiri dibuat
    pemanggil (posting.allocate_payment) sebelum confirm. Fungsi ini
    tinggal transisi status + Invoice.sync_status().
    """
    if payment.status != PaymentRecord.STATUS_CONFIRMED:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} harus confirmed dulu"
        )

    old_state = _payment_snapshot(payment)
    if payment.invoice_id:
        payment.invoice.sync_status()

    payment.status = PaymentRecord.STATUS_ALLOCATED
    payment.save(update_fields=['status'])

    # Create log
    PaymentLog.objects.create(
        payment=payment,
        action=PaymentLog.ACTION_ALLOCATED,
        before_state=old_state,
        after_state=_payment_snapshot(payment),
        performed_by=created_by,
        note=note or f'Allocated to invoice {payment.invoice.invoice_number}',
    )

    return payment


def _payment_snapshot(payment):
    """Create a JSON-serializable snapshot of payment state."""
    return {
        'payment_number': payment.payment_number,
        'status': payment.status,
        'amount_sar': payment.amount_sar,
        'invoice_id': payment.invoice_id,
        'client_id': payment.client_id,
    }


# ── Query helpers (to replace ledger.py functions) ──────────────


def _net(qs):
    agg = qs.aggregate(d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or 0) - (agg['c'] or 0)


def client_balance(client):
    """Client's receivable balance from journal lines.

    Positive = client owes us (receivable).
    """
    return _net(JournalLine.objects.filter(client=client, account_id=AR))


def invoice_paid_sar_jl(invoice_id):
    """How much has been credited to AR for an invoice (from journal lines).

    Returns a NEGATIVE number (credits), matching the legacy convention:
    callers negate it to get a positive "paid" amount.
    """
    agg = JournalLine.objects.filter(
        invoice_id=invoice_id, account_id=AR, credit__gt=0,
    ).aggregate(c=Sum('credit'))
    return -(agg['c'] or 0)


def kas_saldo(account, company=None):
    """Cash/account balance (debit - credit) from journal lines."""
    qs = JournalLine.objects.filter(account_id=resolve_account_code(str(account)))
    if company:
        qs = qs.filter(journal_entry__company=company)
    return _net(qs)


def client_statement(client, date_from=None, date_to=None):
    """Generate a client statement from JournalLines.

    Returns a list of transactions sorted by date with running balance.
    Positive balance = client owes us (receivable).
    Negative balance = we owe client (prepaid/credit).
    """
    lines = JournalLine.objects.filter(
        client=client,
    ).select_related('journal_entry', 'account').order_by('journal_entry__entry_date', 'journal_entry__created_at')

    if date_from:
        lines = lines.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        lines = lines.filter(journal_entry__entry_date__lte=date_to)

    transactions = []
    running_balance = 0

    for line in lines:
        entry = line.journal_entry
        running_balance += line.amount_sar

        transactions.append({
            'date': entry.entry_date.isoformat(),
            'entry_number': entry.entry_number,
            'entry_type': entry.entry_type,
            'entry_type_display': entry.get_entry_type_display(),
            'description': entry.description,
            'account': line.account_id,
            'account_display': line.account.name,
            'amount_sar': line.amount_sar,
            'balance': running_balance,
            'reference_type': entry.reference_type,
            'reference_id': entry.reference_id,
        })

    return {
        'transactions': transactions,
        'closing_balance': running_balance,
        'total_debit': sum(t['amount_sar'] for t in transactions if t['amount_sar'] > 0),
        'total_credit': abs(sum(t['amount_sar'] for t in transactions if t['amount_sar'] < 0)),
    }


def account_summary(company=None):
    """Summary of all accounts from JournalLines (balance = debit - credit)."""
    qs = JournalLine.objects.all()
    if company:
        qs = qs.filter(journal_entry__company=company)

    totals = {
        row['account']: (row['d'] or 0) - (row['c'] or 0)
        for row in qs.values('account').annotate(d=Sum('debit'), c=Sum('credit'))
    }
    summary = {}
    for acc in LedgerAccount.objects.all():
        total = totals.get(acc.code)
        if total:
            summary[acc.code] = {'label': acc.name, 'balance': total}
    return summary
