import csv
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..ai import generate_cl_summary
from ..models import ActivityLog, ConfirmationLetter, Hotel, Invoice, Reservation, Room, log_activity
from .helpers import _paginated_list, _parse_date, _render_list_pdf
from .pdf import _logo_file_url, _render_cl_pdf


@login_required
def cl_list(request):
    active_company = request.session.get("active_company")
    base_qs = ConfirmationLetter.objects.filter(company=active_company) if active_company else ConfirmationLetter.objects.all()

    q             = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').upper()
    date_from     = request.GET.get('date_from', '').strip()
    date_to       = request.GET.get('date_to', '').strip()

    qs = base_qs
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q) |
            Q(hotel_name__icontains=q) |
            Q(confirmation_number__icontains=q)
        )
    if status_filter in ('DEFINITE', 'TENTATIVE', 'CANCELLED'):
        qs = qs.filter(reservation_status=status_filter)
    if date_from:
        qs = qs.filter(check_in__gte=date_from)
    if date_to:
        qs = qs.filter(check_in__lte=date_to)

    active_filters = sum(bool(x) for x in [status_filter, date_from, date_to])
    counts = {
        'all':       base_qs.count(),
        'definite':  base_qs.filter(reservation_status='DEFINITE').count(),
        'tentative': base_qs.filter(reservation_status='TENTATIVE').count(),
        'cancelled': base_qs.filter(reservation_status='CANCELLED').count(),
    }
    return _paginated_list(request, qs, "hw/cl/cl_history.html", "letters",
                           extra_ctx={
                               'status_filter':  status_filter,
                               'date_from':      date_from,
                               'date_to':        date_to,
                               'active_filters': active_filters,
                               'counts':         counts,
                           })


@login_required
def cl_new(request):
    suggested_number = ConfirmationLetter.generate_number()
    if request.method == "POST":
        check_in = _parse_date(request.POST.get("check_in"))
        check_out = _parse_date(request.POST.get("check_out"))

        if check_in and check_out and check_out < check_in:
            messages.error(request, "Check-out tidak boleh sebelum check-in.")
            hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
            return render(request, "hw/cl/cl_form.html", {
                "suggested_number": suggested_number,
                "default_company": request.session.get("active_company", "konoz"),
                "form_data": request.POST,
                "hotels": hotels,
            })

        confirmation_number = request.POST.get("confirmation_number", "")
        if ConfirmationLetter.objects.filter(confirmation_number=confirmation_number).exists():
            messages.error(request, f"Nomor CL '{confirmation_number}' sudah digunakan.")
            hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
            return render(request, "hw/cl/cl_form.html", {
                "suggested_number": confirmation_number,
                "default_company": request.session.get("active_company", "konoz"),
                "form_data": request.POST,
                "hotels": hotels,
            })

        cl = ConfirmationLetter.objects.create(
            company=request.POST.get("company", "konoz"),
            hotel_name=request.POST.get("hotel_name", ""),
            guest_name=request.POST.get("guest_name", ""),
            guest_phone=request.POST.get("guest_phone", ""),
            check_in=check_in,
            check_out=check_out,
            confirmation_number=confirmation_number,
            reservation_status=request.POST.get("reservation_status", "DEFINITE"),
            note=request.POST.get("note", ""),
        )
        _save_cl_rooms(cl, request)
        generate_cl_summary(cl)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'CL', cl.confirmation_number, cl.company)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} berhasil dibuat.")
        return redirect("cl_detail", pk=cl.pk)

    hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
    return render(request, "hw/cl/cl_form.html", {
        "suggested_number": suggested_number,
        "default_company": request.session.get("active_company", "konoz"),
        "hotels": hotels,
    })


@login_required
def cl_detail(request, pk):
    cl = get_object_or_404(ConfirmationLetter, pk=pk)
    return render(request, "hw/cl/cl_detail.html", {
        "cl": cl,
        "ai_summary": cl.ai_summary or None,
    })


