"""Receipt (Kwitansi) service — auto-generation from payments.

Setiap kali pembayaran menjadi efektif (uang benar-benar masuk, status dalam
PaymentRecord.EFFECTIVE_STATUSES), sebuah receipt otomatis dibuat. Ini
memastikan setiap pembayaran punya kwitansi tanpa langkah manual tambahan.
"""

from django.db import transaction
from django.utils import timezone


def _resolve_confirmation(payment):
    """Reservasi (CL) yang dibayar payment ini: dari baris invoice hotel yang
    pada alokasi pertamanya."""
    alloc = payment.allocations.filter(invoice_line__kind='hotel').select_related(
        'invoice_line__confirmation_letter',
    ).order_by('pk').first()
    return alloc.invoice_line.confirmation_letter if alloc else None


def void_receipts_for_payment(payment, *, reason):
    """Void every active Receipt attesting to `payment`. Returns the count.

    A receipt is evidence that money was received. Once the payment's journal
    has been reversed that evidence must stop printing as ACTIVE -- otherwise
    /receipt/<pk>/pdf/ keeps issuing a full-value, apparently-valid kwitansi
    for money that has left the ledger.

    Void, never delete: the receipt number stays in sequence so the audit
    trail has no unexplained gap, and `voided_reason` records why.
    """
    from ..models import Receipt

    return Receipt.objects.filter(
        payment=payment, status=Receipt.STATUS_ACTIVE,
    ).update(status=Receipt.STATUS_VOIDED, voided_reason=reason)


@transaction.atomic
def ensure_receipt(payment, created_by=None):
    """Buat receipt untuk `payment` bila belum ada yang aktif.

    Idempotent: satu payment hanya punya satu Receipt aktif. Dipanggil setiap
    kali pembayaran masuk ke status efektif (receive/confirm/allocated/apply).
    Mengembalikan Receipt yang aktif (baru atau yang sudah ada).

    Pembayaran tanpa invoice (deposit) juga mendapat kwitansi: `invoice` dibuat
    None, dan PDF menampilkan tanpa blok invoice serta tanpa rincian alokasi
    selama belum didistribusikan.
    """
    from ..models import Receipt

    existing = Receipt.objects.filter(
        payment=payment, status=Receipt.STATUS_ACTIVE,
    ).first()
    if existing:
        return existing

    confirmation = _resolve_confirmation(payment)

    return Receipt.objects.create(
        receipt_number=Receipt.generate_number(),
        receipt_date=payment.payment_date or timezone.localdate(),
        payment=payment,
        invoice=payment.invoice,
        client=payment.client,
        confirmation_letter=confirmation,
        amount_sar=payment.amount_sar,
        payment_method=payment.method or 'Cash',
        payment_note=payment.note,
        created_by=created_by or payment.created_by,
    )
