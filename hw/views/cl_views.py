import json
import logging
from datetime import date

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import (
    ActivityLog, Client, ConfirmationLetter, Hotel, Invoice, MealPlan, Reservation, ReservationStatus, Room,
    RoomType, log_activity,
)
from ..models.confirmation import guest_name_expr
from ..permissions import require_perm
from ..i18n import tr
from .helpers import _is_mobile, _parse_date, _parse_search_tokens, _render_list_pdf, csv_export_response, pagination_props, snapshot_fields, track_changes
from .pdf import _logo_file_url, _render_cl_pdf
from ..utils import round_half_up
from ..finance.reservation_rules import reservation_total_for_cl

logger = logging.getLogger(__name__)


def _get_cl(request, pk, qs=None):
    """Fetch a ConfirmationLetter by pk."""
    qs = qs if qs is not None else ConfirmationLetter.objects.all()
    return get_object_or_404(qs, pk=pk)


_SORT_MAP = {
    '-check_in':   ['-check_in'],
    'check_in':    ['check_in'],
    # Nama tampil client (brand, atau nama perusahaan) dibaca lewat FK.
    'guest_name':  [guest_name_expr().asc(), 'pk'],
    '-created_at': ['-created_at'],
}


def _order(qs, sort, default='-check_in'):
    return qs.order_by(*_SORT_MAP.get(sort, _SORT_MAP[default]))


def _cl_filter_params(request):
    """Read the standard CL list filters (q/status/date range) off the querystring."""
    return (
        request.GET.get('q', '').strip(),
        [s.upper() for s in request.GET.getlist('status') if s.upper() in ('DEFINITE', 'TENTATIVE', 'CANCELLED')],
        _parse_date(request.GET.get('date_from', '').strip()),
        _parse_date(request.GET.get('date_to', '').strip()),
    )


def _apply_cl_filters(qs, q, status_list, date_from, date_to):
    if q:
        tokens = _parse_search_tokens(q)
        if tokens:
            combined = Q()
            for token in tokens:
                combined |= ConfirmationLetter.objects.name_matches(token)
            qs = qs.filter(combined)
    if status_list:
        qs = qs.filter(reservation_status__in=status_list)
    if date_from:
        qs = qs.filter(check_in__gte=date_from)
    if date_to:
        qs = qs.filter(check_in__lte=date_to)
    return qs


def _filter_cl_qs(qs, request):
    q, status_list, date_from, date_to = _cl_filter_params(request)
    sort = request.GET.get('sort', '-check_in')
    qs = _apply_cl_filters(qs, q, status_list, date_from, date_to)
    return _order(qs, sort)


@require_perm('cl', 'view')
def cl_list(request):
    base_qs = (
        ConfirmationLetter.objects.all()
        .defer('note').select_related('invoice', 'client', 'hotel')
        .prefetch_related('rooms__room_type_ref')
    )

    q, status_list, date_from, date_to = _cl_filter_params(request)
    sort = request.GET.get('sort', 'check_in')

    _sort_labels = {
        'check_in':    tr(request, 'Check-in (oldest)', 'Check-in (terlama)'),
        '-check_in':   tr(request, 'Check-in (newest)', 'Check-in (terbaru)'),
        'guest_name':  tr(request, 'Guest name (A–Z)', 'Nama tamu (A–Z)'),
        '-created_at': tr(request, 'Created (newest)', 'Dibuat (terbaru)'),
    }

    qs = _apply_cl_filters(base_qs, q, status_list, date_from, date_to)
    qs = _order(qs, sort)

    # Counts filter GROUPS in use, not individual values (doc 02b "Badge
    # hitung"): three checked statuses is still one group, a date range is
    # one more — so the badge reads 2, not 5.
    active_filters = bool(status_list) + bool(date_from or date_to)
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
        "num_nights": cl.num_nights,
        "total_rooms": cl.total_rooms,
        "total_price": round_half_up(cl.total_price) if cl.total_price else None,
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
        "sort_label": _sort_labels.get(sort, tr(request, 'Check-in (newest)', 'Check-in (terbaru)')),
        "sort_labels": _sort_labels,
        "active_filters": active_filters,
        "counts": counts,
        "pagination": pagination_props(page_obj),
    })


