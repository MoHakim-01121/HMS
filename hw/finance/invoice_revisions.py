"""Riwayat nilai tagihan invoice (InvoiceRevision).

CL sering berubah setelah invoice terbit, dan invoice mengikutinya. Setiap kali
yang ditagih invoice berubah, satu revisi dicatat: total yang harus dibayar
client setelah perubahan, dan nilai tiap baris saat itu. Revisi hanya
bertambah; nilai baris yang sudah di-void dibaca dari sini.
"""
from django.db import transaction
from django.db.models import Max

from ..models.invoice import Invoice, InvoiceRevision


def snapshot(invoice):
    """[{line_id, line_no, kind, label, amount}] untuk baris yang sedang ditagih."""
    return [
        {
            'line_id': line.pk, 'line_no': line.line_no, 'kind': line.kind,
            'label': line.label, 'amount': int(line.amount or 0),
        }
        for line in invoice.billed_lines()
    ]


@transaction.atomic
def record(invoice, *, reason=None, user=None, lines=None):
    """Catat keadaan invoice sekarang sebagai revisi baru.

    `lines` menimpa snapshot (dipakai saat void: baris dipotret SEBELUM
    di-void, sementara total yang dicatat sudah 0)."""
    # Kunci invoice-nya supaya dua perubahan bersamaan tidak berebut nomor revisi.
    Invoice.objects.select_for_update().filter(pk=invoice.pk).first()
    last = invoice.revisions.aggregate(m=Max('revision_no'))['m'] or 0
    if reason is None:
        reason = InvoiceRevision.REASON_ISSUE if last == 0 else InvoiceRevision.REASON_LINE_CHANGE
    invoice.__dict__.pop('_frozen_amounts', None)
    return InvoiceRevision.objects.create(
        invoice=invoice, revision_no=last + 1, reason=reason,
        total=int(invoice.due_sar), lines_snapshot=snapshot(invoice) if lines is None else lines,
        changed_by=user,
    )
