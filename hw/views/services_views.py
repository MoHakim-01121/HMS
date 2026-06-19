import csv
import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models import ActivityLog, Invoice, ServiceItem, log_activity
from .context import _build_visa_payments_context, _build_visa_services_context
from .helpers import (
    _is_mobile,
    _page_range_display,
    _parse_date,
    _render_list_pdf,
    _save_service_payments,
    _to_float,
)
from .pdf import _render_services_pdf


@login_required
def services_list(request):
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="visa")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))

    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    invoices = [{
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "customer_name": inv.customer_name,
        "currency": inv.currency,
        "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
        "created_at": inv.created_at.strftime("%d/%m/%Y"),
    } for inv in page_obj]
    return inertia_render(request, "Services/List", props={
        "invoices": invoices,
        "total_count": paginator.count,
        "q": q,
        "pagination": {
            "number": page_obj.number,
            "num_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
            "has_other_pages": page_obj.has_other_pages(),
            "range": _page_range_display(page_obj),
        },
    })


@login_required
def services_new(request):
    suggested_number = Invoice.generate_number("visa")
    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return inertia_render(request, "Services/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": suggested_number,
                "default_company": request.session.get("active_company", "ijabah"),
                "initial": _services_echo(request),
                "errors": {"invoice_number": f"Nomor Invoice '{invoice_number}' sudah digunakan."},
            })

        invoice = Invoice.objects.create(
            company=request.POST.get("company", "ijabah"),
            invoice_type="visa",
            invoice_number=invoice_number,
            customer_name=request.POST.get("customer_name", ""),
            issued_date=_parse_date(request.POST.get("issued_date")),
            due_date=_parse_date(request.POST.get("due_date")),
            currency=request.POST.get("invoice_currency", "USD"),
        )
        _save_service_items(invoice, request)
        _save_service_payments(invoice, request)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Services', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice Services {invoice.invoice_number} berhasil dibuat.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "default_company": request.session.get("active_company", "ijabah"),
    })


@login_required
def services_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    visa_services = _build_visa_services_context(invoice)
    payments_raw = _build_visa_payments_context(invoice)
    services_remaining = sum(s["remaining"] for s in visa_services)
    payments_history = [{
        "payment_date": p["payment_date"].strftime("%d/%m/%Y") if p["payment_date"] else None,
        "payment_method": p["payment_method"],
        "payment_amount": p["payment_amount"],
        "payment_currency": p["payment_currency"],
        "payment_exchange": f"{float(p['payment_exchange']):.2f}",
        "payment_note": p["payment_note"],
        "proof_url": p["proof"].url if p["proof"] else None,
    } for p in payments_raw]
    return inertia_render(request, "Services/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "currency": invoice.currency,
            "company": invoice.company,
            "issued_date": invoice.issued_date.strftime("%d/%m/%Y") if invoice.issued_date else None,
            "due_date": invoice.due_date.strftime("%d/%m/%Y") if invoice.due_date else None,
            "created_at": invoice.created_at.strftime("%d/%m/%Y %H:%M"),
        },
        "visa_services": visa_services,
        "payments_history": payments_history,
        "services_remaining": services_remaining,
    })


@login_required
def services_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")

    if request.method == "POST":
        _before = {
            'Nama Customer': invoice.customer_name,
            'No. Invoice':   invoice.invoice_number,
            'Tgl. Terbit':   str(invoice.issued_date or ''),
            'Tgl. Jatuh Tempo': str(invoice.due_date or ''),
            'Mata Uang':     invoice.currency,
            'Company':       invoice.company,
        }
        new_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            echo = _services_echo(request)
            echo["pk"] = invoice.pk
            return inertia_render(request, "Services/Form", props={
                "edit": True,
                "invoice": _serialize_service_invoice(invoice),
                "initial": echo,
                "errors": {"invoice_number": f"Nomor Invoice '{new_number}' sudah digunakan."},
            })

        invoice.company = request.POST.get("company", "ijabah")
        invoice.invoice_number = new_number
        invoice.customer_name = request.POST.get("customer_name", "")
        invoice.issued_date = _parse_date(request.POST.get("issued_date"))
        invoice.due_date = _parse_date(request.POST.get("due_date"))
        invoice.currency = request.POST.get("invoice_currency", "USD")
        invoice.save()

        invoice.service_items.all().delete()
        invoice.payments.all().delete()
        _save_service_items(invoice, request)
        _save_service_payments(invoice, request)
        _after = {
            'Nama Customer': invoice.customer_name,
            'No. Invoice':   invoice.invoice_number,
            'Tgl. Terbit':   str(invoice.issued_date or ''),
            'Tgl. Jatuh Tempo': str(invoice.due_date or ''),
            'Mata Uang':     invoice.currency,
            'Company':       invoice.company,
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Services', invoice.invoice_number, invoice.company, changes)
        messages.success(request, f"Invoice Services {invoice.invoice_number} berhasil diperbarui.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": True,
        "invoice": _serialize_service_invoice(invoice),
    })


