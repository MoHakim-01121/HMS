import json
import logging
from urllib.parse import urlencode
from datetime import date

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import (
    ActivityLog, Client, ConfirmationLetter, Hotel, Invoice, MealPlan, ReservationStatus, Room,
    RoomType, log_activity,
)
from ..models.confirmation import guest_name_expr
from ..branch_scope import get_in_scope_or_404, scope
from ..permissions import require_perm
from ..i18n import tr
from .helpers import _is_mobile, _parse_date, _parse_search_tokens, _render_list_pdf, csv_export_response, pagination_props, snapshot_fields, track_changes
from .pdf import _logo_file_url, _render_cl_pdf
from ..utils import round_half_up
from ..signals import invoice_sync_suspended, sync_invoice_for_cl

logger = logging.getLogger(__name__)


def _get_cl(request, pk, qs=None):
    """Fetch a ConfirmationLetter of the user's branches by pk (404 otherwise)."""
    qs = qs if qs is not None else ConfirmationLetter.objects.all()
    return get_in_scope_or_404(qs, request.user, pk=pk)


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
    """Read the standard CL list filters (q/status/date range/basis) off the querystring."""
    return (
        request.GET.get('q', '').strip(),
        [s.upper() for s in request.GET.getlist('status') if s.upper() in ('DEFINITE', 'TENTATIVE', 'CANCELLED')],
        _parse_date(request.GET.get('date_from', '').strip()),
        _parse_date(request.GET.get('date_to', '').strip()),
        'sold' if request.GET.get('by') == 'sold' else 'check_in',
    )


def _apply_cl_filters(qs, q, status_list, date_from, date_to, by='check_in'):
    """`by` picks the date the range applies to: 'check_in', or 'sold' (the
    day the CL was made, created_at in local time)."""
    if q:
        tokens = _parse_search_tokens(q)
        if tokens:
            combined = Q()
            for token in tokens:
                combined |= ConfirmationLetter.objects.name_matches(token)
            qs = qs.filter(combined)
    if status_list:
        qs = qs.filter(reservation_status__in=status_list)
    field = 'created_at__date' if by == 'sold' else 'check_in'
    if date_from:
        qs = qs.filter(**{f'{field}__gte': date_from})
    if date_to:
        qs = qs.filter(**{f'{field}__lte': date_to})
    return qs


def _filter_cl_qs(qs, request):
    """`qs` narrowed to the user's branches and the list filters, ordered."""
    qs = scope(qs, request.user)
    q, status_list, date_from, date_to, by = _cl_filter_params(request)
    sort = request.GET.get('sort', '-check_in')
    qs = _apply_cl_filters(qs, q, status_list, date_from, date_to, by)
    return _order(qs, sort)


def _sold_on(cl):
    return timezone.localtime(cl.created_at).date()


def _cl_month_stats(cls, first, last):
    """KPI figures of CLs sold (created) between first and last: counts, room
    nights and value of the live ones, the cancelled ones, and cumulative
    series by sale day (5, 10, ... end of month) for the trend lines."""
    live = [c for c in cls if c.reservation_status != 'CANCELLED']
    cancelled = [c for c in cls if c.reservation_status == 'CANCELLED']
    nights = lambda c: sum(r.quantity for r in c.rooms.all()) * (c.num_nights or 0)
    value = lambda c: float(c.total_price or 0)
    marks = list(range(5, last.day, 5)) + [last.day]
    series = lambda f: [round(sum(f(c) for c in live if _sold_on(c).day <= d)) for d in marks]
    return {
        'count': len(live),
        'nights': sum(nights(c) for c in live),
        'value': round_half_up(sum(value(c) for c in live)),
        'cancelled': len(cancelled),
        'cancelled_value': round_half_up(sum(value(c) for c in cancelled)),
        'spark_count': series(lambda c: 1),
        'spark_nights': series(nights),
        'spark_value': series(lambda c: value(c) / 1000),
    }


