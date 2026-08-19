import csv
import json
import logging
from datetime import date, timedelta
from django.utils import timezone

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models import ActivityLog, Invoice, ServiceItem, log_activity
from ..permissions import require_perm
from .context import _build_visa_payments_context, _build_visa_services_context
from .helpers import (
    _is_mobile,
    _page_range_display,
    _parse_date,
    _render_list_pdf,
    _to_float,
    get_active_company,
)
from .invoice_billing import _billing_client, _billing_props, _save_service_payments
from .pdf import _render_services_pdf

logger = logging.getLogger(__name__)


def _get_service_invoice(request, pk):
    """Fetch a visa invoice scoped to the active company (consistent with invoice/cl views)."""
    return get_object_or_404(
        Invoice, pk=pk, invoice_type='visa', company=get_active_company(request)
    )


@require_perm('services', 'view')
def services_list(request):
    qs = Invoice.objects.filter(invoice_type="visa", company=get_active_company(request))
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
            "start_index": page_obj.start_index(),
            "end_index": page_obj.end_index(),
            "count": paginator.count,
        },
    })


@require_perm('services', 'create')
def services_new(request):
    suggested_number = Invoice.generate_number("visa")
    active_company = get_active_company(request)
    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return inertia_render(request, "Services/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": suggested_number,
                "initial": _services_echo(request),
                "errors": {"invoice_number": f"Invoice number '{invoice_number}' is already in use."},
            })

        with transaction.atomic():
            invoice = Invoice.objects.create(
                # The form no longer posts a company: it used to submit one of its
                # own, unchecked against can_use_company, so a user restricted to
                # one company could file a record under the other — and every
                # list/detail/edit view here filters by the active company, meaning
                # the row simply vanished from the list it was created from.
                company=active_company,
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
        messages.success(request, f"Services Invoice {invoice.invoice_number} created successfully.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
    })


@require_perm('services', 'view')
def services_detail(request, pk):
    invoice = _get_service_invoice(request, pk)
    visa_services = _build_visa_services_context(invoice)
    payments_raw = _build_visa_payments_context(invoice)
    services_remaining = sum(s["remaining"] for s in visa_services)
    # linked_number and amount_main mirror Invoice/Detail's payments payload:
    # the service a payment settles is the only reference it carries, and the
    # converted figure is what the totals column adds up.
    payments_history = [{
        "linked_number": p["linked_number"],
        "payment_date": p["payment_date"].strftime("%d/%m/%Y") if p["payment_date"] else None,
        "payment_method": p["payment_method"],
        "payment_amount": p["payment_amount"],
        "payment_amount_main": int(round(p["payment_amount_main"])),
        "payment_currency": p["payment_currency"],
        "payment_exchange": f"{float(p['payment_exchange']):.2f}",
        "payment_note": p["payment_note"],
        "proof_url": p["proof"].url if p["proof"] else None,
    } for p in payments_raw]

    # Same rule as invoice_detail: only warn while money is still owed.
    due_alert = None
    if invoice.due_date and services_remaining > 0:
        days = (invoice.due_date - timezone.now().date()).days
        if days < 0:
            due_alert = {"type": "red", "msg": f"Payment is {abs(days)} day(s) overdue."}
        elif days == 0:
            due_alert = {"type": "red", "msg": "Due today!"}
        elif days <= 7:
            due_alert = {"type": "yellow", "msg": f"Due in {days} day(s)."}

    return inertia_render(request, "Services/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "currency": invoice.currency,
            "company": invoice.company,
            "issued_date": invoice.issued_date.strftime("%d %b %Y") if invoice.issued_date else None,
            "due_date": invoice.due_date.strftime("%d %b %Y") if invoice.due_date else None,
            "created_at": invoice.created_at.strftime("%d/%m/%Y %H:%M"),
        },
        "visa_services": visa_services,
        "payments_history": payments_history,
        "services_remaining": services_remaining,
        "due_alert": due_alert,
        **_billing_props(invoice),
    })