def _form_context_data():
    hotels = [{
        "id": h.id, "name": h.name, "city": h.city,
        # Both lists filter in Python rather than with .filter(): a filter()
        # on a prefetched relation re-queries per hotel, an N+1 across the
        # whole catalog on every CL form open.
        "room_types": [
            {"id": rt.id, "name": rt.name, "capacity": rt.capacity}
            for rt in h.room_types.all() if rt.is_active
        ],
        "meal_plans": [
            {"code": mp.code, "name": mp.name}
            for mp in h.meal_plans.all() if mp.is_active
        ],
    } for h in Hotel.objects.filter(is_active=True).prefetch_related('room_types', 'meal_plans').order_by('city', 'name')]
    return {
        "hotels": hotels,
        "clients": list(Client.objects.filter(is_active=True).values("id", "name", "brand").order_by("name")),
    }


def _resolve_hotel_id(request):
    hotel_id = request.POST.get("hotel_id") or None
    if hotel_id and not Hotel.objects.filter(pk=hotel_id).exists():
        hotel_id = None
    return hotel_id


def _posted_rooms(data):
    try:
        rooms = json.loads(data.get("rooms", "[]") or "[]")
    except (ValueError, TypeError):
        rooms = []
    return [r for r in rooms if isinstance(r, dict) and ((r.get("room_type") or "").strip() or r.get("room_type_id"))]


def _validate_cl(data, exclude_pk=None):
    errors = {}
    # Reservasi selalu milik satu client dan satu hotel dari master (skema v2):
    # nama yang diketik tanpa memilih dari daftar tidak lagi disimpan sebagai teks.
    client_id = data.get("client_id") or None
    if not client_id or not Client.objects.filter(pk=client_id).exists():
        errors["guest_name"] = "Choose the client from the list (add the client first if it is new)."
    hotel_id = data.get("hotel_id") or None
    if not hotel_id or not Hotel.objects.filter(pk=hotel_id).exists():
        errors["hotel_name"] = "Choose the hotel from the list (add the hotel first if it is new)."
    check_in = _parse_date(data.get("check_in"))
    check_out = _parse_date(data.get("check_out"))
    if not check_in:
        errors["check_in"] = "Check-in date is required."
    if not check_out:
        errors["check_out"] = "Check-out date is required."
    status = (data.get("reservation_status") or "DEFINITE").upper()
    if status not in ReservationStatus.values:
        errors["reservation_status"] = "Unknown reservation status."
    rooms = _posted_rooms(data)
    if not rooms:
        errors["rooms"] = "Add at least one room."
    elif hotel_id and "hotel_name" not in errors:
        valid = set(RoomType.objects.filter(hotel_id=hotel_id).values_list("pk", flat=True))
        for r in rooms:
            try:
                ok = int(r.get("room_type_id") or 0) in valid
            except (ValueError, TypeError):
                ok = False
            if not ok:
                errors["rooms"] = "Choose each room type from this hotel's catalog."
                break
    if check_in and check_out and check_out <= check_in:
        # <=, not <: mirrors the DB CheckConstraint (cl_check_out_after_check_in,
        # v2.0 §11) so a same-day date surfaces as a clean form error instead
        # of an IntegrityError from the save.
        errors["check_out"] = "Check-out must be after check-in."
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
        "client_id": data.get("client_id", ""),
        "hotel_name": data.get("hotel_name", ""),
        "hotel_id": data.get("hotel_id", ""),
        "guest_name": data.get("guest_name", ""),
        "guest_phone": data.get("guest_phone", ""),
        "check_in": data.get("check_in", ""),
        "check_out": data.get("check_out", ""),
        "confirmation_number": data.get("confirmation_number", ""),
        "reservation_status": data.get("reservation_status", "DEFINITE"),
        "note": data.get("note", ""),
        "rooms": rooms,
    }


@require_perm('cl', 'create')
def cl_new(request):
    suggested_number = ConfirmationLetter.suggest_number()
    if request.method == "POST":
        errors = _validate_cl(request.POST)
        if errors:
            return inertia_render(request, "Cl/Form", props={
                "cl": _cl_echo(request.POST), "edit": False, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", suggested_number),
                **_form_context_data(),
            })
        with transaction.atomic():
            cl = ConfirmationLetter.objects.create(
                client_id=request.POST.get("client_id"),
                hotel_id=_resolve_hotel_id(request),
                guest_phone=request.POST.get("guest_phone", ""),
                check_in=_parse_date(request.POST.get("check_in")),
                check_out=_parse_date(request.POST.get("check_out")),
                confirmation_number=request.POST.get("confirmation_number", ""),
                reservation_status=(request.POST.get("reservation_status") or "DEFINITE").upper(),
                note=request.POST.get("note", ""),
            )
            _save_cl_rooms(cl, request)
        ConfirmationLetter.claim_number(cl.confirmation_number)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'CL', cl.confirmation_number)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} created successfully.")
        return redirect("cl_detail", pk=cl.pk)

    return inertia_render(request, "Cl/Form", props={
        "cl": None, "edit": False,
        "suggested_number": suggested_number,
        **_form_context_data(),
    })


