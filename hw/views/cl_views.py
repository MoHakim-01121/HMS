import csv
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Client, ConfirmationLetter, Hotel, Invoice, Reservation, Room, log_activity
from .helpers import _is_mobile, _page_range_display, _paginated_list, _parse_date, _render_list_pdf
from .pdf import _logo_file_url, _render_cl_pdf


def _get_cl(request, pk, qs=None):
    """Fetch a ConfirmationLetter by pk, scoped to the active company (consistent
    with the list/invoice/client views) so a CL from another company cannot be
    opened by URL while a company is selected."""
    active_company = request.session.get("active_company")
    qs = qs if qs is not None else ConfirmationLetter.objects.all()
    if active_company:
        qs = qs.filter(company=active_company)
    return get_object_or_404(qs, pk=pk)


@login_required
def cl_list(request):
    active_company = request.session.get("active_company")
    base_qs = (ConfirmationLetter.objects.filter(company=active_company) if active_company else ConfirmationLetter.objects.all()).select_related('invoice').prefetch_related('rooms')

    q           = request.GET.get('q', '').strip()
    status_list = [s.upper() for s in request.GET.getlist('status') if s.upper() in ('DEFINITE', 'TENTATIVE', 'CANCELLED')]
    date_from   = _parse_date(request.GET.get('date_from', '').strip())
    date_to     = _parse_date(request.GET.get('date_to', '').strip())
    sort        = request.GET.get('sort', 'check_in')

    _sort_map = {
        'check_in':    'check_in',
        '-check_in':   '-check_in',
        'guest_name':  'guest_name',
        '-created_at': '-created_at',
    }
    _sort_labels = {
        'check_in':    'Check-in (oldest)',
        '-check_in':   'Check-in (newest)',
        'guest_name':  'Guest name (A–Z)',
        '-created_at': 'Created (newest)',
    }

    qs = base_qs
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q) |
            Q(hotel_name__icontains=q) |
            Q(confirmation_number__icontains=q)
        )
    if status_list:
        qs = qs.filter(reservation_status__in=status_list)
    if date_from:
        qs = qs.filter(check_in__gte=date_from)
    if date_to:
        qs = qs.filter(check_in__lte=date_to)

    qs = qs.order_by(_sort_map.get(sort, '-check_in'))

    active_filters = len(status_list) + bool(date_from) + bool(date_to)
    _status_counts = {
        row['reservation_status']: row['n']
        for row in base_qs.values('reservation_status').annotate(n=Count('id'))
    }
    counts = {
        'all':       sum(_status_counts.values()),
        'definite':  _status_counts.get('DEFINITE', 0),
        'tentative': _status_counts.get('TENTATIVE', 0),
        'cancelled': _status_counts.get('CANCELLED', 0),
    }
    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    letters = [{
        "id": cl.id,
        "confirmation_number": cl.confirmation_number,
        "reservation_status": cl.reservation_status,
        "guest_name": cl.guest_name,
        "hotel_name": cl.hotel_name,
        "check_in": cl.check_in.strftime("%d/%m/%Y") if cl.check_in else None,
        "check_out": cl.check_out.strftime("%d/%m/%Y") if cl.check_out else None,
        "total_price": int(round(cl.total_price)) if cl.total_price else None,
        "has_invoice": bool(cl.invoice_id),
        "invoice_number": cl.invoice.invoice_number if cl.invoice_id else "",
    } for cl in page_obj]

    return inertia_render(request, "Cl/List", props={
        "letters": letters,
        "total_count": paginator.count,
        "q": q,
        "status_list": [s.lower() for s in status_list],
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "sort": sort,
        "sort_label": _sort_labels.get(sort, 'Check-in (terbaru)'),
        "sort_labels": _sort_labels,
        "active_filters": active_filters,
        "counts": counts,
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


def _form_context_data():
    return {
        "hotels": list(Hotel.objects.filter(is_active=True).values("name", "company", "city").order_by("company", "city", "name")),
        "clients": list(Client.objects.filter(is_active=True).values("id", "name", "company").order_by("company", "name")),
    }


def _validate_cl(data, exclude_pk=None):
    errors = {}
    check_in = _parse_date(data.get("check_in"))
    check_out = _parse_date(data.get("check_out"))
    if check_in and check_out and check_out < check_in:
        errors["check_out"] = "Check-out cannot be before check-in."
    number = data.get("confirmation_number", "")
    qs = ConfirmationLetter.objects.filter(confirmation_number=number)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if number and qs.exists():
        errors["confirmation_number"] = f"CL number '{number}' is already in use."
    return errors


def _cl_echo(data):
    try:
        rooms = json.loads(data.get("rooms", "[]") or "[]")
    except (ValueError, TypeError):
        rooms = []
    return {
        "company": data.get("company", "konoz"),
        "client_id": data.get("client_id", ""),
        "hotel_name": data.get("hotel_name", ""),
        "guest_name": data.get("guest_name", ""),
        "guest_phone": data.get("guest_phone", ""),
        "check_in": data.get("check_in", ""),
        "check_out": data.get("check_out", ""),
        "confirmation_number": data.get("confirmation_number", ""),
        "reservation_status": data.get("reservation_status", "DEFINITE"),
        "note": data.get("note", ""),
        "rooms": rooms,
    }


def cl_new(request):
    suggested_number = ConfirmationLetter.generate_number()
    default_company = request.session.get("active_company", "konoz")
    if request.method == "POST":
        errors = _validate_cl(request.POST)
        if errors:
            return inertia_render(request, "Cl/Form", props={
                "cl": _cl_echo(request.POST), "edit": False, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", suggested_number),
                "default_company": default_company, **_form_context_data(),
            })
        client_id = request.POST.get("client_id") or None
        guest_name = request.POST.get("guest_name", "").strip()
        if not guest_name and client_id:
            guest_name = Client.objects.filter(pk=client_id).values_list("name", flat=True).first() or ""
        cl = ConfirmationLetter.objects.create(
            company=request.POST.get("company", "konoz"),
            client_id=client_id,
            hotel_name=request.POST.get("hotel_name", ""),
            guest_name=guest_name,
            guest_phone=request.POST.get("guest_phone", ""),
            check_in=_parse_date(request.POST.get("check_in")),
            check_out=_parse_date(request.POST.get("check_out")),
            confirmation_number=request.POST.get("confirmation_number", ""),
            reservation_status=request.POST.get("reservation_status", "DEFINITE"),
            note=request.POST.get("note", ""),
        )
        _save_cl_rooms(cl, request)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'CL', cl.confirmation_number, cl.company)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} created successfully.")
        return redirect("cl_detail", pk=cl.pk)

    return inertia_render(request, "Cl/Form", props={
        "cl": None, "edit": False,
        "suggested_number": suggested_number, "default_company": default_company,
        **_form_context_data(),
    })


