"""[COMPATIBILITY LAYER — DEPRECATED] Finance helpers lama.

File ini dulunya berisi campuran exception classes, period helpers, adapter
jurnal, logika lifecycle pembayaran, dan query helper. Saat merapikan, bagian-
bagian yang sudah punya rumah sendiri kini di-re-export dari lokasi tersebut:

- exception classes      → hw/finance/errors.py
- period helpers         → hw/finance/posting.py
- adapter jurnal         → hw/finance/posting.py (post_entry / reverse_entry)

Yang MASIH di sini (logika asli):
- lifecycle pembayaran   → create_payment_record / confirm_payment /
                           allocate_payment (lapisan manipulasi PaymentRecord)
- query helper kas_saldo / account_summary yang dipakai view (home, payment)

KERAS DIRENCANAKAN: kode baru panggil langsung dari hw/finance/*. Fungsi di
file ini dipertahankan agar import lama (view + test) tidak pecah.
"""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .finance.errors import (
    FinanceError, PeriodLockedError, JournalImbalanceError,
    PaymentAlreadyProcessedError, InsufficientAllocationError,
)
from .finance.posting import (
    get_current_period, get_period_for_date, check_period_postable,
)
from .models.payment import PaymentRecord, PaymentLog
from .models.journal import JournalEntry, JournalLine, LedgerAccount
from .finance.accounts import resolve_account_code, AR

__all__ = [
    # exceptions (re-exported)
    'FinanceError', 'PeriodLockedError', 'JournalImbalanceError',
    'PaymentAlreadyProcessedError', 'InsufficientAllocationError',
    # period helpers (re-exported)
    'get_current_period', 'get_period_for_date', 'check_period_postable',
    # adapters (delegates)
    'create_journal_entry', 'reverse_journal_entry',
    # payment lifecycle (original logic)
    'create_payment_record', 'confirm_payment', 'allocate_payment',
    # query helpers
    'client_balance', 'invoice_paid_sar_jl', 'kas_saldo',
    'client_statement', 'account_summary',
    # shared
    'LedgerAccount', 'JournalEntry', 'JournalLine',
]


def _account_obj(ref):
    """Terima kode v2, kode enum v1, atau instance LedgerAccount → LedgerAccount."""
    if isinstance(ref, LedgerAccount):
        return ref
    return LedgerAccount.objects.get(pk=resolve_account_code(str(ref)))


# ── Adapter jurnal (delegasi ke posting layer) ─────────────────


def create_journal_entry(
    entry_type,
    description,
    entry_date,
    lines,
    reference_type='',
    reference_id=None,
    created_by=None,
    is_reversal=False,
    reverses=None,
):
    """[DEPRECATED] Adapter lama — delegasi ke hw.finance.posting.post_entry.

    Dipakai penalty_views & test sampai dirombak ke posting layer.
    Kode baru panggil post_entry() langsung.
    """
    from .finance.posting import post_entry

    return post_entry(
        entry_type=entry_type,
        description=description,
        entry_date=entry_date,
        lines=lines,
        source_type=reference_type,
        source_id=reference_id,
        created_by=created_by,
        is_reversal=is_reversal,
        reverses=reverses,
    )


def reverse_journal_entry(original_entry, reversal_date, created_by, note=''):
    """[DEPRECATED] Adapter lama — delegasi ke hw.finance.posting.reverse_entry."""
    from .finance.posting import reverse_entry

    return reverse_entry(
        original_entry, reversal_date=reversal_date, created_by=created_by, note=note,
    )


# ── Payment lifecycle (logika asli PaymentRecord) ───────────────


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
    bank_account=None,
    cash_account=None,
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

    received_in = received_in if received_in in ('sby', 'jkt', 'pusat') else 'sby'
    # Kalau pemanggil tidak memberi rekening konkret, turunkan CashAccount
    # cabang dari received_in (v2.0 FASE C). Rekening bank riil harus eksplisit.
    if bank_account is None and cash_account is None:
        from .models import CashAccount
        cash_account = CashAccount.objects.filter(
            branch_id=received_in, is_active=True,
        ).order_by('id').first()

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
        received_in=received_in,
        bank_account=bank_account,
        cash_account=cash_account,
        method=method,
        bank_name=bank_name,
        account_number=account_number,
        reference=reference,
        note=note,
        proof=proof,
        status=PaymentRecord.STATUS_PENDING,
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

    # Lock the row and re-read its status: two confirms racing (double
    # click) must not both pass the pending check and post twice.
    payment.status = (
        PaymentRecord.objects.select_for_update()
        .values_list('status', flat=True).get(pk=payment.pk)
    )
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


# ── Query helpers (untuk kompatibilitas; prefer hw/finance/queries.py) ──


def _net(qs):
    agg = qs.aggregate(d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or 0) - (agg['c'] or 0)


def client_balance(client):
    """[DEPRECATED] Piutang client dari jurnal. Prefer finance.queries.client_receivable."""
    return _net(JournalLine.objects.filter(client=client, account_id=AR))


def invoice_paid_sar_jl(invoice_id):
    """[DEPRECATED] Total kredit Piutang untuk sebuah invoice (negatif).
    Prefer finance.queries.invoice_paid_sar / invoice_paid_map."""
    agg = JournalLine.objects.filter(
        invoice_id=invoice_id, account_id=AR, credit__gt=0,
    ).aggregate(c=Sum('credit'))
    return -(agg['c'] or 0)


def kas_saldo(account):
    """Saldo kas/akun (debit - credit) dari baris jurnal."""
    qs = JournalLine.objects.filter(account_id=resolve_account_code(str(account)))
    return _net(qs)


def client_statement(client, date_from=None, date_to=None):
    """[DEPRECATED] Statement klien dari jurnal. Prefer finance.queries.client_statement."""
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


def account_summary():
    """[DEPRECATED] Ringkasan semua akun dari jurnal. Prefer finance.queries
    (trial_balance / account_balance). Dipakai payment_views sementara."""
    qs = JournalLine.objects.all()

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