@require_perm('cl', 'view')
def cl_detail(request, pk):
    cl = _get_cl(
        request, pk,
        ConfirmationLetter.objects.select_related('client', 'hotel', 'invoice', 'penalty')
        .prefetch_related('rooms__room_type_ref', 'attachments'),
    )
    rooms = [{
        "room_type": r.room_type,
        "meals": r.meals,
        "quantity": r.quantity,
        "price": float(r.price),
        "subtotal": round_half_up(r.subtotal),
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

    log_qs = ActivityLog.objects.filter(
        model_name='CL', object_ref=cl.confirmation_number,
    ).select_related('user').order_by('-timestamp')
    logs = [{
        "action": l.get_action_display(),
        "by": l.user.get_full_name() or l.user.username,
        "changes": l.changes,
        "timestamp": l.timestamp.strftime("%d %b %Y %H:%M"),
    } for l in log_qs]

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
            "total_price": round_half_up(cl.total_price) if cl.total_price else 0,
            "note": cl.note,
            "created_at": cl.created_at.strftime("%d %b %Y") if cl.created_at else None,
            "client": {"pk": cl.client.pk, "name": cl.client.name} if cl.client_id else None,
            "invoice": {"pk": cl.invoice.pk, "invoice_number": cl.invoice.invoice_number} if cl.invoice_id else None,
        },
        "rooms": rooms,
        "penalty": penalty,
        "attachments": attachments,
        "logs": logs,
    })


@require_perm('cl', 'edit')
def cl_edit(request, pk):
    cl = _get_cl(request, pk)

    def _room_snapshot(rooms_qs):
        rows = [f"{r.room_type} x{r.quantity} @ {r.price or 0}" for r in rooms_qs.order_by('id')]
        return ' | '.join(rows) if rows else '—'

    if request.method == "POST":
        errors = _validate_cl(request.POST, exclude_pk=cl.pk)
        if errors:
            echo = _cl_echo(request.POST); echo["id"] = cl.pk
            return inertia_render(request, "Cl/Form", props={
                "cl": echo, "edit": True, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", cl.confirmation_number),
                **_form_context_data(),
            })

        _before = snapshot_fields(cl, ['hotel_name', 'guest_name', 'guest_phone', 'check_in', 'check_out', 'reservation_status'])
        _rooms_before = _room_snapshot(cl.rooms.all())

        cl.client_id = request.POST.get("client_id")
        cl.hotel_id = _resolve_hotel_id(request)
        cl.guest_phone = request.POST.get("guest_phone", "")
        cl.check_in = _parse_date(request.POST.get("check_in"))
        cl.check_out = _parse_date(request.POST.get("check_out"))
        cl.confirmation_number = request.POST.get("confirmation_number", "")
        cl.reservation_status = (request.POST.get("reservation_status") or "DEFINITE").upper()
        cl.note = request.POST.get("note", "")
        cl.save()
        ConfirmationLetter.claim_number(cl.confirmation_number)

        cl.rooms.all().delete()
        _save_cl_rooms(cl, request)

        if cl.invoice_id:
            _sync_invoice_reservation_from_cl(cl, request.user)

        _after = snapshot_fields(cl, ['hotel_name', 'guest_name', 'guest_phone', 'check_in', 'check_out', 'reservation_status'])
        _rooms_after = _room_snapshot(cl.rooms.all())
        changes = track_changes(
            {**_before, 'Rooms': _rooms_before},
            {**_after, 'Rooms': _rooms_after},
            labels={'hotel_name': 'Hotel', 'guest_name': 'Guest', 'guest_phone': 'Phone', 'check_in': 'Check-in', 'check_out': 'Check-out', 'reservation_status': 'Status', 'Rooms': 'Rooms'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'CL', cl.confirmation_number, changes)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} updated successfully.")
        return redirect("cl_detail", pk=cl.pk)

    rooms = [{
        "room_type": r.room_type, "room_type_id": r.room_type_ref_id or "",
        "meals": r.meals, "meal_plan_code": r.meal_plan_id or "",
        "quantity": r.quantity, "price": float(r.price),
    } for r in cl.rooms.all()]
    return inertia_render(request, "Cl/Form", props={
        "cl": {
            "id": cl.pk,
            "client_id": cl.client_id or "", "hotel_name": cl.hotel_name,
            "hotel_id": cl.hotel_id or "",
            "guest_name": cl.guest_name, "guest_phone": cl.guest_phone,
            "check_in": cl.check_in.isoformat() if cl.check_in else "",
            "check_out": cl.check_out.isoformat() if cl.check_out else "",
            "confirmation_number": cl.confirmation_number,
            "reservation_status": cl.reservation_status, "note": cl.note,
            "rooms": rooms,
        },
        "edit": True, "suggested_number": cl.confirmation_number,
        **_form_context_data(),
    })