@require_perm('services', 'edit')
def services_edit(request, pk):
    invoice = _get_service_invoice(request, pk)

    if request.method == "POST":
        _before = {
            'Customer Name': invoice.customer_name,
            'Invoice No.':   invoice.invoice_number,
            'Issued Date':   str(invoice.issued_date or ''),
            'Due Date':      str(invoice.due_date or ''),
            'Currency':      invoice.currency,
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
                "errors": {"invoice_number": f"Invoice number '{new_number}' is already in use."},
            })

        # invoice.company is deliberately left alone: _get_service_invoice
        # already constrains it to the active company, so any value arriving in
        # the POST could only move the record out from under the user.
        with transaction.atomic():
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
            'Customer Name': invoice.customer_name,
            'Invoice No.':   invoice.invoice_number,
            'Issued Date':   str(invoice.issued_date or ''),
            'Due Date':      str(invoice.due_date or ''),
            'Currency':      invoice.currency,
            'Company':       invoice.company,
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Services', invoice.invoice_number, invoice.company, changes)
        messages.success(request, f"Services Invoice {invoice.invoice_number} updated successfully.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": True,
        "invoice": _serialize_service_invoice(invoice),
    })


@require_perm('services', 'delete')
def services_delete(request, pk):
    invoice = _get_service_invoice(request, pk)
    if request.method == "POST":
        num = invoice.invoice_number
        # System of record: sama seperti invoice hotel -- menghapus invoice
        # meng-cascade ServiceItems → Charges (ledger).
        from ..models import Charge, Allocation, CashMovement
        has_ledger = (
            Charge.objects.filter(invoice=invoice).exists()
            or Allocation.objects.filter(invoice=invoice).exists()
            or CashMovement.objects.filter(invoice=invoice).exists()
        )
        if has_ledger:
            messages.error(request, f'Invoice {num} tidak bisa dihapus karena sudah tercatat di ledger keuangan.')
            return redirect('services_detail', pk=pk)
        invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Services', num, invoice.company)
        messages.success(request, f"Services Invoice {num} deleted successfully.")
        return redirect("services_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("services_list")


@require_perm('services', 'export')
def services_pdf(request, pk):
    invoice = _get_service_invoice(request, pk)
    return _render_services_pdf(invoice)


@require_perm('services', 'export')
def services_list_pdf(request):
    qs = Invoice.objects.filter(invoice_type="visa", company=get_active_company(request))
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    return _render_list_pdf(
        request, qs,
        template="hw/services/services_list_pdf.html",
        filename="invoices_services.pdf",
        extra_ctx={"invoices": list(qs)},
    )


@require_perm('services', 'export')
def services_export_csv(request):
    qs = Invoice.objects.filter(invoice_type="visa", company=get_active_company(request))
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


@require_perm('services', 'create')
def services_duplicate(request, pk):
    original = _get_service_invoice(request, pk)
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
    messages.success(request, f"Services Invoice duplicated as {new_num} (from {original.invoice_number}).")
    return redirect("services_edit", pk=new_inv.pk)


def _save_service_items(invoice, request):
    """Dual-write (remittance ledger redesign, Fase 4) -- see _save_reservations
    for why this is a full recreate rather than a diff, and why deleting the
    old ServiceItem rows is enough to clean up their old Charge rows too."""
    from ..models import Charge, ChargeReason

    try:
        rows = json.loads(request.POST.get("service_items", "[]"))
    except (ValueError, TypeError):
        rows = []
    client = _billing_client(invoice)
    number = 0
    with transaction.atomic():
        for r in rows:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            number += 1
            qty = int(_to_float(r.get("qty"), 1)) or 1
            price = _to_float(r.get("price"))
            item = ServiceItem.objects.create(
                invoice=invoice,
                service_number=number,
                name=name,
                qty=qty,
                price=price,
            )
            total = int(round(qty * price))
            if total:
                Charge.objects.create(
                    company=invoice.company, client=client, invoice=invoice,
                    date=invoice.issued_date or date.today(),
                    amount_sar=total, service_item=item, reason=ChargeReason.INITIAL,
                    description=f'Sinkron dari layanan {name}', created_by=request.user,
                )
    logger.info(
        "ledger: %d service item(s) synced for invoice %s",
        number, invoice.invoice_number,
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
