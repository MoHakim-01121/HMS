import base64
import math
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML

from ..utils import format_currency
from .context import (
    _build_reservation_context,
    _build_visa_payments_context,
    _build_visa_services_context,
)


def _logo_file_url(company):
    filename = "ijabahlogo.png" if company == "ijabah" else "LOGOKONOZ-02.png"
    mime = "image/png"
    path = Path(__file__).resolve().parent.parent / "static" / "hw" / "img" / filename
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _render_cl_pdf(cl):
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
        "company": cl.company,
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
        "logo_rel_path": _logo_file_url(cl.company),
    }

    template = "hw/cl/cl_pdf_ijabah.html" if cl.company == "ijabah" else "hw/cl/cl_pdf_konoz.html"
    html = render_to_string(template, context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    filename = f"{cl.confirmation_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _render_invoice_pdf(invoice):
    reservations = _build_reservation_context(invoice)
    payments = invoice.payments.all()

    payments_ctx = []
    for p in payments:
        amt = float(p.amount)
        ex = float(p.exchange_rate)
        payments_ctx.append({
            "reservation_no": p.linked_number,
            "date": p.payment_date,
            "method": p.method,
            "amount": format_currency(int(round(amt))),
            "currency": p.currency,
            "exchange": f"{ex:,.2f}" if p.currency != "SAR" else "-",
            "amount_sar": format_currency(p.amount_sar),
            "note": p.note or "-",
        })

    total_sar = invoice.total_sar
    total_paid = invoice.total_paid_sar
    total_remaining = total_sar - total_paid

    import hashlib
    hash_input = f"{invoice.invoice_number}|{int(total_sar)}|{invoice.issued_date}"
    doc_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()

    company_name = "" if invoice.company == "konoz" else "iJabah Group"
    context = {
        "company_name": company_name,
        "company_city": "",
        "company_tagline": "" if invoice.company == "konoz" else "Travel & Hospitality Services",
        "customer_name": invoice.customer_name,
        "issued_date": datetime.combine(invoice.issued_date, datetime.min.time()) if invoice.issued_date else None,
        "due_date": datetime.combine(invoice.due_date, datetime.min.time()) if invoice.due_date else None,
        "invoice_number": ('#' + invoice.invoice_number.split('-', 1)[1]) if invoice.company == 'ijabah' and '-' in invoice.invoice_number else invoice.invoice_number,
        "reservations": reservations,
        "payments": payments_ctx,
        "total_reservation_sar": format_currency(total_sar),
        "total_remaining_sar": format_currency(total_remaining),
        "total_paid_sar": format_currency(total_paid),
        "remaining": format_currency(total_remaining),
        "remaining_int": total_remaining,
        "logo_rel_path": _logo_file_url(invoice.company),
        "doc_hash": doc_hash,
    }

    template = "hw/invoice/invoice_pdf_ijabah.html" if invoice.company == "ijabah" else "hw/invoice/invoice_pdf_v2.html"
    html = render_to_string(template, context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    filename = f"{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _render_services_pdf(invoice):
    visa_services = _build_visa_services_context(invoice)
    payments_history = _build_visa_payments_context(invoice)
    main_currency = invoice.currency

    total_visa = math.floor(sum(s["total"] for s in visa_services))
    total_payments = math.floor(sum(p["payment_amount_main"] for p in payments_history))
    remaining_balance = math.floor(total_visa - total_payments)

    issued = datetime.combine(invoice.issued_date, datetime.min.time()) if invoice.issued_date else None
    due = datetime.combine(invoice.due_date, datetime.min.time()) if invoice.due_date else None

    context = {
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "issued_date": issued,
        "due_date": due,
        "visa_services": visa_services,
        "main_currency": main_currency,
        "payments_history": payments_history,
        "total_visa": total_visa,
        "total_remaining": remaining_balance,
        "total_payments": total_payments,
        "remaining_balance": remaining_balance,
        "logo_rel_path": _logo_file_url(invoice.company),
    }

    html = render_to_string("hw/services/invoice_pdf_visa.html", context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    filename = f"VISA_{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _build_checkin_groups(qs):
    from itertools import groupby
    groups = []
    for date_val, date_iter in groupby(qs, key=lambda c: c.check_in):
        date_list = list(date_iter)
        hotels = []
        for hotel_name, hotel_iter in groupby(date_list, key=lambda c: c.hotel_name):
            guests = []
            for i, cl in enumerate(list(hotel_iter), 1):
                rooms_str = ', '.join(
                    f"{r.quantity} {r.room_type}" for r in cl.rooms.all()
                ) or '—'
                guests.append({
                    'no': i,
                    'guest_name': cl.guest_name,
                    'confirmation_number': cl.confirmation_number,
                    'rooms': rooms_str,
                    'eta': cl.estimasi_tiba.strftime('%H:%M') if cl.estimasi_tiba is not None else '—',
                    'check_out': cl.check_out,
                    'num_nights': cl.num_nights,
                    'pic_name': cl.pic_name or '—',
                    'pic_phone': cl.pic_phone or '—',
                })
            hotels.append({'name': hotel_name, 'guests': guests})
        groups.append({
            'date': date_val,
            'hotels': hotels,
            'total': sum(len(h['guests']) for h in hotels),
        })
    return groups


def _render_checkin_pdf(cls, title, company='konoz', filename='checkin-rekap.pdf'):
    groups = _build_checkin_groups(cls)
    context = {
        'title': title,
        'print_date': datetime.now(),
        'groups': groups,
        'logo_rel_path': _logo_file_url(company),
    }
    html = render_to_string('hw/calendar/checkin_recap_pdf.html', context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