@require_perm('cl', 'delete')
def cl_delete(request, pk):
    cl = _get_cl(request, pk)
    if request.method == "POST":
        num = cl.confirmation_number
        cl.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'CL', num)
        messages.success(request, f"Confirmation Letter {num} deleted successfully.")
        return redirect("cl_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("cl_list")


@require_perm('cl', 'export')
def cl_pdf(request, pk):
    cl = _get_cl(request, pk)
    return _render_cl_pdf(cl)


@require_perm('cl', 'export')
def cl_list_pdf(request):
    qs = ConfirmationLetter.objects.all()
    qs = _filter_cl_qs(qs, request).with_parties().prefetch_related('rooms__room_type_ref')
    letters = list(qs)
    # One bulk Payment query for all paid totals -- summing cl.paid_sar here
    # used to cost two queries per CL (N+1).
    from ..finance import queries as finance_queries
    paid_map = finance_queries.cl_paid_sar_map(letters)
    total_rooms  = sum(cl.total_rooms for cl in letters)
    total_nights = sum(cl.num_nights for cl in letters)
    total_sar    = sum(cl.total_price or 0 for cl in letters)
    total_paid   = sum(paid_map.values())
    total_remain = sum(
        (round_half_up(cl.total_price) if cl.total_price else 0) - paid_map.get(cl.pk, 0)
        for cl in letters
    )
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
            "logo_rel_path": _logo_file_url(),
        },
    )


@require_perm('cl', 'export')
def cl_list_pdf_v2(request):
    qs = ConfirmationLetter.objects.all()
    qs = _filter_cl_qs(qs, request).with_parties().prefetch_related('rooms__room_type_ref')
    letters = list(qs)
    for cl in letters:
        counts = {}
        for r in cl.rooms.all():
            key = (r.room_type, (r.meals or '').strip())
            counts[key] = counts.get(key, 0) + r.quantity
        cl.room_types = ", ".join(
            f"{n} {t}" + (f" - {m}" if m else "")
            for (t, m), n in counts.items()
        )
    total_rooms  = sum(cl.total_rooms for cl in letters)
    total_sar    = sum(cl.total_price or 0 for cl in letters)
    return _render_list_pdf(
        request, qs,
        template="hw/cl/cl_list_pdf_v2.html",
        filename="confirmation_letters_v2.pdf",
        extra_ctx={
            "letters":       letters,
            "total_rooms":   total_rooms,
            "total_sar":     total_sar,
            "logo_rel_path": _logo_file_url(),
        },
    )


@require_perm('cl', 'export')
def cl_export_csv(request):
    qs = ConfirmationLetter.objects.all()
    qs = _filter_cl_qs(qs, request)
    headers = ['No CL', 'Guest', 'Hotel', 'Check-in', 'Check-out', 'Total Room', 'Night', 'Total SAR', 'Status', 'Note']
    rows = ([
        cl.confirmation_number, cl.guest_name, cl.hotel_name,
        cl.check_in or '', cl.check_out or '',
        cl.total_rooms, cl.num_nights,
        cl.total_price or 0, cl.reservation_status, cl.note or '',
    ] for cl in qs)
    return csv_export_response('confirmation_letters.csv', headers, rows)


