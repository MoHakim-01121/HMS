import csv
import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ExpressionWrapper, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from inertia import render as inertia_render

from ..models import ActivityLog, ConfirmationLetter, Invoice, Reservation, log_activity
from ..utils import convert_to_sar
from .context import _build_reservation_context
from .helpers import (
    _is_mobile,
    _page_range_display,
    _paginated_list,
    _parse_date,
    _render_list_pdf,
    _save_hotel_payments,
    _to_float,
)
from .pdf import _render_invoice_pdf


@login_required
def invoice_list(request):
    active_company = request.session.get("active_company")
    base_qs = Invoice.objects.filter(invoice_type="hotel").prefetch_related('reservations', 'payments')
    if active_company:
        base_qs = base_qs.filter(company=active_company)

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    due_soon = request.GET.get('due_soon')

    qs = base_qs
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    if due_soon:
        threshold = date.today() + timedelta(days=7)
        qs = qs.filter(due_date__lte=threshold, due_date__gte=date.today())
    if status in ('lunas', 'belum', 'partial'):
        qs = qs.annotate(
            _res=Coalesce(Sum('reservations__total_sar'), 0),
            _paid=Coalesce(Sum(ExpressionWrapper(
                F('payments__amount') * F('payments__exchange_rate'),
                output_field=FloatField()
            )), 0.0),
        )
        if status == 'lunas':
            qs = qs.filter(_paid__gte=F('_res'))
        elif status == 'belum':
            qs = qs.filter(_paid__lt=1)
        elif status == 'partial':
            qs = qs.filter(_paid__gte=1).exclude(_paid__gte=F('_res'))

    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    invoices = [{
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "customer_name": inv.customer_name,
        "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
        "created_at": inv.created_at.strftime("%d/%m/%Y"),
        "total_sar": inv.total_sar,
        "remaining_sar": inv.remaining_sar,
        "status": (
            "paid" if inv.remaining_sar == 0
            else "partial" if inv.remaining_sar < inv.total_sar
            else "unpaid"
        ),
    } for inv in page_obj]

    props = {
        "invoices": invoices,
        "total_count": paginator.count,
        "q": q,
        "status_filter": status,
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
    }
    if active_company == 'konoz':
        props["remit_stats"] = _invoice_stats(base_qs, active_company)

    return inertia_render(request, "Invoice/List", props=props)


def _invoice_stats(invoice_qs, company):
    from ..models import Payment, RemittanceLine
    from django.db.models import Sum as _Sum

    total_tagihan = int(invoice_qs.aggregate(
        t=_Sum('reservations__total_sar')
    )['t'] or 0)

    invoice_ids = invoice_qs.values_list('id', flat=True)
    payments = Payment.objects.filter(invoice_id__in=invoice_ids).values(
        'method', 'amount', 'currency', 'exchange_rate'
    )
    terbayar_surabaya = 0
    terbayar_pusat = 0
    for p in payments:
        sar = int(round(convert_to_sar(float(p['amount']), p['currency'], float(p['exchange_rate']))))
        m = (p['method'] or '').lower()
        if m == 'direct':
            terbayar_pusat += sar
        elif m in ('cash', 'bank transfer', 'deposit'):
            terbayar_surabaya += sar

    sudah_dikirim = int(RemittanceLine.objects.filter(
        remittance__company=company, invoice_id__in=invoice_ids
    ).aggregate(t=_Sum('amount_sar'))['t'] or 0)

    return {
        'total_tagihan': total_tagihan,
        'belum_terbayar': max(0, total_tagihan - terbayar_surabaya - terbayar_pusat),
        'mengendap': max(0, terbayar_surabaya - sudah_dikirim),
        'terbayar_surabaya': terbayar_surabaya,
        'terbayar_pusat': terbayar_pusat,
    }


@login_required
def invoice_new(request):
    suggested_number = Invoice.generate_number("hotel")
    active_company = request.session.get("active_company")

    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return inertia_render(request, "Invoice/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": invoice_number,
                "default_company": active_company or "konoz",
                "cl_data": _cl_data_for_form(active_company),
                "initial": _invoice_echo(request),
                "errors": {"invoice_number": f"Nomor Invoice '{invoice_number}' sudah digunakan."},
            })

        invoice = Invoice.objects.create(
            company=request.POST.get("company", "konoz"),
            invoice_type="hotel",
            invoice_number=invoice_number,
            customer_name=request.POST.get("customer_name", ""),
            issued_date=_parse_date(request.POST.get("issued_date")),
            due_date=_parse_date(request.POST.get("due_date")),
            currency="SAR",
        )
        _save_reservations(invoice, request)
        _save_hotel_payments(invoice, request)

        cl_ids = _parse_cl_ids(request)
        if cl_ids:
            ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice {invoice.invoice_number} berhasil dibuat.")
        return redirect("invoice_detail", pk=invoice.pk)

    return inertia_render(request, "Invoice/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "default_company": active_company or "konoz",
        "cl_data": _cl_data_for_form(active_company),
    })


