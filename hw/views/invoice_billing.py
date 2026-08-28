import json
import logging
from datetime import datetime

from django.db import transaction

from ..models import ConfirmationLetter, Payment, Invoice, InvoiceType
from ..finance.posting import reverse_invoice_payments, post_payment
from ..finance_helpers import create_payment_record
from .helpers import validate_proof_file, _parse_date, _to_float

logger = logging.getLogger(__name__)


def _save_payments(invoice, request, default_currency):
    """Create Payment objects from a JSON `payments` array (one object per row),
    and in parallel build the matching ledger rows (CashMovement + Allocation).

    Each row: {ref, date, method, amount, currency, exchange, note, proof_keep}.
    New proof uploads arrive as multipart files keyed `payment_proof_<index>`,
    where <index> is the row's position in the array. Sets cl FK when ref
    matches a CL number.

    Dual-write (remittance ledger redesign, Fase 4): callers do a full
    delete-then-recreate of `invoice.payments` on every edit (the payments
    array has no row identity to diff against), so we mirror the same
    full-resync for the ledger side. The deletes below are scoped to exactly
    what this function itself ever creates -- CLIENT-origin movements for
    this invoice, and their `initial` allocations -- so remittance transfers
    (SBY->PUSAT), refunds, transfers, and corrections from later phases are
    never touched by a payment-list save.
    """
    try:
        rows = json.loads(request.POST.get('payments', '[]'))
    except (ValueError, TypeError):
        rows = []

    # Pre-fetch CLs that match any of the ref numbers (one query instead of N)
    ref_set = {(r.get('ref') or '').strip() for r in rows if (r.get('ref') or '').strip()}
    cl_by_number = {
        cl.confirmation_number: cl
        for cl in ConfirmationLetter.objects.filter(confirmation_number__in=ref_set)
    } if ref_set else {}

    with transaction.atomic():
        # Full delete-recreate daftar pembayaran: reverse dulu semua journal
        # payment untuk invoice ini, lalu re-post dari baris baru.
        reverse_invoice_payments(invoice, created_by=request.user)

        client = _billing_client(invoice)
        is_hotel = invoice.invoice_type == InvoiceType.HOTEL
        reservations_by_number = {r.reservation_number: r for r in invoice.reservations.all()} if is_hotel else {}
        service_items_by_number = {} if is_hotel else {s.service_number: s for s in invoice.service_items.all()}

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

            # ── Legacy: keep old Payment for backward compat ──────
            p = Payment.objects.create(
                invoice=invoice,
                cl=cl_by_number.get(ref_clean),
                linked_number=ref_clean,
                payment_date=payment_date,
                method=method,
                amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
                note=(r.get('note') or '').strip(),
                proof=proof or keep or None,
            )

            if not amount:
                continue

            reservation = reservations_by_number.get(ref_clean)
            service_item = None
            if reservation is None and not is_hotel:
                try:
                    service_item = service_items_by_number.get(int(ref_clean))
                except (ValueError, TypeError):
                    service_item = None

            if client is None:
                continue  # tak bisa posting jurnal tanpa client — Payment legacy tetap tercatat
            method_l = (method or '').lower()
            received_in = 'pusat' if method_l == 'direct' else 'sby'
            pr = create_payment_record(
                invoice=invoice, client=client,
                payment_date=payment_date or invoice.issued_date or datetime.now().date(),
                amount=int(round(amount)), currency=currency, exchange_rate=exchange_rate,
                method=method, reference='invoice-form',
                note=f'Sinkron dari pembayaran invoice {invoice.invoice_number}',
                created_by=request.user, reservation=reservation, service_item=service_item,
                received_in=received_in,
            )
            post_payment(pr, created_by=request.user)
            pr.status = pr.STATUS_ALLOCATED
            pr.save(update_fields=['status'])

    invoice.sync_status()

    logger.info(
        "ledger: %d payment(s) synced for invoice %s",
        len(rows), invoice.invoice_number,
    )


def _save_hotel_payments(invoice, request):
    _save_payments(invoice, request, 'SAR')


def _save_service_payments(invoice, request):
    _save_payments(invoice, request, invoice.currency)


def _billing_client(invoice):
    """Client efektif untuk kirim billing: client tunggal dari CL-CL yang
    terhubung ke invoice. Lebih dari satu client berbeda = ambigu — fallback
    ke invoice.client yang dipilih user di form."""
    clients = {
        cl.client_id: cl.client
        for cl in invoice.confirmation_letters.select_related('client')
        if cl.client_id
    }
    if len(clients) == 1:
        return next(iter(clients.values()))
    if len(clients) > 1:
        return None
    # No CLs or CLs have no client — fall back to invoice.client
    return invoice.client


def _billing_props(invoice):
    """Shared Inertia props for the billing-message WA send feature."""
    client = _billing_client(invoice)
    last = invoice.billing_logs.order_by('-sent_at').first()
    return {
        'wa_send': {
            'client_name': client.name if client else None,
            'client_wa': client.wa if client else '',
            'has_wa': bool(client and client.wa),
            'has_group': bool(client and client.wa_group),
        },
        'last_billing': {
            'sent_at': last.sent_at.strftime('%d %b %Y %H:%M'),
            'target': last.target,
            'status': last.status,
        } if last else None,
    }