@require_perm('cl', 'create')
@transaction.atomic
def cl_duplicate(request, pk):
    original = _get_cl(request, pk)
    new_num = ConfirmationLetter.generate_number()
    # A duplicate is a new booking for the same client and hotel. A board type
    # the hotel has since stopped selling is not carried as a link: it is kept
    # as the room's free-text note instead, so nothing the catalog no longer
    # offers is re-created as a master reference.
    sold_plans = set(MealPlan.objects.filter(hotels__pk=original.hotel_id, is_active=True).values_list('code', flat=True))
    new_cl = ConfirmationLetter.objects.create(
        client_id=original.client_id,
        hotel_id=original.hotel_id,
        guest_phone=original.guest_phone,
        check_in=original.check_in,
        check_out=original.check_out,
        confirmation_number=new_num,
        reservation_status=original.reservation_status,
        note=original.note,
    )
    for room in original.rooms.all():
        keep_plan = room.meal_plan_id in sold_plans
        Room.objects.create(
            cl=new_cl,
            room_type_ref_id=room.room_type_ref_id,
            meal_plan_id=room.meal_plan_id if keep_plan else None,
            note=room.note if keep_plan or not room.meal_plan_id else room.meal_plan_id,
            quantity=room.quantity,
            price=room.price,
        )
    messages.success(request, f"CL duplicated as {new_num} (from {original.confirmation_number}).")
    return redirect("cl_edit", pk=new_cl.pk)


@require_perm('invoice', 'create')
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
    with transaction.atomic():
        invoice = Invoice.objects.create(
            invoice_type="hotel",
            invoice_number=Invoice.generate_number("hotel"),
            customer_name=first_cl.guest_name,
            issued_date=date.today(),
            currency="SAR",
        )

        clients = {cl.client_id for cl in cls if cl.client_id}
        if len(clients) == 1:
            invoice.client_id = next(iter(clients))
            invoice.save(update_fields=["client", "customer_name"])

        for cl in cls:
            total_sar = reservation_total_for_cl(cl)
            Reservation.objects.create(
                invoice=invoice,
                confirmation_letter=cl,
                client_id=cl.client_id,
                reservation_number=cl.confirmation_number,
                hotel=cl.hotel_name or "-",
                check_in=cl.check_in,
                check_out=cl.check_out,
                total_sar=total_sar,
            )
            cl.invoice = invoice
            cl.save(update_fields=["invoice"])

        if invoice.client_id:
            from ..finance.posting import post_invoice_charge
            post_invoice_charge(invoice, created_by=request.user)

    logger.info(
        "ledger: invoice %s created from %d CL(s)",
        invoice.invoice_number, cls.count(),
    )
    messages.success(request, f"Invoice {invoice.invoice_number} created from {cls.count()} CL(s).")
    return redirect("invoice_edit", pk=invoice.pk)


def _save_cl_rooms(cl, request):
    for r in _posted_rooms(request.POST):
        try:
            qty = max(1, int(r.get("quantity") or 1))
        except (ValueError, TypeError):
            qty = 1
        try:
            price = max(0, float(r.get("price") or 0))
        except (ValueError, TypeError):
            price = 0
        # _validate_cl already refused a room type outside this hotel's catalog.
        room_type_ref = RoomType.objects.filter(pk=r.get("room_type_id") or 0, hotel_id=cl.hotel_id).first()
        if room_type_ref is None:
            continue
        # A board code counts only if the hotel actually sells it; anything
        # else (e.g. "BB + late checkout") is kept as the room's free-text
        # note. Room.meals reads the code or the note, so the PDFs, exports
        # and CL detail that show that string keep working untouched.
        meals = (r.get("meals") or "").strip()
        meal_plan_code = (r.get("meal_plan_code") or "").strip() or meals
        meal_plan = MealPlan.objects.filter(
            code=meal_plan_code, is_active=True, hotels__pk=cl.hotel_id,
        ).first() if meal_plan_code else None
        Room.objects.create(
            cl=cl, room_type_ref=room_type_ref, meal_plan=meal_plan,
            note='' if meal_plan else meals[:100], quantity=qty, price=price,
        )


def _sync_invoice_reservation_from_cl(cl, user=None):
    """Update the Invoice's Reservation to match the CL's current data, lalu
    re-post charge jurnal invoice (idempotent-by-content)."""
    from ..models import Reservation
    try:
        reservation = cl.invoice.reservations.get(reservation_number=cl.confirmation_number)
    except Reservation.DoesNotExist:
        return
    with transaction.atomic():
        reservation.check_in = cl.check_in
        reservation.check_out = cl.check_out
        reservation.total_sar = reservation_total_for_cl(cl)
        reservation.hotel = cl.hotel_name or "-"
        reservation.confirmation_letter = cl
        reservation.client_id = cl.client_id
        reservation.save()

        invoice = cl.invoice
        if not invoice.client_id and cl.client_id:
            invoice.client_id = cl.client_id
            invoice.save(update_fields=["client", "customer_name"])
        if invoice.client_id:
            from ..finance.posting import post_invoice_charge
            post_invoice_charge(invoice, created_by=user)
