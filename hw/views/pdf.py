import base64
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


def _render_invoice_pdf(invoice):
    from django.core.cache import cache
    cache_key = f"pdf:invoice:{invoice.pk}:{invoice.updated_at.isoformat()}"
    cached_pdf = cache.get(cache_key)
    if cached_pdf is not None:
        response = HttpResponse(cached_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
        return response

    reservations = _build_reservation_context(invoice)
    from ..finance import queries as fq
    payments = fq.payment_history_rows(invoice)

    payments_ctx = []
    for p in payments:
        amt = float(p["amount"])
        ex = p["exchange_rate"]
        received_in_display = p.get("received_in_display") or p.get("receiving_office") or p.get("received_in") or "-"
        payments_ctx.append({
            "payment_id": p.get("payment_id") or p.get("payment_number") or p.get("pk"),
            "reservation_no": p["ref"],
            "date": p["payment_date"],
            "method": p["method"],
            "received_in": received_in_display,
            "amount": format_currency(int(round(amt))),
            "currency": p["currency"],
            "exchange": f"{ex:,.2f}" if p["currency"] != "SAR" else "-",
            "amount_sar": format_currency(p["amount_sar"]),
            "note": p["note"] or "-",
        })

    total_sar = invoice.total_sar
    total_paid = invoice.total_paid_sar
    total_remaining = total_sar - total_paid

    import hashlib
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
        "logo_rel_path": _logo_file_url(),
        "doc_hash": doc_hash,
    }

    html = render_to_string("hw/invoice/invoice_pdf_v2.html", context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    cache.set(cache_key, pdf, 3600)
    filename = f"{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
