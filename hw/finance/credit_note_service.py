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

from ..models.credit_note import CreditNote, CreditNoteLine
from ..models.invoice import Invoice, InvoiceLine, InvoiceRevision
from ..models.journal import JournalEntry
from ..models.payment import PaymentRecord
from . import accounts as coa
from . import invoice_revisions, queries
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
    released = list(invoice.confirmation_letters.values_list('confirmation_number', flat=True))
    # Potret baris SEBELUM di-void: nilai baris yang sudah void dibaca dari sini.
    billed = invoice_revisions.snapshot(invoice)
    now = timezone.now()
    # Baris ikut di-void dengan cap waktu yang sama: reservasinya bebas ditagih
    # lagi, dan invoice void tetap bisa menunjukkan apa yang dulu ditagihnya.
    invoice.lines.filter(voided_at__isnull=True).update(voided_at=now)
    invoice.status = Invoice.STATUS_VOID
    invoice.void_reason = reason
    invoice.voided_at = now
    invoice.voided_by = created_by
    invoice.save(update_fields=['status', 'void_reason', 'voided_at', 'voided_by'])
    invoice_revisions.record(invoice, reason=InvoiceRevision.REASON_VOID, user=created_by, lines=billed)
    return released


# ── Credit notes ───────────────────────────────────────────────────────

def _income_account(invoice):
    return coa.INC_HOTEL


_KEY_BY_KIND = {InvoiceLine.KIND_HOTEL: 'r', InvoiceLine.KIND_PENALTY: 'p'}
_FORM_KIND = {InvoiceLine.KIND_HOTEL: 'reservation', InvoiceLine.KIND_PENALTY: 'penalty'}


def _line_key(line):
    """('r', pk) for a hotel line, ('p', pk) for a penalty line."""
    return (_KEY_BY_KIND[line.kind], line.pk)


def _credited_by_line(invoice):
    """{('r' | 'p', pk): SAR already credited by active credit notes}."""
    out = {}
    for cn_line in CreditNoteLine.objects.filter(
        credit_note__invoice=invoice, credit_note__status=CreditNote.STATUS_ACTIVE,
    ).select_related('invoice_line'):
        key = _line_key(cn_line.invoice_line)
        out[key] = out.get(key, 0) + cn_line.amount_sar
    return out


def _credited_by_lines(invoice_ids):
    """Bulk _credited_by_line: {invoice_id: {('r' | 'p', pk): SAR}}."""
    out = {pk: {} for pk in invoice_ids}
    for cn_line in CreditNoteLine.objects.filter(
        credit_note__invoice_id__in=invoice_ids, credit_note__status=CreditNote.STATUS_ACTIVE,
    ).select_related('invoice_line', 'credit_note'):
        credited = out[cn_line.credit_note.invoice_id]
        key = _line_key(cn_line.invoice_line)
        credited[key] = credited.get(key, 0) + cn_line.amount_sar
    return out


def creditable_lines(invoice):
    """What each line of the invoice may still be credited: its billed amount
    minus active credit notes on it."""
    credited = _credited_by_line(invoice)
    rows = []
    for line in sorted(invoice.billed_lines(), key=lambda l: (l.kind != InvoiceLine.KIND_HOTEL, l.pk)):
        key = _line_key(line)
        billed = int(line.amount or 0)
        rows.append({
            'kind': _FORM_KIND[line.kind], 'id': line.pk,
            'label': line.label,
            'billed': billed, 'credited': credited.get(key, 0),
            'available': max(billed - credited.get(key, 0), 0),
        })
    return rows


@transaction.atomic
def issue_credit_note(invoice, *, lines, reason, issued_date, created_by):
    """lines: [{'kind': 'reservation'|'penalty', 'id': pk, 'amount_sar': int}].
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
    hotel_by_cl = {
        l.confirmation_letter_id: l.pk for l in invoice.billed_lines() if l.kind == InvoiceLine.KIND_HOTEL
    }
    journal = []
    ar_room = total - to_deposit
    for row, amount in picked:
        dims = {'invoice': invoice.pk}
        line_income = income
        if row['kind'] == 'reservation':
            dims['invoice_line'] = row['id']
            branch = coa.HQ_BRANCH if income == coa.INC_HOTEL else invoice.branch_id
        elif row['kind'] == 'penalty':
            # Same dimensions as the penalty charge: the reservation's line, revenue at HQ.
            pen_line = InvoiceLine.objects.select_related('penalty').get(pk=row['id'])
            dims['invoice_line'] = hotel_by_cl.get(pen_line.penalty.cl_id)
            dims['penalty'] = pen_line.penalty_id
            branch = coa.HQ_BRANCH
            line_income = coa.INC_PENALTY
        else:
            dims['invoice_line'] = row['id']
            branch = None
        CreditNoteLine.objects.create(
            credit_note=cn, invoice_line_id=row['id'], description=row['label'], amount_sar=amount,
        )
        journal.append({'account': line_income, 'debit': amount, 'branch': branch, **dims})
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
    invoice_revisions.record(invoice, reason=InvoiceRevision.REASON_CREDIT_NOTE, user=created_by)
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
    invoice_revisions.record(cn.invoice, reason=InvoiceRevision.REASON_CREDIT_NOTE, user=created_by)
    return cn