@login_required
def services_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    if request.method == "POST":
        num = invoice.invoice_number
        invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Services', num, invoice.company)
        messages.success(request, f"Invoice Services {num} berhasil dihapus.")
        return redirect("services_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("services_list")


@login_required
def services_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    return _render_services_pdf(invoice)


@login_required
def services_list_pdf(request):
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="visa")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    return _render_list_pdf(
        request, qs,
        template="hw/services/services_list_pdf.html",
        filename="invoices_services.pdf",
        extra_ctx={"invoices": list(qs)},
    )


@login_required
def services_export_csv(request):
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="visa")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="invoices_services.csv"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['Invoice #', 'Company', 'Customer', 'Currency', 'Issued Date', 'Due Date'])
    for inv in qs:
        writer.writerow([
            inv.invoice_number, inv.company, inv.customer_name,
            inv.currency, inv.issued_date or '', inv.due_date or '',
        ])
    return response


@login_required
def services_duplicate(request, pk):
    original = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    new_num = Invoice.generate_number("visa")
    today = date.today()
    new_inv = Invoice.objects.create(
        company=original.company,
        invoice_type="visa",
        invoice_number=new_num,
        customer_name=original.customer_name,
        issued_date=today,
        due_date=today + timedelta(days=30),
        currency=original.currency,
    )
    for item in original.service_items.all():
        ServiceItem.objects.create(
            invoice=new_inv,
            service_number=item.service_number,
            name=item.name,
            qty=item.qty,
            price=item.price,
        )
    messages.success(request, f"Invoice Services diduplikasi sebagai {new_num} (dari {original.invoice_number}).")
    return redirect("services_edit", pk=new_inv.pk)


def _save_service_items(invoice, request):
    try:
        rows = json.loads(request.POST.get("service_items", "[]"))
    except (ValueError, TypeError):
        rows = []
    number = 0
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        number += 1
        ServiceItem.objects.create(
            invoice=invoice,
            service_number=number,
            name=name,
            qty=int(_to_float(r.get("qty"), 1)) or 1,
            price=_to_float(r.get("price")),
        )


def _services_echo(request):
    """Echo submitted values (incl. JSON arrays) back to the form on error."""
    try:
        items = json.loads(request.POST.get("service_items", "[]"))
    except (ValueError, TypeError):
        items = []
    try:
        pays = json.loads(request.POST.get("payments", "[]"))
    except (ValueError, TypeError):
        pays = []
    return {
        "company": request.POST.get("company", "ijabah"),
        "customer_name": request.POST.get("customer_name", ""),
        "invoice_number": request.POST.get("invoice_number", ""),
        "invoice_currency": request.POST.get("invoice_currency", "USD"),
        "issued_date": request.POST.get("issued_date", ""),
        "due_date": request.POST.get("due_date", ""),
        "service_items": items,
        "payments": pays,
    }


def _serialize_service_invoice(invoice):
    """Invoice + service items + payments serialized for the React form."""
    return {
        "pk": invoice.pk,
        "company": invoice.company,
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "invoice_currency": invoice.currency,
        "issued_date": invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "",
        "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        "service_items": [{
            "service_number": it.service_number,
            "name": it.name,
            "qty": it.qty,
            "price": float(it.price),
        } for it in invoice.service_items.all()],
        "payments": [{
            "ref": p.linked_number,
            "date": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else "",
            "method": p.method,
            "amount": float(p.amount),
            "currency": p.currency,
            "exchange": float(p.exchange_rate),
            "note": p.note,
            "proof_keep": p.proof.name if p.proof else "",
            "proof_url": p.proof.url if p.proof else None,
        } for p in invoice.payments.all()],
    }