@login_required
def cl_detail(request, pk):
    cl = _get_cl(
        request, pk,
        ConfirmationLetter.objects.select_related('client', 'invoice', 'penalty')
        .prefetch_related('rooms', 'attachments'),
    )
    rooms = [{
        "room_type": r.room_type,
        "meals": r.meals,
        "quantity": r.quantity,
        "price": int(round(float(r.price))),
        "subtotal": int(round(r.subtotal)),
    } for r in cl.rooms.all()]

    try:
        pen = cl.penalty
    except ObjectDoesNotExist:
        pen = None
    penalty = None
    if pen:
        penalty = {
            "pk": pen.pk,
            "penalty_number": pen.penalty_number,
            "cancellation_date": pen.cancellation_date.strftime("%d/%m/%Y") if pen.cancellation_date else None,
            "penalty_amount": int(round(float(pen.penalty_amount))),
            "penalty_currency": pen.penalty_currency,
            "is_paid": pen.is_paid,
        }

    attachments = [{
        "id": a.id, "icon": a.icon, "url": a.file.url, "name": a.name, "size": a.size,
    } for a in cl.attachments.all()]

    return inertia_render(request, "Cl/Detail", props={
        "cl": {
            "pk": cl.pk,
            "confirmation_number": cl.confirmation_number,
            "guest_name": cl.guest_name,
            "guest_phone": cl.guest_phone,
            "hotel_name": cl.hotel_name,
            "reservation_status": cl.reservation_status,
            "check_in": cl.check_in.strftime("%d/%m/%Y") if cl.check_in else None,
            "check_out": cl.check_out.strftime("%d/%m/%Y") if cl.check_out else None,
            "num_nights": cl.num_nights,
            "num_guests": cl.num_guests,
            "total_price": int(round(cl.total_price)) if cl.total_price else 0,
            "note": cl.note,
            "client": {"pk": cl.client.pk, "name": cl.client.name} if cl.client_id else None,
            "invoice": {"pk": cl.invoice.pk, "invoice_number": cl.invoice.invoice_number} if cl.invoice_id else None,
        },
        "rooms": rooms,
        "penalty": penalty,
        "attachments": attachments,
    })


