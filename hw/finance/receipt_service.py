"""Receipt (Kwitansi) service — auto-generation from payments.

Setiap kali pembayaran menjadi efektif (uang benar-benar masuk, status dalam
PaymentRecord.EFFECTIVE_STATUSES), sebuah receipt otomatis dibuat. Ini
memastikan setiap pembayaran punya kwitansi tanpa langkah manual tambahan.
"""
from datetime import date


def _resolve_confirmation(payment):
    """Resolve ConfirmationLetter dari reservation payment atau alokasinya.

    Reservation pada PaymentRecord ber-nomor `reservation_number` yang sama
    dengan `confirmation_number` pada ConfirmationLetter (dalam company sama).
    """
    from ..models import ConfirmationLetter

    cl_number = None
    reservation = getattr(payment, 'reservation', None)
    if reservation is not None and reservation.reservation_number:
        cl_number = reservation.reservation_number
    if not cl_number:
        alloc = payment.allocations.select_related('reservation').first()
        if alloc and alloc.reservation_id and alloc.reservation:
            cl_number = alloc.reservation.reservation_number
    if not cl_number:
        return None

    return ConfirmationLetter.objects.filter(
        company=payment.company, confirmation_number=cl_number,
    ).first()


def ensure_receipt(payment, created_by=None):
    """Buat receipt untuk `payment` bila belum ada yang aktif.

    Idempotent: satu payment hanya punya satu Receipt aktif. Dipanggil setiap
    kali pembayaran masuk ke status efektif (receive/confirm/allocated/apply).
    Mengembalikan Receipt yang aktif (baru atau yang sudah ada), atau None bila
    data yang dibutuhkan kurang.
    """
    from ..models import Receipt

    existing = Receipt.objects.filter(
        payment=payment, status=Receipt.STATUS_ACTIVE,
    ).first()
    if existing:
        return existing

    invoice = payment.invoice
    client = payment.client
    if invoice is None or client is None:
        return None

    confirmation = _resolve_confirmation(payment)

    return Receipt.objects.create(
        receipt_number=Receipt.generate_number(),
        receipt_date=payment.payment_date or date.today(),
        company=payment.company,
        payment=payment,
        invoice=invoice,
        client=client,
        confirmation_letter=confirmation,
        amount_sar=payment.amount_sar,
        payment_method=payment.method or 'Cash',
        payment_note=payment.note,
        created_by=created_by or payment.created_by,
    )
