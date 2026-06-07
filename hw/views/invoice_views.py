import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ExpressionWrapper, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..ai import generate_invoice_summary
from ..models import ActivityLog, ConfirmationLetter, Invoice, Reservation, log_activity
from ..utils import convert_to_sar
from .context import _build_reservation_context
from .helpers import _paginated_list, _parse_date, _render_list_pdf, _save_hotel_payments
from .pdf import _render_invoice_pdf


@login_required
def invoice_list(request):
    active_company = request.session.get("active_company")
    base_qs = Invoice.objects.filter(invoice_type="hotel")
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

    extra = {"due_soon_filter": bool(due_soon), "status_filter": status}
    if active_company == 'konoz':
        extra['remit_stats'] = _invoice_stats(base_qs, active_company)

    return _paginated_list(request, qs, "hw/invoice/invoice_history.html", "invoices", extra_ctx=extra)


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
            messages.error(request, f"Nomor Invoice '{invoice_number}' sudah digunakan.")
            cl_qs = ConfirmationLetter.objects.select_related("invoice")
            if active_company:
                cl_qs = cl_qs.filter(company=active_company)
            cl_data = [{
                "id": cl.pk, "ref": cl.confirmation_number, "guest": cl.guest_name,
                "hotel": cl.hotel_name or "-",
                "check_in": cl.check_in.isoformat() if cl.check_in else "",
                "check_out": cl.check_out.isoformat() if cl.check_out else "",
                "total": int(round(cl.total_price)) if cl.total_price else 0,
                "inv": cl.invoice.invoice_number if cl.invoice_id else "",
            } for cl in cl_qs.order_by("-created_at")[:100]]
            return render(request, "hw/invoice/invoice_form.html", {
                "suggested_number": invoice_number,
                "default_company": active_company or "konoz",
                "cl_data_json": cl_data,
                "form_data": request.POST,
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

        cl_ids = request.POST.getlist("linked_cl_ids")
        if cl_ids:
            ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

        generate_invoice_summary(invoice)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice {invoice.invoice_number} berhasil dibuat.")
        return redirect("invoice_detail", pk=invoice.pk)

    cl_qs = ConfirmationLetter.objects.select_related("invoice")
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)
    cl_data = [{
        "id": cl.pk,
        "ref": cl.confirmation_number,
        "guest": cl.guest_name,
        "hotel": cl.hotel_name or "-",
        "check_in": cl.check_in.isoformat() if cl.check_in else "",
        "check_out": cl.check_out.isoformat() if cl.check_out else "",
        "total": int(round(cl.total_price)) if cl.total_price else 0,
        "inv": cl.invoice.invoice_number if cl.invoice_id else "",
    } for cl in cl_qs.order_by("-created_at")[:100]]

    return render(request, "hw/invoice/invoice_form.html", {
        "suggested_number": suggested_number,
        "default_company": active_company or "konoz",
        "cl_data_json": cl_data,
    })


@login_required
def invoice_detail(request, pk):
    active_company = request.session.get('active_company')
    filters = {'pk': pk, 'invoice_type': 'hotel'}
    if active_company:
        filters['company'] = active_company
    invoice = get_object_or_404(Invoice, **filters)
    reservations = _build_reservation_context(invoice)
    due_alert = None
    if invoice.due_date and invoice.remaining_sar > 0:
        days = (invoice.due_date - date.today()).days
        if days < 0:
            due_alert = {"type": "red", "msg": f"Jatuh tempo sudah lewat {abs(days)} hari yang lalu."}
        elif days == 0:
            due_alert = {"type": "red", "msg": "Jatuh tempo hari ini!"}
        elif days <= 7:
            due_alert = {"type": "yellow", "msg": f"Jatuh tempo {days} hari lagi."}
    return render(request, "hw/invoice/invoice_detail.html", {
        "invoice": invoice,
        "reservations": reservations,
        "ai_summary": invoice.ai_summary or None,
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
            messages.error(request, f"Nomor Invoice '{new_number}' sudah digunakan.")
            return render(request, "hw/invoice/invoice_form.html", {"invoice": invoice, "edit": True, "form_data": request.POST})

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
        cl_ids = request.POST.getlist("linked_cl_ids")
        if cl_ids:
            ConfirmationLetter.objects.filter(invoice=invoice).update(invoice=None)
            ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)
        generate_invoice_summary(invoice)
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

    cl_qs = ConfirmationLetter.objects.select_related("invoice")
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)
    cl_data = [{
        "id": cl.pk,
        "ref": cl.confirmation_number,
        "guest": cl.guest_name,
        "hotel": cl.hotel_name or "-",
        "check_in": cl.check_in.isoformat() if cl.check_in else "",
        "check_out": cl.check_out.isoformat() if cl.check_out else "",
        "total": int(round(cl.total_price)) if cl.total_price else 0,
        "inv": cl.invoice.invoice_number if cl.invoice_id else "",
    } for cl in cl_qs.order_by("-created_at")[:100]]
    return render(request, "hw/invoice/invoice_form.html", {
        "invoice": invoice, "edit": True, "cl_data_json": cl_data,
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
    reservation_numbers = request.POST.getlist("reservation_number")
    hotels = request.POST.getlist("hotel")
    checkins = request.POST.getlist("check_in")
    checkouts = request.POST.getlist("check_out")
    reservation_totals = request.POST.getlist("reservation_total")
    for num, hotel, ci, co, total in zip(reservation_numbers, hotels, checkins, checkouts, reservation_totals):
        amt = int(round(float(total.strip()))) if total and total.strip() else 0
        Reservation.objects.create(
            invoice=invoice,
            reservation_number=num.strip() if num else "-",
            hotel=hotel.strip() if hotel else "-",
            check_in=_parse_date(ci),
            check_out=_parse_date(co),
            total_sar=amt,
        )