@login_required
def cl_edit(request, pk):
    cl = _get_cl(request, pk)

    def _room_snapshot(rooms_qs):
        rows = [f"{r.room_type} x{r.quantity} @ {int(r.price or 0)}" for r in rooms_qs.order_by('id')]
        return ' | '.join(rows) if rows else '—'

    if request.method == "POST":
        errors = _validate_cl(request.POST, exclude_pk=cl.pk)
        if errors:
            echo = _cl_echo(request.POST); echo["id"] = cl.pk
            return inertia_render(request, "Cl/Form", props={
                "cl": echo, "edit": True, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", cl.confirmation_number),
                "default_company": cl.company, **_form_context_data(),
            })

        _before = {
            'Hotel':     cl.hotel_name,
            'Guest':     cl.guest_name,
            'Phone':     cl.guest_phone,
            'Check-in':  str(cl.check_in or ''),
            'Check-out': str(cl.check_out or ''),
            'Status':    cl.reservation_status,
            'Company':   cl.company,
            'Rooms':     _room_snapshot(cl.rooms.all()),
        }

        cl.company = request.POST.get("company", "konoz")
        cl.client_id = request.POST.get("client_id") or None
        cl.hotel_name = request.POST.get("hotel_name", "")
        guest_name = request.POST.get("guest_name", "").strip()
        if not guest_name and cl.client_id:
            guest_name = Client.objects.filter(pk=cl.client_id).values_list("name", flat=True).first() or ""
        cl.guest_name = guest_name
        cl.guest_phone = request.POST.get("guest_phone", "")
        cl.check_in = _parse_date(request.POST.get("check_in"))
        cl.check_out = _parse_date(request.POST.get("check_out"))
        cl.confirmation_number = request.POST.get("confirmation_number", "")
        cl.reservation_status = request.POST.get("reservation_status", "DEFINITE")
        cl.note = request.POST.get("note", "")
        cl.save()

        cl.rooms.all().delete()
        _save_cl_rooms(cl, request)

        _after = {
            'Hotel':     cl.hotel_name,
            'Guest':     cl.guest_name,
            'Phone':     cl.guest_phone,
            'Check-in':  str(cl.check_in or ''),
            'Check-out': str(cl.check_out or ''),
            'Status':    cl.reservation_status,
            'Company':   cl.company,
            'Rooms':     _room_snapshot(cl.rooms.all()),
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'CL', cl.confirmation_number, cl.company, changes)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} updated successfully.")
        return redirect("cl_detail", pk=cl.pk)

    rooms = [{
        "room_type": r.room_type, "meals": r.meals,
        "quantity": r.quantity, "price": int(round(float(r.price))),
    } for r in cl.rooms.all()]
    return inertia_render(request, "Cl/Form", props={
        "cl": {
            "id": cl.pk, "company": cl.company,
            "client_id": cl.client_id or "", "hotel_name": cl.hotel_name,
            "guest_name": cl.guest_name, "guest_phone": cl.guest_phone,
            "check_in": cl.check_in.isoformat() if cl.check_in else "",
            "check_out": cl.check_out.isoformat() if cl.check_out else "",
            "confirmation_number": cl.confirmation_number,
            "reservation_status": cl.reservation_status, "note": cl.note,
            "rooms": rooms,
        },
        "edit": True, "suggested_number": cl.confirmation_number,
        "default_company": cl.company, **_form_context_data(),
    })


