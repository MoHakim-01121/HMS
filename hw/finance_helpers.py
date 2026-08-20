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
    JournalEntry, JournalLine, Account, AccountType, ACCOUNT_TYPE_MAP,
)
from .models.invoice import Invoice
from .models.choices import Company


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


@transaction.atomic
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
    """Create a balanced, immutable journal entry.

    Args:
        entry_type: JournalEntry TYPE_* constant
        description: Human-readable description
        entry_date: Date of the entry
        lines: List of dicts with keys:
            - account: Account.* constant
            - amount_sar: int (positive=debit, negative=credit)
            - Optional: client, invoice, reservation, service_item, penalty
            - Optional: note
        company: Company.* constant
        reference_type: Source model name (e.g. 'PaymentRecord', 'Invoice')
        reference_id: Source object PK
        created_by: User instance
        is_reversal: True if this is a reversal entry
        reverses: JournalEntry this reverses

    Returns:
        JournalEntry instance (committed to DB)
    """
    # Validate
    _validate_balance(lines)

    # Get period
    period = get_period_for_date(entry_date)
    check_period_postable(period)

    # Create entry
    entry = JournalEntry.objects.create(
        entry_number=JournalEntry.generate_number(),
        entry_type=entry_type,
        description=description,
        entry_date=entry_date,
        reference_type=reference_type,
        reference_id=reference_id,
        is_reversal=is_reversal,
        reverses=reverses,
        period=period,
        company=company,
        created_by=created_by,
    )

    # Create lines
    journal_lines = []
    for line_data in lines:
        line = JournalLine(
            journal_entry=entry,
            account=line_data['account'],
            amount_sar=line_data['amount_sar'],
            note=line_data.get('note', ''),
        )
        # Set dimension FKs if provided
        for dim in ('client', 'invoice', 'reservation', 'service_item', 'penalty'):
            if dim in line_data and line_data[dim] is not None:
                setattr(line, dim, line_data[dim])
        journal_lines.append(line)

    JournalLine.objects.bulk_create(journal_lines)

    # Verify balance after save
    saved_total = JournalLine.objects.filter(journal_entry=entry).aggregate(
        total=models.Sum('amount_sar')
    )['total']
    if saved_total != 0:
        raise JournalImbalanceError(
            f"Journal entry balance check failed after save: {saved_total:+,}"
        )

    return entry


