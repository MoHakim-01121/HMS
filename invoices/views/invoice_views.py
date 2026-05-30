import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Invoice, Reservation
from .context import _build_reservation_context
from .helpers import _paginated_list, _parse_date, _render_list_pdf, _save_hotel_payments
from .pdf import _render_invoice_pdf


@login_required
def invoice_list(request):
    from datetime import date as _date, timedelta
    active_company = request.session.get("active_company")
    qs = Invoice.objects.filter(invoice_type="hotel")
    if active_company:
        qs = qs.filter(company=active_company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    due_soon = request.GET.get('due_soon')
    if due_soon:
        threshold = _date.today() + timedelta(days=7)
        qs = qs.filter(due_date__lte=threshold, due_date__gte=_date.today())
    return _paginated_list(request, qs, "invoices/invoice/invoice_history.html", "invoices",
                           extra_ctx={"due_soon_filter": bool(due_soon)})


@login_required
def invoice_new(request):
    import json as _json
    from ..models import ConfirmationLetter as _CL
    suggested_number = Invoice.generate_number("hotel")
    active_company = request.session.get("active_company")

    if request.method == "POST":
        invoice = Invoice.objects.create(
            company=request.POST.get("company", "konoz"),
            invoice_type="hotel",
            invoice_number=request.POST.get("invoice_number", ""),
            customer_name=request.POST.get("customer_name", ""),
            issued_date=_parse_date(request.POST.get("issued_date")),
            due_date=_parse_date(request.POST.get("due_date")),
            currency="SAR",
        )
        _save_reservations(invoice, request)
        _save_hotel_payments(invoice, request)

        # Link any CLs that were imported
        cl_ids = request.POST.getlist("linked_cl_ids")
        if cl_ids:
            _CL.objects.filter(pk__in=cl_ids).update(invoice=invoice)

        from ..ai import generate_invoice_summary
        generate_invoice_summary(invoice)
        from ..models import log_activity, ActivityLog
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice {invoice.invoice_number} berhasil dibuat.")
        return redirect("invoice_detail", pk=invoice.pk)

    cl_qs = _CL.objects.select_related("invoice")
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)
    cl_data = _json.dumps([{
        "id": cl.pk,
        "ref": cl.confirmation_number,
        "guest": cl.guest_name,
        "hotel": cl.hotel_name or "-",
        "check_in": cl.check_in.isoformat() if cl.check_in else "",
        "check_out": cl.check_out.isoformat() if cl.check_out else "",
        "total": int(round(cl.total_price)) if cl.total_price else 0,
        "inv": cl.invoice.invoice_number if cl.invoice_id else "",
    } for cl in cl_qs.order_by("-created_at")[:100]])

    return render(request, "invoices/invoice/invoice_form.html", {
        "suggested_number": suggested_number,
        "default_company": active_company or "konoz",
        "cl_data_json": cl_data,
    })


@login_required
def invoice_detail(request, pk):
    from datetime import date as _date
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="hotel")
    reservations = _build_reservation_context(invoice)
    due_alert = None
    if invoice.due_date and invoice.remaining_sar > 0:
        days = (invoice.due_date - _date.today()).days
        if days < 0:
            due_alert = {"type": "red", "msg": f"Jatuh tempo sudah lewat {abs(days)} hari yang lalu."}
        elif days == 0:
            due_alert = {"type": "red", "msg": "Jatuh tempo hari ini!"}
        elif days <= 7:
            due_alert = {"type": "yellow", "msg": f"Jatuh tempo {days} hari lagi."}
    return render(request, "invoices/invoice/invoice_detail.html", {
        "invoice": invoice,
        "reservations": reservations,
        "ai_summary": invoice.ai_summary or None,
        "due_alert": due_alert,
    })


@login_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="hotel")

    if request.method == "POST":
        from ..models import log_activity, ActivityLog

        def _res_snapshot(inv):
            rows = []
            for r in inv.reservations.order_by('id'):
                rows.append(f"{r.hotel} {r.check_in}–{r.check_out} ({int(r.total_sar or 0)} SAR)")
            return ' | '.join(rows) if rows else '—'

        _before = {
            'Nama Customer':    invoice.customer_name,
            'No. Invoice':      invoice.invoice_number,
            'Tgl. Terbit':      str(invoice.issued_date or ''),
            'Tgl. Jatuh Tempo': str(invoice.due_date or ''),
            'Company':          invoice.company,
            'Reservasi':        _res_snapshot(invoice),
        }
        invoice.company = request.POST.get("company", "konoz")
        invoice.invoice_number = request.POST.get("invoice_number", "")
        invoice.customer_name = request.POST.get("customer_name", "")
        invoice.issued_date = _parse_date(request.POST.get("issued_date"))
        invoice.due_date = _parse_date(request.POST.get("due_date"))
        invoice.save()

        invoice.reservations.all().delete()
        invoice.payments.all().delete()
        _save_reservations(invoice, request)
        _save_hotel_payments(invoice, request)
        from ..ai import generate_invoice_summary
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

    return render(request, "invoices/invoice/invoice_form.html", {"invoice": invoice, "edit": True})


@login_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="hotel")
    if request.method == "POST":
        num = invoice.invoice_number
        invoice.delete()
        from ..models import log_activity, ActivityLog
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Hotel', num, invoice.company)
        messages.success(request, f"Invoice {num} berhasil dihapus.")
        return redirect("invoice_list")
    return render(request, "invoices/partials/confirm_delete.html", {"object": invoice, "type": "Invoice Hotel"})


@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type="hotel")
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
        template="invoices/invoice/invoice_list_pdf.html",
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
    original = get_object_or_404(Invoice, pk=pk, invoice_type="hotel")
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