@login_required
def cl_edit(request, pk):
    cl = get_object_or_404(ConfirmationLetter, pk=pk)

    if request.method == "POST":
        check_in = _parse_date(request.POST.get("check_in"))
        check_out = _parse_date(request.POST.get("check_out"))

        if check_in and check_out and check_out < check_in:
            messages.error(request, "Check-out tidak boleh sebelum check-in.")
            hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
            return render(request, "hw/cl/cl_form.html", {"cl": cl, "edit": True, "hotels": hotels})

        def _room_snapshot(rooms_qs):
            rows = [f"{r.room_type} x{r.quantity} @ {int(r.price or 0)}" for r in rooms_qs.order_by('id')]
            return ' | '.join(rows) if rows else '—'

        _before = {
            'Hotel':     cl.hotel_name,
            'Tamu':      cl.guest_name,
            'No. Telp':  cl.guest_phone,
            'Check-in':  str(cl.check_in or ''),
            'Check-out': str(cl.check_out or ''),
            'Status':    cl.reservation_status,
            'Company':   cl.company,
            'Kamar':     _room_snapshot(cl.rooms.all()),
        }

        new_number = request.POST.get("confirmation_number", "")
        if ConfirmationLetter.objects.filter(confirmation_number=new_number).exclude(pk=cl.pk).exists():
            messages.error(request, f"Nomor CL '{new_number}' sudah digunakan.")
            hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
            return render(request, "hw/cl/cl_form.html", {"cl": cl, "edit": True, "hotels": hotels, "form_data": request.POST})

        cl.company = request.POST.get("company", "konoz")
        cl.hotel_name = request.POST.get("hotel_name", "")
        cl.guest_name = request.POST.get("guest_name", "")
        cl.guest_phone = request.POST.get("guest_phone", "")
        cl.check_in = check_in
        cl.check_out = check_out
        cl.confirmation_number = new_number
        cl.reservation_status = request.POST.get("reservation_status", "DEFINITE")
        cl.note = request.POST.get("note", "")
        cl.save()

        cl.rooms.all().delete()
        _save_cl_rooms(cl, request)
        generate_cl_summary(cl)

        _after = {
            'Hotel':     cl.hotel_name,
            'Tamu':      cl.guest_name,
            'No. Telp':  cl.guest_phone,
            'Check-in':  str(cl.check_in or ''),
            'Check-out': str(cl.check_out or ''),
            'Status':    cl.reservation_status,
            'Company':   cl.company,
            'Kamar':     _room_snapshot(cl.rooms.all()),
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'CL', cl.confirmation_number, cl.company, changes)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} berhasil diperbarui.")
        return redirect("cl_detail", pk=cl.pk)

    hotels = json.dumps(list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")))
    return render(request, "hw/cl/cl_form.html", {"cl": cl, "edit": True, "hotels": hotels})


@login_required
def cl_delete(request, pk):
    cl = get_object_or_404(ConfirmationLetter, pk=pk)
    if request.method == "POST":
        num = cl.confirmation_number
        cl.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'CL', num, cl.company)
        messages.success(request, f"Confirmation Letter {num} berhasil dihapus.")
        return redirect("cl_list")
    return render(request, "hw/partials/confirm_delete.html", {"object": cl, "type": "Confirmation Letter"})


@login_required
def cl_pdf(request, pk):
    cl = get_object_or_404(ConfirmationLetter, pk=pk)
    return _render_cl_pdf(cl)


@login_required
def cl_list_pdf(request):
    active_company = request.session.get("active_company")
    qs = ConfirmationLetter.objects.filter(company=active_company) if active_company else ConfirmationLetter.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q) |
            Q(hotel_name__icontains=q) |
            Q(confirmation_number__icontains=q)
        )
    letters = list(qs)
    total_rooms  = sum(cl.total_rooms for cl in letters)
    total_nights = sum(cl.num_nights for cl in letters)
    total_sar    = sum(cl.total_price or 0 for cl in letters)
    total_paid   = sum(cl.paid_sar for cl in letters)
    total_remain = sum(cl.remaining_sar for cl in letters)
    return _render_list_pdf(
        request, qs,
        template="hw/cl/cl_list_pdf.html",
        filename="confirmation_letters.pdf",
        extra_ctx={
            "letters":       letters,
            "total_rooms":   total_rooms,
            "total_nights":  total_nights,
            "total_sar":     total_sar,
            "total_paid":    total_paid,
            "total_remain":  total_remain,
            "logo_rel_path": _logo_file_url(active_company or "konoz"),
        },
    )