@transaction.atomic
def reverse_journal_entry(original_entry, reversal_date, created_by, note=''):
    """Create a reversal entry for an existing journal entry.

    A reversal creates a new entry with opposite lines, effectively
    zeroing out the original entry's impact.
    """
    if original_entry.is_reversal:
        raise FinanceError("Tidak bisa me-reversal entry yang sudah reversal")

    # Build reversal lines (flip sign)
    reversal_lines = []
    for line in original_entry.lines.all():
        reversal_lines.append({
            'account': line.account,
            'amount_sar': -line.amount_sar,  # Flip sign
            'client': line.client,
            'invoice': line.invoice,
            'reservation': line.reservation,
            'service_item': line.service_item,
            'penalty': line.penalty,
            'note': f'Reversal of {original_entry.entry_number}',
        })

    # Create reversal entry
    reversal = create_journal_entry(
        entry_type=JournalEntry.TYPE_REVERSAL,
        description=f'Reversal: {original_entry.description}',
        entry_date=reversal_date,
        lines=reversal_lines,
        company=original_entry.company,
        reference_type='JournalEntry',
        reference_id=original_entry.pk,
        created_by=created_by,
        is_reversal=True,
        reverses=original_entry,
    )

    return reversal


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
):
    """Create a PaymentRecord + JournalEntry atomically.

    Lifecycle: pending → confirmed (via confirm_payment)
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
    """Confirm a pending payment → creates JournalEntry.

    Journal entry:
    + Cash_SBY or Cash_Pusat (money masuk)
    - Receivable (piutang client berkurang)
    """
    if payment.status != PaymentRecord.STATUS_PENDING:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} sudah {payment.get_status_display()}"
        )

    # Determine cash account based on method
    # TODO: auto-detect from method/bank
    cash_account = Account.CASH_SBY

    # Determine which dimensions to tag
    dims = {}
    if payment.client:
        dims['client'] = payment.client
    if payment.invoice:
        dims['invoice'] = payment.invoice
    if payment.reservation:
        dims['reservation'] = payment.reservation
    if payment.service_item:
        dims['service_item'] = payment.service_item

    # Create journal entry: Cash (debit) + Receivable (credit)
    journal_lines = [
        {
            'account': cash_account,
            'amount_sar': payment.amount_sar,  # Debit: money masuk
            **dims,
        },
        {
            'account': Account.RECEIVABLE,
            'amount_sar': -payment.amount_sar,  # Credit: piutang berkurang
            **dims,
        },
    ]

    journal = create_journal_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f'Payment {payment.payment_number} dari {payment.client}',
        entry_date=payment.payment_date,
        lines=journal_lines,
        company=payment.company,
        reference_type='PaymentRecord',
        reference_id=payment.pk,
        created_by=confirmed_by,
    )

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
    """Allocate confirmed payment to invoice → creates JournalEntry.

    Journal entry:
    + Receivable (piutang client naik — wait, no)
    Actually: we're allocating the payment to the invoice, so:
    - Cash (money keluar dari kas) — NO, money stays in kas
    + Receivable (we mark the receivable as allocated)

    Actually, allocation means: we assign the payment to specific invoices.
    The journal entry is:
    + Invoice.paid_sar += payment.amount_sar
    - (no journal entry needed — the allocation is tracked in PaymentRecord)

    Wait, let me rethink. In double-entry:
    - When payment is confirmed: DR Cash, CR Receivable
    - When payment is allocated: DR Receivable, CR Income (or similar)

    Actually, the simpler approach:
    - Payment confirmation = Cash in, Receivable down
    - Allocation = we just mark the payment as allocated (update Invoice.paid_sar)

    Let me simplify: allocation is just a status change, not a journal entry.
    The journal entry already happened at confirmation.
    """
    if payment.status != PaymentRecord.STATUS_CONFIRMED:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} harus confirmed dulu"
        )

    # Update invoice paid_sar
    old_state = _payment_snapshot(payment)
    invoice = payment.invoice
    invoice.paid_sar += payment.amount_sar
    invoice.save(update_fields=['paid_sar'])

    # Update invoice status
    if invoice.paid_sar >= invoice.total_sar:
        invoice.status = Invoice.STATUS_PAID
    elif invoice.paid_sar > 0:
        invoice.status = Invoice.STATUS_PARTIAL
    invoice.save(update_fields=['status'])

    # Update payment status
    payment.status = PaymentRecord.STATUS_ALLOCATED
    payment.save(update_fields=['status'])

    # Create log
    PaymentLog.objects.create(
        payment=payment,
        action=PaymentLog.ACTION_ALLOCATED,
        before_state=old_state,
        after_state=_payment_snapshot(payment),
        performed_by=created_by,
        note=note or f'Allocated to invoice {invoice.invoice_number}',
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


def client_balance(client):
    """Calculate client's current balance from journal entries.

    Positive = client owes us (receivable)
    Negative = we owe client (prepaid/credit)
    """
    from django.db.models import Sum

    # Get all journal lines for this client
    lines = JournalLine.objects.filter(client=client)

    # Sum by account type
    receivable = lines.filter(
        account=Account.RECEIVABLE
    ).aggregate(total=Sum('amount_sar'))['total'] or 0

    return receivable


def invoice_paid_sar_jl(invoice_id):
    """Calculate how much has been paid toward an invoice (from journal lines)."""
    from django.db.models import Sum

    return JournalLine.objects.filter(
        invoice_id=invoice_id,
        account=Account.RECEIVABLE,
        amount_sar__lt=0,  # Credit = payment received
    ).aggregate(total=Sum('amount_sar'))['total'] or 0


def kas_saldo(account, company=None):
    """Calculate cash balance for an account from journal lines."""
    from django.db.models import Sum

    qs = JournalLine.objects.filter(account=account)
    if company:
        qs = qs.filter(journal_entry__company=company)

    return qs.aggregate(total=Sum('amount_sar'))['total'] or 0


def client_statement(client, date_from=None, date_to=None):
    """Generate a client statement from JournalLines.

    Returns a list of transactions sorted by date with running balance.
    Positive balance = client owes us (receivable).
    Negative balance = we owe client (prepaid/credit).
    """
    lines = JournalLine.objects.filter(
        client=client,
    ).select_related('journal_entry').order_by('journal_entry__entry_date', 'journal_entry__created_at')

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
            'account': line.account,
            'account_display': line.get_account_display(),
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
    """Summary of all accounts from JournalLines."""
    from django.db.models import Sum

    qs = JournalLine.objects.all()
    if company:
        qs = qs.filter(journal_entry__company=company)

    summary = {}
    for account_choice in Account.choices:
        account_value = account_choice[0]
        account_label = account_choice[1]
        total = qs.filter(account=account_value).aggregate(total=Sum('amount_sar'))['total'] or 0
        if total != 0:
            summary[account_value] = {
                'label': account_label,
                'balance': total,
            }

    return summary