@login_required
def cl_delete(request, pk):
    cl = _get_cl(request, pk)
    if request.method == "POST":
        num = cl.confirmation_number
        cl.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'CL', num, cl.company)
        messages.success(request, f"Confirmation Letter {num} deleted successfully.")
        return redirect("cl_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("cl_list")


@login_required
def cl_pdf(request, pk):
    cl = _get_cl(request, pk)
    return _render_cl_pdf(cl)


_SORT_MAP = {
    '-check_in':   '-check_in',
    'check_in':    'check_in',
    'guest_name':  'guest_name',
    '-created_at': '-created_at',
}

def _filter_cl_qs(qs, request):
    q           = request.GET.get('q', '').strip()
    status_list = [s.upper() for s in request.GET.getlist('status') if s.upper() in ('DEFINITE', 'TENTATIVE', 'CANCELLED')]
    date_from   = _parse_date(request.GET.get('date_from', '').strip())
    date_to     = _parse_date(request.GET.get('date_to', '').strip())
    sort        = request.GET.get('sort', '-check_in')
    if q:
        qs = qs.filter(Q(guest_name__icontains=q) | Q(hotel_name__icontains=q) | Q(confirmation_number__icontains=q))
    if status_list:
        qs = qs.filter(reservation_status__in=status_list)
    if date_from:
        qs = qs.filter(check_in__gte=date_from)
    if date_to:
        qs = qs.filter(check_in__lte=date_to)
    return qs.order_by(_SORT_MAP.get(sort, '-check_in'))


@login_required
def cl_list_pdf(request):
    active_company = request.session.get("active_company")
    qs = ConfirmationLetter.objects.filter(company=active_company) if active_company else ConfirmationLetter.objects.all()
    qs = _filter_cl_qs(qs, request)
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
    qs = _filter_cl_qs(qs, request)
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
    original = _get_cl(request, pk)
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
    messages.success(request, f"CL duplicated as {new_num} (from {original.confirmation_number}).")
    return redirect("cl_edit", pk=new_cl.pk)


@login_required
@require_POST
def invoice_from_cls(request):
    cl_ids = request.POST.getlist("cl_ids")
    if not cl_ids:
        messages.error(request, "Select at least one CL.")
        return redirect("cl_list")

    cls = ConfirmationLetter.objects.filter(pk__in=cl_ids)
    if not cls.exists():
        messages.error(request, "CL not found.")
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

    messages.success(request, f"Invoice {invoice.invoice_number} created from {cls.count()} CL(s).")
    return redirect("invoice_edit", pk=invoice.pk)


def _save_cl_rooms(cl, request):
    try:
        rooms = json.loads(request.POST.get("rooms", "[]") or "[]")
    except (ValueError, TypeError):
        rooms = []
    for r in rooms:
        rt = (r.get("room_type") or "").strip()
        if not rt:
            continue
        try:
            qty = max(1, int(r.get("quantity") or 1))
        except (ValueError, TypeError):
            qty = 1
        try:
            price = max(0, float(r.get("price") or 0))
        except (ValueError, TypeError):
            price = 0
        Room.objects.create(cl=cl, room_type=rt, meals=(r.get("meals") or ""), quantity=qty, price=price)
