"""Void invoice and credit notes (Nota Kredit) — see hw/models/credit_note.py.

Void: an invoice nobody has paid on is cancelled whole — its charge is
reversed, status becomes void, the number stays (no gap), and its CLs are
released so they can be billed again.

Credit note: an invoice that stays valid but bills too much is reduced by a
numbered document. Dr Pendapatan (same account and branch dimension as the
charge) / Cr Piutang up to what the invoice still has open; anything beyond
that was already paid, so it becomes client deposit (Cr Titipan).
"""
from django.db import transaction
from django.utils import timezone

from ..models.choices import InvoiceType
from ..models.credit_note import CreditNote, CreditNoteLine
from ..models.invoice import Invoice
from ..models.journal import JournalEntry
from ..models.payment import PaymentRecord
from . import accounts as coa
from . import queries
from .errors import FinanceError
from .posting import _live_entries, post_entry, reverse_entry, void_invoice_charge

# Payments that still count, or may still come to count, against an invoice.
_OPEN_PAYMENT_STATUSES = (*PaymentRecord.EFFECTIVE_STATUSES, PaymentRecord.STATUS_PENDING)


def void_blockers(invoice):
    """Reasons this invoice cannot be voided (empty list = it can)."""
    out = []
    if invoice.status == Invoice.STATUS_VOID:
        out.append('Invoice sudah void.')
    if invoice.payment_records.filter(status__in=_OPEN_PAYMENT_STATUSES).exists():
        out.append('Masih ada pembayaran di invoice ini. Batalkan pembayarannya, atau buat nota kredit.')
    elif queries.invoice_paid_sar(invoice.pk):
        out.append('Invoice ini sudah menerima uang. Buat nota kredit sebagai gantinya.')
    if invoice.credit_notes.filter(status=CreditNote.STATUS_ACTIVE).exists():
        out.append('Batalkan dulu nota kredit yang masih berlaku.')
    return out


@transaction.atomic
def void_invoice(invoice, *, reason, created_by, void_date=None):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    reason = (reason or '').strip()
    if not reason:
        raise FinanceError('Alasan void wajib diisi.')
    blockers = void_blockers(invoice)
    if blockers:
        raise FinanceError(blockers[0])
    void_invoice_charge(invoice, created_by=created_by, entry_date=void_date or timezone.now().date())
    from ..models.confirmation import ConfirmationLetter
    released = list(ConfirmationLetter.objects.filter(invoice=invoice).values_list('confirmation_number', flat=True))
    ConfirmationLetter.objects.filter(invoice=invoice).update(invoice=None)
    invoice.status = Invoice.STATUS_VOID
    invoice.void_reason = reason
    invoice.voided_at = timezone.now()
    invoice.voided_by = created_by
    invoice.save(update_fields=['status', 'void_reason', 'voided_at', 'voided_by'])
    return released


# ── Credit notes ───────────────────────────────────────────────────────

def _income_account(invoice):
    return coa.INC_HOTEL if invoice.invoice_type == InvoiceType.HOTEL else coa.INC_SERVICE


def _credited_by_line(invoice):
    """{('r', pk) | ('s', pk): SAR already credited by active credit notes}."""
    out = {}
    for line in CreditNoteLine.objects.filter(
        credit_note__invoice=invoice, credit_note__status=CreditNote.STATUS_ACTIVE,
    ):
        key = ('r', line.reservation_id) if line.reservation_id else ('s', line.service_item_id)
        out[key] = out.get(key, 0) + line.amount_sar
    return out


def creditable_lines(invoice):
    """What each reservation / service line of the invoice may still be
    credited: its billed amount minus active credit notes on it."""
    credited = _credited_by_line(invoice)
    rows = []
    for r in invoice.reservations.all().order_by('pk'):
        billed = int(r.total_sar or 0)
        rows.append({
            'kind': 'reservation', 'id': r.pk,
            'label': f'{r.reservation_number} · {r.hotel}'.strip(' ·'),
            'billed': billed, 'credited': credited.get(('r', r.pk), 0),
            'available': max(billed - credited.get(('r', r.pk), 0), 0),
        })
    for s in invoice.service_items.all():
        billed = int(s.total or 0)
        rows.append({
            'kind': 'service', 'id': s.pk,
            'label': f'#{s.service_number} {s.name}',
            'billed': billed, 'credited': credited.get(('s', s.pk), 0),
            'available': max(billed - credited.get(('s', s.pk), 0), 0),
        })
    return rows


