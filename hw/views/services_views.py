import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import ActivityLog, Invoice, ServiceItem, log_activity
from .context import _build_visa_payments_context, _build_visa_services_context
from .helpers import _paginated_list, _parse_date, _render_list_pdf, _save_service_payments
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
    return _paginated_list(request, qs, "hw/services/services_history.html", "invoices")


@login_required
def services_new(request):
    suggested_number = Invoice.generate_number("visa")
    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            messages.error(request, f"Nomor Invoice '{invoice_number}' sudah digunakan.")
            return render(request, "hw/services/services_form.html", {
                "suggested_number": invoice_number,
                "default_company": request.session.get("active_company", "ijabah"),
                "form_data": request.POST,
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

    return render(request, "hw/services/services_form.html", {
        "suggested_number": suggested_number,
        "default_company": request.session.get("active_company", "ijabah"),
    })


@login_required
def services_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    visa_services = _build_visa_services_context(invoice)
    payments_history = _build_visa_payments_context(invoice)
    services_remaining = sum(s["remaining"] for s in visa_services)
    return render(request, "hw/services/services_detail.html", {
        "invoice": invoice,
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
            messages.error(request, f"Nomor Invoice '{new_number}' sudah digunakan.")
            return render(request, "hw/services/services_form.html", {"invoice": invoice, "edit": True, "form_data": request.POST})

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

    return render(request, "hw/services/services_form.html", {"invoice": invoice, "edit": True})


@login_required
def services_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="visa")
    if request.method == "POST":
        num = invoice.invoice_number
        invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Services', num, invoice.company)
        messages.success(request, f"Invoice Services {num} berhasil dihapus.")
        return redirect("services_list")
    return render(request, "hw/partials/confirm_delete.html", {"object": invoice, "type": "Invoice Services"})


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
    service_names = request.POST.getlist("service")
    qtys = request.POST.getlist("qty")
    amounts = request.POST.getlist("amount")
    for i, name in enumerate(service_names):
        if not name:
            continue
        ServiceItem.objects.create(
            invoice=invoice,
            service_number=i + 1,
            name=name,
            qty=int(qtys[i]) if i < len(qtys) and qtys[i] else 1,
            price=float(amounts[i]) if i < len(amounts) and amounts[i] else 0,
        )