@require_perm('cl', 'view')
def cl_list(request):
    """CL list (Record View HMS canvas): the month (or year) nav shows the CLs
    sold in it, by created_at, with KPIs by sale day against the month before;
    the Check-in range filter, when set, picks by check-in instead."""
    from .helpers import csv_list, list_per_page, list_period, num_delta, pct_delta, prev_month_range
    base_qs = (
        scope(ConfirmationLetter.objects.all(), request.user)
        .defer('note').select_related('client', 'hotel').with_invoice()
        .prefetch_related('rooms__room_type_ref')
    )
    q = request.GET.get('q', '').strip()
    status_list = [s.upper() for s in csv_list(request, 'status', ['definite', 'tentative', 'cancelled'])]
    inv = request.GET.get('inv', '')
    sort = request.GET.get('sort', 'check_in')
    date_from, date_to, period = list_period(request)

    by = 'check_in' if (period['from'] or period['to']) else 'sold'
    period_qs = _apply_cl_filters(base_qs, q, [], date_from, date_to, by)
    qs = period_qs
    if status_list:
        qs = qs.filter(reservation_status__in=status_list)
    if inv == 'yes':
        qs = qs.invoiced()
    elif inv == 'no':
        qs = qs.uninvoiced()
    qs = _order(qs, sort if sort in _SORT_MAP else 'check_in')

    # Filter counts over the period (before the status/invoice filter).
    by_status = {r['reservation_status']: r['n'] for r in period_qs.values('reservation_status').annotate(n=Count('id'))}
    invoiced_n = period_qs.invoiced().count()
    counts = {
        'definite': by_status.get('DEFINITE', 0), 'tentative': by_status.get('TENTATIVE', 0),
        'cancelled': by_status.get('CANCELLED', 0), 'all': sum(by_status.values()),
        'invoiced': invoiced_n, 'not_invoiced': sum(by_status.values()) - invoiced_n,
    }

    # KPIs: a calendar month only (the period of the month nav).
    kpis = None
    if period['month']:
        sold = lambda a, b: list(base_qs.filter(created_at__date__gte=a, created_at__date__lte=b))
        cur = _cl_month_stats(sold(date_from, date_to), date_from, date_to)
        pf, pl = prev_month_range(date_from)
        prev = _cl_month_stats(sold(pf, pl), pf, pl)
        kpis = {'cur': cur, 'prev': prev, 'prev_month': pf.strftime('%Y-%m'),
                'delta': {'count': num_delta(cur['count'], prev['count']),
                          'nights': pct_delta(cur['nights'], prev['nights']),
                          'value': pct_delta(cur['value'], prev['value']),
                          'cancelled': num_delta(cur['cancelled'], prev['cancelled'])}}

    page_obj = Paginator(qs, list_per_page(request)).get_page(request.GET.get('page'))
    letters = [{
        "id": cl.id,
        "confirmation_number": cl.confirmation_number,
        "reservation_status": cl.reservation_status,
        "guest_name": cl.guest_name,
        "hotel_name": cl.hotel_name,
        "check_in": cl.check_in.isoformat() if cl.check_in else None,
        "check_out": cl.check_out.isoformat() if cl.check_out else None,
        "num_nights": cl.num_nights,
        "total_rooms": cl.total_rooms,
        "total_price": round_half_up(cl.total_price) if cl.total_price else 0,
        "invoice_number": cl.invoice.invoice_number if cl.invoice_id else "",
        "invoice_id": cl.invoice.pk if cl.invoice_id else None,
    } for cl in page_obj]

    years = sorted({d.year for d in base_qs.datetimes('created_at', 'year')} | {date.today().year})
    return inertia_render(request, "Cl/List", props={
        "letters": letters,
        "filters": {"q": q, "status": [s.lower() for s in status_list], "inv": inv, "sort": sort,
                    "per": list_per_page(request), **period},
        "years": years,
        "counts": counts,
        "kpis": kpis,
        "export_qs": "?" + urlencode([(k, v) for k, v in [
            ("q", q), ("date_from", date_from.isoformat() if date_from else ""),
            ("date_to", date_to.isoformat() if date_to else ""), ("sort", sort),
            ("by", "sold" if by == "sold" else ""),
        ] + [("status", s.lower()) for s in status_list] if v]),
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
        "clients": list(Client.objects.filter(is_active=True).values("id", "name", "brand", "city").order_by("name")),
        "salespeople": _salespeople(),
    }


def _salespeople():
    """Active HMS users for the CL's Salesperson picker: name, and where they
    work (head office, or their branches)."""
    users = (User.objects.filter(is_active=True)
             .select_related('profile').prefetch_related('profile__branch_access__branch'))
    out = []
    for u in users:
        profile = getattr(u, 'profile', None)
        if u.is_superuser or profile is None or profile.all_branches:
            where = "HQ"
        else:
            where = ", ".join(sorted(a.branch.name for a in profile.branch_access.all())) or "HQ"
        out.append({"id": u.pk, "name": u.get_full_name() or u.username, "meta": where})
    return sorted(out, key=lambda r: r["name"].lower())


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


def _validate_cl(data, exclude_pk=None, need_salesperson=True):
    errors = {}
    salesperson = data.get("salesperson_id") or None
    if salesperson and not User.objects.filter(pk=salesperson, is_active=True).exists():
        errors["salesperson_id"] = "Choose the salesperson from the list."
    elif need_salesperson and not salesperson:
        errors["salesperson_id"] = "Choose the salesperson."
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
        "salesperson_id": data.get("salesperson_id", ""),
        "note": data.get("note", ""),
        "rooms": rooms,
    }