@transaction.atomic
def issue_credit_note(invoice, *, lines, reason, issued_date, created_by):
    """lines: [{'kind': 'reservation'|'service', 'id': pk, 'amount_sar': int}].
    Lines with amount 0 are ignored. Returns the CreditNote."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    reason = (reason or '').strip()
    if invoice.status == Invoice.STATUS_VOID:
        raise FinanceError('Invoice void tidak bisa diberi nota kredit.')
    if not invoice.client_id:
        raise FinanceError('Invoice belum punya client.')
    if not reason:
        raise FinanceError('Alasan nota kredit wajib diisi.')
    if not issued_date:
        raise FinanceError('Tanggal nota kredit wajib diisi.')

    available = {(row['kind'], row['id']): row for row in creditable_lines(invoice)}
    picked = []
    for spec in lines:
        try:
            amount = int(spec.get('amount_sar') or 0)
        except (TypeError, ValueError):
            raise FinanceError('Nominal nota kredit tidak valid.') from None
        if amount == 0:
            continue
        row = available.get((spec.get('kind'), int(spec.get('id') or 0)))
        if row is None:
            raise FinanceError('Baris nota kredit bukan milik invoice ini.')
        if amount < 0 or amount > row['available']:
            raise FinanceError(f"{row['label']}: maksimal {row['available']:,} SAR yang masih bisa dikreditkan.")
        picked.append((row, amount))
    if not picked:
        raise FinanceError('Isi nominal minimal satu baris.')

    total = sum(a for _r, a in picked)
    open_ar = max(queries.invoice_outstanding_sar(invoice.pk), 0)
    to_deposit = max(total - open_ar, 0)

    cn = CreditNote.objects.create(
        credit_note_number=CreditNote.generate_number(issued_date), invoice=invoice,
        client_id=invoice.client_id, issued_date=issued_date, reason=reason,
        to_deposit_sar=to_deposit, created_by=created_by,
    )
    income = _income_account(invoice)
    journal = []
    ar_room = total - to_deposit
    for row, amount in picked:
        dims = {'invoice': invoice.pk}
        if row['kind'] == 'reservation':
            res = invoice.reservations.get(pk=row['id'])
            dims['reservation'] = res.pk
            branch = coa.HQ_BRANCH if income == coa.INC_HOTEL else res.owner_branch_id
            CreditNoteLine.objects.create(credit_note=cn, reservation=res, description=row['label'], amount_sar=amount)
        else:
            dims['service_item'] = row['id']
            branch = None
            CreditNoteLine.objects.create(credit_note=cn, service_item_id=row['id'], description=row['label'], amount_sar=amount)
        journal.append({'account': income, 'debit': amount, 'branch': branch, **dims})
        to_ar = min(amount, ar_room)
        ar_room -= to_ar
        if to_ar:
            journal.append({'account': coa.AR, 'credit': to_ar, 'client': invoice.client_id, **dims})
    if to_deposit:
        journal.append({'account': coa.CUST_CREDIT, 'credit': to_deposit, 'client': invoice.client_id,
                        'invoice': invoice.pk})
    post_entry(
        entry_type=JournalEntry.TYPE_CREDIT_NOTE,
        description=f'Credit note {cn.credit_note_number} for {invoice.invoice_number}',
        entry_date=issued_date, lines=journal,
        source_type='CreditNote', source_id=cn.pk, created_by=created_by,
    )
    invoice.sync_status()
    return cn


@transaction.atomic
def void_credit_note(cn, *, reason, created_by, void_date=None):
    cn = CreditNote.objects.select_for_update().get(pk=cn.pk)
    reason = (reason or '').strip()
    if cn.status == CreditNote.STATUS_VOIDED:
        raise FinanceError(f'{cn.credit_note_number} sudah dibatalkan.')
    if not reason:
        raise FinanceError('Alasan pembatalan wajib diisi.')
    if cn.to_deposit_sar and queries.client_credit_balance(cn.client_id) < cn.to_deposit_sar:
        raise FinanceError(
            f'{cn.to_deposit_sar:,} SAR dari nota kredit ini masuk ke titipan client dan sebagian '
            'sudah dipakai (refund/transfer). Tidak bisa dibatalkan.'
        )
    for e in _live_entries('CreditNote', cn.pk, JournalEntry.TYPE_CREDIT_NOTE):
        reverse_entry(e, reversal_date=void_date or timezone.now().date(), created_by=created_by)
    cn.status = CreditNote.STATUS_VOIDED
    cn.voided_reason = reason
    cn.voided_by = created_by
    cn.voided_at = timezone.now()
    cn.save(update_fields=['status', 'voided_reason', 'voided_by', 'voided_at'])
    cn.invoice.sync_status()
    return cn
