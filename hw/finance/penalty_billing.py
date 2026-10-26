"""Denda pembatalan ditagih lewat invoice (aturan bisnis B14).

Denda bukan piutang yang berdiri sendiri. Begitu ditetapkan, ia menjadi satu
baris di invoice hotel yang menagih reservasinya; bila reservasi itu belum
punya invoice, invoice-nya diterbitkan saat itu juga. Tagihannya mengikuti
dimensi reservasi yang sama, jadi uang yang sudah diterima untuk reservasi itu
menutup denda lebih dulu, dan sisanya menjadi kelebihan bayar.
"""
from django.db import transaction
from django.utils import timezone

from ..models.invoice import Invoice, InvoiceLine, InvoiceRevision
from . import queries
from .posting import post_invoice_charge


def _remove_penalty_lines(penalty, *, keep_invoice=None):
    """Lepas baris denda yang masih berlaku (kecuali di `keep_invoice`).
    Baris yang sudah dirujuk jurnal atau nota kredit di-void, selain itu dihapus.
    Mengembalikan invoice-invoice yang berubah."""
    from ..models.journal import JournalLine

    touched = []
    lines = InvoiceLine.objects.filter(kind=InvoiceLine.KIND_PENALTY, penalty=penalty, voided_at__isnull=True)
    if keep_invoice is not None:
        lines = lines.exclude(invoice=keep_invoice)
    for line in lines.select_related('invoice'):
        referenced = (
            JournalLine.objects.filter(invoice_id=line.invoice_id, penalty_id=penalty.pk).exists()
            or line.credit_note_lines.exists()
        )
        if referenced:
            line.void()
        else:
            line.delete()
        touched.append(line.invoice)
    return touched


@transaction.atomic
def bill_penalty(penalty, *, user=None):
    """Pastikan denda ditagih di invoice reservasinya, lalu sesuaikan jurnal.

    Mengembalikan (invoice, created): `created` True bila invoice-nya baru
    diterbitkan karena reservasi itu belum ditagih di mana pun."""
    cl = penalty.cl
    hotel_line = cl.invoice_line
    created = hotel_line is None
    if created:
        invoice = Invoice.objects.create(
            invoice_type='hotel', invoice_number=Invoice.generate_number('hotel'),
            client_id=cl.client_id, branch_id=cl.client.owner_branch_id,
            issued_date=penalty.cancellation_date or timezone.localdate(),
            currency='SAR', created_by=user,
        )
        invoice.add_hotel_line(cl)   # menambahkan baris dendanya juga
    else:
        invoice = hotel_line.invoice
        invoice.add_penalty_line(penalty)
    for other in _remove_penalty_lines(penalty, keep_invoice=invoice):
        post_invoice_charge(other, created_by=user, reason=InvoiceRevision.REASON_LINE_CHANGE)
    post_invoice_charge(invoice, created_by=user, reason=None if created else InvoiceRevision.REASON_LINE_CHANGE)
    return invoice, created


@transaction.atomic
def unbill_penalty(penalty, *, user=None):
    """Berhenti menagih denda (dipanggil sebelum dokumen dendanya dihapus)."""
    for invoice in _remove_penalty_lines(penalty):
        post_invoice_charge(invoice, created_by=user, reason=InvoiceRevision.REASON_LINE_CHANGE)


def reservation_balances(invoice, *, credited=None, paid_map=None):
    """{pk baris hotel: angka reservasi itu di invoice ini}.

    Satu reservasi = baris hotelnya + baris dendanya (bila ada). Uang yang
    diterima untuk reservasi itu menutup denda lebih dulu, baru nilai
    hotelnya; `remaining` negatif berarti kelebihan bayar. `credited` dan
    `paid_map` boleh diisi pemanggil yang sudah menghitungnya massal
    (credit_note_service._credited_by_lines, queries.reservation_paid_maps).
    """
    from .credit_note_service import _credited_by_line, _line_key

    lines = invoice.billed_lines()
    if invoice.is_void:
        credited = {_line_key(line): int(line.amount or 0) for line in lines}
    elif credited is None:
        credited = _credited_by_line(invoice)
    if paid_map is None:
        paid_map = queries.reservation_paid_map(invoice.pk)
    penalty_by_cl = {
        line.penalty.cl_id: line for line in lines if line.kind == InvoiceLine.KIND_PENALTY
    }
    out = {}
    for line in lines:
        if line.kind != InvoiceLine.KIND_HOTEL:
            continue
        pen_line = penalty_by_cl.get(line.confirmation_letter_id)
        hotel_amount = int(line.amount or 0)
        hotel_credited = credited.get(_line_key(line), 0)
        penalty_amount = int(pen_line.amount or 0) if pen_line else 0
        penalty_credited = credited.get(_line_key(pen_line), 0) if pen_line else 0
        paid = paid_map.get(line.pk, 0)
        penalty_due = max(penalty_amount - penalty_credited, 0)
        penalty_paid = min(max(paid, 0), penalty_due)
        out[line.pk] = {
            'line': line,
            'penalty_line': pen_line,
            'hotel_amount': hotel_amount,
            'penalty_amount': penalty_amount,
            'penalty_due': penalty_due,
            'total': hotel_amount + penalty_amount,
            'credited': hotel_credited + penalty_credited,
            'paid': paid,
            'penalty_paid': penalty_paid,
            'remaining': hotel_amount + penalty_amount - hotel_credited - penalty_credited - paid,
        }
    return out


def penalty_state(penalty):
    """{'invoice', 'due', 'paid', 'is_paid', 'paid_on'} untuk satu denda."""
    unbilled = {'invoice': None, 'due': int(penalty.penalty_amount), 'paid': 0, 'is_paid': False, 'paid_on': None}
    line = penalty.invoice_line
    if line is None:
        return unbilled
    invoice = line.invoice
    row = next(
        (r for r in reservation_balances(invoice).values() if r['penalty_line'] and r['penalty_line'].pk == line.pk),
        None,
    )
    if row is None:
        return {**unbilled, 'invoice': invoice}
    due, paid = row['penalty_due'], row['penalty_paid']
    is_paid = paid >= due
    paid_on = queries.line_last_settled_date(row['line'].pk) if is_paid and due > 0 else None
    return {'invoice': invoice, 'due': due, 'paid': paid, 'is_paid': is_paid, 'paid_on': paid_on}