def _salesperson_name(cl):
    u = cl.salesperson
    return (u.get_full_name() or u.username) if u else '—'


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
                salesperson_id=request.POST.get("salesperson_id") or None,
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
        ConfirmationLetter.objects.select_related('client', 'hotel', 'penalty').with_invoice()
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
        "by": l.actor_display,
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
        # A CL from before Salesperson existed may stay without one.
        errors = _validate_cl(request.POST, exclude_pk=cl.pk, need_salesperson=bool(cl.salesperson_id))
        billed_on = cl.invoice
        if billed_on and not errors and str(request.POST.get("client_id") or "") != str(cl.client_id):
            errors["guest_name"] = (
                f"This reservation is billed on invoice {billed_on.invoice_number}, "
                "so its client cannot be changed. Void the invoice first."
            )
        new_status = (request.POST.get("reservation_status") or "DEFINITE").upper()
        if hasattr(cl, 'penalty') and new_status != ReservationStatus.CANCELLED and not errors:
            errors["reservation_status"] = (
                f"This reservation has cancellation penalty {cl.penalty.penalty_number}, "
                "so it stays Cancelled. Remove the penalty first."
            )
        if errors:
            echo = _cl_echo(request.POST); echo["id"] = cl.pk
            return inertia_render(request, "Cl/Form", props={
                "cl": echo, "edit": True, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", cl.confirmation_number),
                **_form_context_data(),
            })

        _before = {**snapshot_fields(cl, ['hotel_name', 'guest_name', 'guest_phone', 'check_in', 'check_out', 'reservation_status']),
                   'salesperson': _salesperson_name(cl)}
        _rooms_before = _room_snapshot(cl.rooms.all())

        # One transaction, one invoice sync: the rooms are rewritten row by
        # row, and the invoice should follow the finished CL, not each step.
        with transaction.atomic(), invoice_sync_suspended():
            cl.client_id = request.POST.get("client_id")
            cl.hotel_id = _resolve_hotel_id(request)
            cl.guest_phone = request.POST.get("guest_phone", "")
            cl.check_in = _parse_date(request.POST.get("check_in"))
            cl.check_out = _parse_date(request.POST.get("check_out"))
            cl.confirmation_number = request.POST.get("confirmation_number", "")
            cl.reservation_status = (request.POST.get("reservation_status") or "DEFINITE").upper()
            cl.salesperson_id = request.POST.get("salesperson_id") or None
            cl.note = request.POST.get("note", "")
            cl.save()
            ConfirmationLetter.claim_number(cl.confirmation_number)

            cl.rooms.all().delete()
            _save_cl_rooms(cl, request)
            cl = ConfirmationLetter.objects.get(pk=cl.pk)   # drop cached rooms
            sync_invoice_for_cl(cl, request.user)

        _after = {**snapshot_fields(cl, ['hotel_name', 'guest_name', 'guest_phone', 'check_in', 'check_out', 'reservation_status']),
                  'salesperson': _salesperson_name(cl)}
        _rooms_after = _room_snapshot(cl.rooms.all())
        changes = track_changes(
            {**_before, 'Rooms': _rooms_before},
            {**_after, 'Rooms': _rooms_after},
            labels={'hotel_name': 'Hotel', 'guest_name': 'Guest', 'guest_phone': 'Phone', 'check_in': 'Check-in', 'check_out': 'Check-out', 'reservation_status': 'Status', 'salesperson': 'Salesperson', 'Rooms': 'Rooms'},
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
            "salesperson_id": cl.salesperson_id or "",
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
        if cl.invoice_lines.exists():
            messages.error(
                request,
                f"Confirmation Letter {num} is on an invoice and cannot be deleted. "
                "Cancel the reservation instead.",
            )
            return redirect("cl_detail", pk=cl.pk)
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

    cls = scope(ConfirmationLetter.objects.filter(pk__in=cl_ids), request.user).select_related('client', 'hotel').with_invoice()
    if not cls.exists():
        messages.error(request, "CL not found.")
        return redirect("cl_list")

    # One invoice bills one client, and a reservation is billed once.
    clients = {cl.client_id for cl in cls}
    if len(clients) > 1:
        messages.error(request, "The selected CLs belong to different clients. One invoice bills one client.")
        return redirect("cl_list")
    billed = [cl.confirmation_number for cl in cls if cl.invoice_id]
    if billed:
        messages.error(request, f"Already on an invoice: CL {', '.join(billed)}.")
        return redirect("cl_list")

    first_cl = cls.order_by('created_at').first()
    with transaction.atomic():
        invoice = Invoice.objects.create(
            invoice_type="hotel",
            invoice_number=Invoice.generate_number("hotel"),
            client_id=first_cl.client_id,
            branch_id=first_cl.client.owner_branch_id,
            issued_date=date.today(),
            currency="SAR",
            created_by=request.user,
        )
        for cl in cls.order_by('created_at'):
            invoice.add_hotel_line(cl)

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