@login_required
def cl_export_csv(request):
    active_company = request.session.get("active_company")
    qs = ConfirmationLetter.objects.filter(company=active_company) if active_company else ConfirmationLetter.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q) |
            Q(hotel_name__icontains=q) |
            Q(confirmation_number__icontains=q)
        )
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="confirmation_letters.csv"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['No CL', 'Company', 'Guest', 'Hotel', 'Check-in', 'Check-out', 'Total SAR', 'Status', 'Note'])
    for cl in qs:
        writer.writerow([
            cl.confirmation_number, cl.company, cl.guest_name, cl.hotel_name,
            cl.check_in or '', cl.check_out or '',
            cl.total_price or 0, cl.reservation_status, cl.note or '',
        ])
    return response


@login_required
def cl_duplicate(request, pk):
    original = get_object_or_404(ConfirmationLetter, pk=pk)
    new_num = ConfirmationLetter.generate_number()
    new_cl = ConfirmationLetter.objects.create(
        company=original.company,
        hotel_name=original.hotel_name,
        guest_name=original.guest_name,
        guest_phone=original.guest_phone,
        check_in=original.check_in,
        check_out=original.check_out,
        confirmation_number=new_num,
        reservation_status=original.reservation_status,
        note=original.note,
    )
    for room in original.rooms.all():
        Room.objects.create(
            cl=new_cl,
            room_type=room.room_type,
            meals=room.meals,
            quantity=room.quantity,
            price=room.price,
        )
    messages.success(request, f"CL diduplikasi sebagai {new_num} (dari {original.confirmation_number}).")
    return redirect("cl_edit", pk=new_cl.pk)


@login_required
@require_POST
def invoice_from_cls(request):
    cl_ids = request.POST.getlist("cl_ids")
    if not cl_ids:
        messages.error(request, "Pilih minimal satu CL.")
        return redirect("cl_list")

    cls = ConfirmationLetter.objects.filter(pk__in=cl_ids)
    if not cls.exists():
        messages.error(request, "CL tidak ditemukan.")
        return redirect("cl_list")

    first_cl = cls.order_by('created_at').first()
    invoice = Invoice.objects.create(
        company=first_cl.company,
        invoice_type="hotel",
        invoice_number=Invoice.generate_number("hotel"),
        customer_name=first_cl.guest_name,
        issued_date=date.today(),
        currency="SAR",
    )

    for cl in cls:
        Reservation.objects.create(
            invoice=invoice,
            reservation_number=cl.confirmation_number,
            hotel=cl.hotel_name or "-",
            check_in=cl.check_in,
            check_out=cl.check_out,
            total_sar=int(round(cl.total_price)) if cl.total_price else 0,
        )
        cl.invoice = invoice
        cl.save(update_fields=["invoice"])

    messages.success(request, f"Invoice {invoice.invoice_number} berhasil dibuat dari {cls.count()} CL.")
    return redirect("invoice_edit", pk=invoice.pk)


def _save_cl_rooms(cl, request):
    room_types  = request.POST.getlist("room_type")
    room_meals  = request.POST.getlist("room_meals")
    num_rooms   = request.POST.getlist("num_rooms")
    room_prices = request.POST.getlist("room_price")
    for i, rt in enumerate(room_types):
        if not rt:
            continue
        Room.objects.create(
            cl=cl,
            room_type=rt,
            meals=room_meals[i] if i < len(room_meals) else "",
            quantity=max(1, int(num_rooms[i])) if i < len(num_rooms) and num_rooms[i] else 1,
            price=max(0, float(room_prices[i])) if i < len(room_prices) and room_prices[i] else 0,
        )