@login_required
def invoice_detail(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    invoice = get_object_or_404(Invoice, **filters)
    res_ctx = _build_reservation_context(invoice)
    reservations = [{
        "number": r["number"],
        "hotel": r["hotel"],
        "check_in": r["check_in"].strftime("%d/%m/%Y") if r["check_in"] else None,
        "check_out": r["check_out"].strftime("%d/%m/%Y") if r["check_out"] else None,
        "total_int": r["total_int"],
        "remaining_int": r["remaining_int"],
        "remaining_class": r["remaining_class"],
        "cl_pk": r["cl_pk"],
    } for r in res_ctx]

    payments = [{
        "linked_number": p.linked_number,
        "payment_date": p.payment_date.strftime("%d/%m/%Y") if p.payment_date else None,
        "method": p.method,
        "amount_int": int(round(float(p.amount))),
        "currency": p.currency,
        "exchange_rate": float(p.exchange_rate),
        "exchange_rate_fmt": f"{float(p.exchange_rate):.2f}",
        "amount_sar_int": p.amount_sar,
        "proof_url": p.proof.url if p.proof else None,
        "note": p.note,
    } for p in invoice.payments.all()]

    due_alert = None
    if invoice.due_date and invoice.remaining_sar > 0:
        days = (invoice.due_date - date.today()).days
        if days < 0:
            due_alert = {"type": "red", "msg": f"Jatuh tempo sudah lewat {abs(days)} hari yang lalu."}
        elif days == 0:
            due_alert = {"type": "red", "msg": "Jatuh tempo hari ini!"}
        elif days <= 7:
            due_alert = {"type": "yellow", "msg": f"Jatuh tempo {days} hari lagi."}

    return inertia_render(request, "Invoice/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "issued_date": invoice.issued_date.strftime("%d %b %Y") if invoice.issued_date else None,
            "total_sar": invoice.total_sar,
            "total_paid_sar": invoice.total_paid_sar,
            "remaining_sar": invoice.remaining_sar,
        },
        "reservations": reservations,
        "payments": payments,
        "due_alert": due_alert,
    })


@login_required
def invoice_edit(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    invoice = get_object_or_404(Invoice, **filters)

    if request.method == "POST":
        def _res_snapshot(inv):
            rows = [
                f"{r.hotel} {r.check_in}–{r.check_out} ({int(r.total_sar or 0)} SAR)"
                for r in inv.reservations.order_by('id')
            ]
            return ' | '.join(rows) if rows else '—'

        _before = {
            'Nama Customer':    invoice.customer_name,
            'No. Invoice':      invoice.invoice_number,
            'Tgl. Terbit':      str(invoice.issued_date or ''),
            'Tgl. Jatuh Tempo': str(invoice.due_date or ''),
            'Company':          invoice.company,
            'Reservasi':        _res_snapshot(invoice),
        }
        new_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            return inertia_render(request, "Invoice/Form", props={
                "edit": True,
                "invoice": _serialize_hotel_invoice(invoice),
                "cl_data": _cl_data_for_form(active_company),
                "initial": _invoice_echo(request),
                "errors": {"invoice_number": f"Nomor Invoice '{new_number}' sudah digunakan."},
            })

        invoice.company = request.POST.get("company", "konoz")
        invoice.invoice_number = new_number
        invoice.customer_name = request.POST.get("customer_name", "")
        invoice.issued_date = _parse_date(request.POST.get("issued_date"))
        invoice.due_date = _parse_date(request.POST.get("due_date"))
        invoice.save()

        invoice.reservations.all().delete()
        invoice.payments.all().delete()
        _save_reservations(invoice, request)
        _save_hotel_payments(invoice, request)
        cl_ids = _parse_cl_ids(request)
        if cl_ids:
            ConfirmationLetter.objects.filter(invoice=invoice).update(invoice=None)
            ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)
        _after = {
            'Nama Customer':    invoice.customer_name,
            'No. Invoice':      invoice.invoice_number,
            'Tgl. Terbit':      str(invoice.issued_date or ''),
            'Tgl. Jatuh Tempo': str(invoice.due_date or ''),
            'Company':          invoice.company,
            'Reservasi':        _res_snapshot(invoice),
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Hotel', invoice.invoice_number, invoice.company, changes)
        messages.success(request, f"Invoice {invoice.invoice_number} berhasil diperbarui.")
        return redirect("invoice_detail", pk=invoice.pk)

    return inertia_render(request, "Invoice/Form", props={
        "edit": True,
        "invoice": _serialize_hotel_invoice(invoice),
        "cl_data": _cl_data_for_form(active_company),
    })


@login_required
def invoice_delete(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    invoice = get_object_or_404(Invoice, **filters)
    if request.method == "POST":
        num = invoice.invoice_number
        invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Hotel', num, invoice.company)
        messages.success(request, f"Invoice {num} berhasil dihapus.")
        return redirect("invoice_list")
    return render(request, "hw/partials/confirm_delete.html", {"object": invoice, "type": "Invoice Hotel"})


@login_required
def invoice_pdf(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    invoice = get_object_or_404(Invoice, **filters)
    return _render_invoice_pdf(invoice)


@login_required
def invoice_list_pdf(request):
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="hotel")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    inv_list = list(qs)
    total_sar = sum(i.total_sar for i in inv_list)
    total_remaining = sum(i.remaining_sar for i in inv_list)
    return _render_list_pdf(
        request, qs,
        template="hw/invoice/invoice_list_pdf.html",
        filename="invoices_hotel.pdf",
        extra_ctx={
            "invoices": inv_list,
            "total_sar": total_sar,
            "total_paid": total_sar - total_remaining,
            "total_remaining": total_remaining,
        },
    )


@login_required
def invoice_export_csv(request):
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="hotel")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="invoices_hotel.csv"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['Invoice #', 'Company', 'Customer', 'Issued Date', 'Due Date', 'Total SAR', 'Paid SAR', 'Sisa SAR'])
    for inv in qs:
        writer.writerow([
            inv.invoice_number, inv.company, inv.customer_name,
            inv.issued_date or '', inv.due_date or '',
            inv.total_sar, inv.total_sar - inv.remaining_sar, inv.remaining_sar,
        ])
    return response


