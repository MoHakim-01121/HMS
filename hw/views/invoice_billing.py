import json
import logging
from datetime import datetime

from django.db import transaction

from ..models import InvoiceType
from ..finance.posting import reverse_invoice_payments, post_payment
from ..finance_helpers import create_payment_record
from .helpers import validate_proof_file, _parse_date, _to_float

logger = logging.getLogger(__name__)


def _save_payments(invoice, request, default_currency):
    """Re-post the journal payment legs from a JSON `payments` array (one object
    per row) — PaymentRecord + journal are the only stores written.

    Each row: {ref, date, method, amount, currency, exchange, note, proof_keep}.
    New proof uploads arrive as multipart files keyed `payment_proof_<index>`,
    where <index> is the row's position in the array.

    Full-resync (Fase 4+): the payments array has no row identity to diff
    against, so each save reverses this invoice's live payment entries and
    re-posts from the new rows. The reversal is scoped to exactly what this
    function itself ever creates -- payment entries for this invoice -- so
    remittance sends, refunds, transfers, and penalty entries are never touched
    by a payment-list save.
    """
    # A missing `payments` key is not an empty payment list. Invoice/Form.jsx
    # and Services/Form.jsx render payments read-only -- they are recorded
    # through the Payment module, so those forms never submit the field.
    # Reading the absent key as '[]' made every unrelated save (fixing a due
    # date, say) run the full resync below: reverse_invoice_payments reversed
    # this invoice's live payment entries and flipped the PaymentRecords to
    # REVERSED, with nothing re-posted. Only an explicitly submitted list --
    # empty or not -- is a resync instruction.
    if 'payments' not in request.POST:
        return

    try:
        rows = json.loads(request.POST.get('payments', '[]'))
    except (ValueError, TypeError):
        rows = []

    with transaction.atomic():
        # Full delete-recreate daftar pembayaran: reverse dulu semua journal
        # payment untuk invoice ini, lalu re-post dari baris baru.
        #
        # Tanggal reversal = tanggal pembayaran baru TERAWAL (bukan "hari ini"
        # default) supaya reversal + repost selalu jatuh di periode yang sama.
        # Kalau tanggal itu berada di periode terkunci, reverse_entry melempar
        # PeriodLockedError → seluruh blok rollback → pesan error jelas ke user,
        # tidak ada mutasi parsial (sebelumnya reversal tercatat di periode
        # berbeda dari repost, mengotori ledger walau posting akhirnya gagal).
        new_rows = [r for r in rows if _to_float(r.get('amount'))]
        rev_date = None
        if new_rows:
            dates = [
                _parse_date(r.get('date')) or invoice.issued_date or datetime.now().date()
                for r in new_rows
            ]
            rev_date = min(dates)
        reverse_invoice_payments(
            invoice, created_by=request.user, entry_date=rev_date,
        )

        client = invoice.client
        is_hotel = invoice.invoice_type == InvoiceType.HOTEL
        reservations_by_number = {r.reservation_number: r for r in invoice.reservations} if is_hotel else {}
        service_items_by_number = {} if is_hotel else {s.service_number: s for s in invoice.service_items}

        for i, r in enumerate(rows):
            proof = request.FILES.get(f"payment_proof_{i}")
            if proof:
                error = validate_proof_file(proof)
                if error:
                    raise ValueError(f"Payment proof #{i + 1}: {error}")
            keep  = (r.get('proof_keep') or '').strip()
            ref_clean = (r.get('ref') or '').strip()
            currency = (r.get('currency') or default_currency)
            currency = currency.upper() if currency else default_currency
            exchange_rate = _to_float(r.get('exchange'), 1) or 1
            amount = _to_float(r.get('amount'))
            method = (r.get('method') or '').strip()
            payment_date = _parse_date(r.get('date'))

            if not amount:
                continue

            reservation = reservations_by_number.get(ref_clean)
            service_item = None
            if reservation is None and not is_hotel:
                try:
                    service_item = service_items_by_number.get(int(ref_clean))
                except (ValueError, TypeError):
                    service_item = None

            method_l = (method or '').lower()
            received_in = 'pusat' if method_l == 'direct' else 'sby'
            pr = create_payment_record(
                invoice=invoice, client=client,
                payment_date=payment_date or invoice.issued_date or datetime.now().date(),
                amount=int(round(amount)), currency=currency, exchange_rate=exchange_rate,
                method=method, reference='invoice-form',
                note=f'Sinkron dari pembayaran invoice {invoice.invoice_number}',
                created_by=request.user, reservation=reservation, service_item=service_item,
                received_in=received_in, proof=proof or keep or None,
            )
            post_payment(pr, created_by=request.user)
            pr.status = pr.STATUS_ALLOCATED
            pr.save(update_fields=['status'])

    logger.info(
        "ledger: %d payment(s) synced for invoice %s",
        len(rows), invoice.invoice_number,
    )


def _save_hotel_payments(invoice, request):
    _save_payments(invoice, request, 'SAR')


def _save_service_payments(invoice, request):
    _save_payments(invoice, request, invoice.currency)


def _billing_client(invoice):
    """Client yang ditagih invoice ini. Satu invoice satu client, dan setiap
    reservasi di dalamnya milik client itu (dijaga skema), jadi tidak ada lagi
    yang perlu ditebak dari CL-nya."""
    return invoice.client


def _billing_props(invoice):
    """Shared Inertia props for the billing-message generator. The client's WA
    number (when known) feeds the wa.me deep link in the draft modal."""
    client = _billing_client(invoice)
    return {
        'wa_send': {
            'client_name': client.name if client else None,
            'client_wa': client.wa if client else '',
            'has_wa': bool(client and client.wa),
            'has_group': bool(client and client.wa_group),
        },
    }
