import base64
import hashlib
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML

from ..utils import format_currency
from .context import _build_reservation_context


def _logo_file_url():
    filename = "LOGOKONOZ-02.png"
    mime = "image/png"
    path = Path(__file__).resolve().parent.parent / "static" / "hw" / "img" / filename
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _render_cl_pdf(cl):
    from django.core.cache import cache
    cache_key = f"pdf:cl:{cl.pk}:{cl.updated_at.isoformat()}"
    cached_pdf = cache.get(cache_key)
    if cached_pdf is not None:
        response = HttpResponse(cached_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{cl.confirmation_number}.pdf"'
        return response

    nights = cl.num_nights
    nights_factor = nights if nights > 0 else 1

    rooms = []
    for r in cl.rooms.all():
        rooms.append({
            "type": r.room_type,
            "meals": r.meals,
            "quantity": r.quantity,
            "price": float(r.price),
            "subtotal": float(r.price) * r.quantity * nights_factor,
        })

    context = {
        "hotel_name": cl.hotel_name,
        "guest_name": cl.guest_name,
        "guest_phone": cl.guest_phone,
        "num_guests": cl.num_guests,
        "check_in": datetime.combine(cl.check_in, datetime.min.time()) if cl.check_in else None,
        "check_out": datetime.combine(cl.check_out, datetime.min.time()) if cl.check_out else None,
        "num_nights": nights,
        "confirmation_number": cl.confirmation_number,
        "reservation_status": cl.reservation_status,
        "note": cl.note,
        "rooms": rooms,
        "total_rooms": cl.total_rooms,
        "total_price": cl.total_price,
        "logo_rel_path": _logo_file_url(),
    }

    html = render_to_string("hw/cl/cl_pdf_konoz.html", context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    cache.set(cache_key, pdf, 3600)
    filename = f"{cl.confirmation_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _stay_label(check_in, check_out):
    """'01 – 06 Dec 2026 (5N)' for one stay, collapsing what both dates share."""
    if not check_in and not check_out:
        return ''
    full = '%d %b %Y'
    if not (check_in and check_out):
        return (check_in or check_out).strftime(full)
    if check_in.year != check_out.year:
        start = full
    elif check_in.month != check_out.month:
        start = '%d %b'
    else:
        start = '%d'
    nights = (check_out - check_in).days
    return f"{check_in.strftime(start)} – {check_out.strftime(full)} ({nights}N)"


def _payment_history_context(payment):
    """One row per allocation of a payment_history_rows row; money not yet
    allocated is a row with no reservation. The paid-currency amount is split
    by SAR share, and the last row takes the rounding so the rows add up to
    what was received."""
    parts = [(a['rsv'], a['amount_sar']) for a in payment['allocations']]
    if payment['unallocated_sar'] > 0 or not parts:
        parts.append(('—', payment['unallocated_sar']))

    rows = []
    amount_left = payment['amount']
    for i, (rsv, amount_sar) in enumerate(parts):
        if i == len(parts) - 1:
            amount = amount_left
        else:
            amount = round(payment['amount'] * amount_sar / payment['amount_sar'])
        amount_left -= amount
        rows.append({
            # The later rows of a payment print only what differs per allocation.
            "first": i == 0,
            "payment_id": payment['payment_id'],
            "date": payment['payment_date'],
            "rsv": rsv,
            "method": payment['method'],
            "received_in": payment['received_in_display'] or "-",
            "amount": format_currency(amount),
            "currency": payment['currency'],
            "exchange": f"{payment['exchange_rate']:,.2f}" if payment['currency'] != "SAR" else "-",
            "amount_sar": format_currency(amount_sar),
        })
    return rows


def _reservation_room_rows(row, line):
    """The rooms behind one reservation row of the detailed invoice, read from
    its CL, with a cancellation penalty as a row of its own so they add up to
    the reservation's amount."""
    rows = [{
        "type": room.room_type,
        "meal": room.meals,
        "quantity": room.quantity,
        "rate": format_currency(room.price),
        "amount": format_currency(room.subtotal),
    } for room in line.confirmation_letter.rooms.select_related("room_type_ref")]
    if row["penalty_int"]:
        rows.append({
            "type": "Cancellation penalty", "meal": "", "quantity": "", "rate": "",
            "amount": format_currency(row["penalty_int"]),
        })
    return rows


# Part of the cache key: bump it when invoice_pdf_v2.html changes, or the
# database cache keeps serving the old layout for up to an hour after a deploy.
INVOICE_PDF_LAYOUT = 3


def _render_invoice_pdf(invoice, *, detailed=False):
    from django.core.cache import cache
    from ..finance import queries as fq

    filename = f"{invoice.invoice_number}{'-detailed' if detailed else ''}.pdf"
    payment_rows = fq.payment_history_rows(invoice)
    payment_state = [
        (
            p['pk'], p['payment_id'], p['payment_date'], p['method'], p['received_in_display'],
            p['amount'], p['currency'], p['exchange_rate'], p['amount_sar'], p['unallocated_sar'],
            tuple((a['rsv'], a['amount_sar']) for a in p['allocations']),
        )
        for p in payment_rows
    ]
    payment_fingerprint = hashlib.sha256(repr(payment_state).encode()).hexdigest()
    # Paid and credited are in the key: a payment or credit note changes the
    # document without saving the invoice row. Allocation state is included
    # too, since re-applying a payment can change the PDF without changing the
    # invoice's total paid amount.
    cache_key = (
        f"pdf:invoice:v{INVOICE_PDF_LAYOUT}:{invoice.pk}:{invoice.updated_at.isoformat()}"
        f":{invoice.total_paid_sar}:{invoice.credited_sar}:{invoice.down_payment_percent}"
        f":{detailed}:{payment_fingerprint}"
    )
    cached_pdf = cache.get(cache_key)
    if cached_pdf is not None:
        response = HttpResponse(cached_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    reservations = _build_reservation_context(invoice)
    lines_by_pk = {line.pk: line for line in invoice.billed_lines()} if detailed else {}
    for r in reservations:
        r["stay"] = _stay_label(r["check_in"], r["check_out"])
        if detailed:
            r["rooms"] = _reservation_room_rows(r, lines_by_pk[r["id"]])
            # One room type: its row already is the reservation's total.
            r["single_room"] = len(r["rooms"]) == 1
            r["rowspan"] = 1 if r["single_room"] else len(r["rooms"]) + 1
    payments_ctx = [
        row for p in payment_rows for row in _payment_history_context(p)
    ]

    total_sar = invoice.total_sar
    total_paid = invoice.applied_paid_sar
    total_remaining = invoice.remaining_sar

    hash_input = f"{invoice.invoice_number}|{int(total_sar)}|{invoice.issued_date}"
    doc_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()

    context = {
        "company_name": "",
        "company_city": "",
        "company_tagline": "",
        "customer_name": invoice.customer_name,
        "issued_date": datetime.combine(invoice.issued_date, datetime.min.time()) if invoice.issued_date else None,
        "due_date": datetime.combine(invoice.due_date, datetime.min.time()) if invoice.due_date else None,
        "invoice_number": invoice.invoice_number,
        "reservations": reservations,
        "payments": payments_ctx,
        "total_reservation_sar": format_currency(total_sar),
        "total_remaining_sar": format_currency(total_remaining),
        "total_paid_sar": format_currency(total_paid),
        "remaining": format_currency(total_remaining),
        "remaining_int": total_remaining,
        "excess_sar": format_currency(-total_remaining) if total_remaining < 0 else "",
        "credited_sar": format_currency(invoice.credited_sar) if invoice.credited_sar else "",
        "is_void": invoice.is_void,
        "detailed": detailed,
        "dp_percent": invoice.down_payment_percent if invoice.down_payment_sar else 0,
        "dp_due": invoice.down_payment_due_date,
        "dp_outstanding": format_currency(invoice.down_payment_outstanding_sar) if invoice.down_payment_outstanding_sar else "",
        "after_dp": format_currency(total_remaining - invoice.down_payment_outstanding_sar),
        "pay_to": list(invoice.pay_to_accounts()) if total_remaining > 0 else [],
        "logo_rel_path": _logo_file_url(),
        "doc_hash": doc_hash,
    }

    html = render_to_string("hw/invoice/invoice_pdf_v2.html", context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    cache.set(cache_key, pdf, 3600)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