@login_required
def invoice_duplicate(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    original = get_object_or_404(Invoice, **filters)
    new_num = Invoice.generate_number("hotel")
    today = date.today()
    new_inv = Invoice.objects.create(
        company=original.company,
        invoice_type="hotel",
        invoice_number=new_num,
        customer_name=original.customer_name,
        issued_date=today,
        due_date=today + timedelta(days=30),
        currency=original.currency,
    )
    for res in original.reservations.all():
        Reservation.objects.create(
            invoice=new_inv,
            reservation_number=res.reservation_number,
            hotel=res.hotel,
            check_in=res.check_in,
            check_out=res.check_out,
            total_sar=res.total_sar,
        )
    messages.success(request, f"Invoice diduplikasi sebagai {new_num} (dari {original.invoice_number}).")
    return redirect("invoice_edit", pk=new_inv.pk)


def _save_reservations(invoice, request):
    try:
        rows = json.loads(request.POST.get("reservations", "[]"))
    except (ValueError, TypeError):
        rows = []
    for r in rows:
        Reservation.objects.create(
            invoice=invoice,
            reservation_number=(r.get("reservation_number") or "-").strip() or "-",
            hotel=(r.get("hotel") or "-").strip() or "-",
            check_in=_parse_date(r.get("check_in")),
            check_out=_parse_date(r.get("check_out")),
            total_sar=int(round(_to_float(r.get("reservation_total")))),
        )


def _invoice_echo(request):
    """Echo submitted values (incl. JSON arrays) back to the form on error."""
    def _loads(key):
        try:
            return json.loads(request.POST.get(key, "[]"))
        except (ValueError, TypeError):
            return []
    return {
        "company": request.POST.get("company", "konoz"),
        "customer_name": request.POST.get("customer_name", ""),
        "invoice_number": request.POST.get("invoice_number", ""),
        "issued_date": request.POST.get("issued_date", ""),
        "due_date": request.POST.get("due_date", ""),
        "reservations": _loads("reservations"),
        "payments": _loads("payments"),
        "linked_cl_ids": _loads("linked_cl_ids"),
    }


def _serialize_hotel_invoice(invoice):
    """Invoice + reservations + payments serialized for the React form."""
    return {
        "pk": invoice.pk,
        "company": invoice.company,
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "issued_date": invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "",
        "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        "reservations": [{
            "reservation_number": r.reservation_number,
            "hotel": r.hotel,
            "check_in": r.check_in.strftime("%Y-%m-%d") if r.check_in else "",
            "check_out": r.check_out.strftime("%Y-%m-%d") if r.check_out else "",
            "reservation_total": int(r.total_sar or 0),
        } for r in invoice.reservations.all()],
        "payments": [{
            "ref": p.linked_number,
            "date": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else "",
            "method": p.method or "Cash",
            "amount": float(p.amount),
            "currency": p.currency,
            "exchange": float(p.exchange_rate),
            "note": p.note,
            "proof_keep": p.proof.name if p.proof else "",
            "proof_url": p.proof.url if p.proof else None,
        } for p in invoice.payments.all()],
    }


def _parse_cl_ids(request):
    try:
        ids = json.loads(request.POST.get("linked_cl_ids", "[]"))
    except (ValueError, TypeError):
        ids = []
    return [i for i in ids if i]


def _cl_data_for_form(active_company):
    cl_qs = ConfirmationLetter.objects.select_related("invoice")
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)
    return [{
        "id": cl.pk,
        "ref": cl.confirmation_number,
        "guest": cl.guest_name,
        "hotel": cl.hotel_name or "-",
        "check_in": cl.check_in.isoformat() if cl.check_in else "",
        "check_out": cl.check_out.isoformat() if cl.check_out else "",
        "total": int(round(cl.total_price)) if cl.total_price else 0,
        "inv": cl.invoice.invoice_number if cl.invoice_id else "",
    } for cl in cl_qs.order_by("-created_at")[:100]]
