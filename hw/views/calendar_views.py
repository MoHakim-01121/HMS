import calendar
from collections import Counter
from datetime import date, timedelta

from django.urls import reverse
from inertia import render as inertia_render

from ..branch_scope import scope
from ..models import ConfirmationLetter, Invoice
from ..models.choices import HotelCity
from ..models.confirmation import ReservationStatus
from ..permissions import require_perm

# The two-week timeline opens on the Sunday of the week holding the anchor day.
WEEK_DAYS = 14


def _parse_date(raw, fallback):
    try:
        return date.fromisoformat(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


def _sunday_of(d):
    # date.weekday(): Monday = 0 ... Sunday = 6.
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _window(request, today):
    """(view, first day, last day) of the range shown. `start` anchors either
    view: the two weeks open on its Sunday, the month is the month holding it."""
    view = 'month' if request.GET.get('view') == 'month' else 'weeks'
    anchor = _parse_date(request.GET.get('start'), today)
    if view == 'month':
        first = anchor.replace(day=1)
        return view, first, first.replace(day=calendar.monthrange(first.year, first.month)[1])
    first = _sunday_of(anchor)
    return view, first, first + timedelta(days=WEEK_DAYS - 1)


def _room_types(cl):
    """'3 Quad, 2 Triple': the rooms booked, by room type, in booking order."""
    counts = Counter()
    for room in cl.rooms.all():
        counts[room.room_type] += room.quantity
    return ', '.join(f'{n} {name}' for name, n in counts.items())


@require_perm('calendar', 'view')
def calendar_view(request):
    """Occupancy timeline per hotel (Record View HMS canvas, 'Calendar').

    Every booking that touches the range comes back with real dates; the page
    draws the bars and works out Arriving, Leaving and In-house for the picked
    day. A cancelled booking holds no rooms, so it is left out.
    """
    today = date.today()
    view, first, last = _window(request, today)

    cls_list = list(
        scope(ConfirmationLetter.objects.all(), request.user)
        # check_out == first still counts: it is that day's Leaving list.
        .filter(check_in__lte=last, check_out__gte=first)
        .exclude(reservation_status=ReservationStatus.CANCELLED)
        .select_related('client', 'hotel')
        .prefetch_related('rooms__room_type_ref')
        .with_invoice()
        .order_by('check_in', 'confirmation_number')
    )
    invoice_ids = {cl.invoice_id for cl in cls_list if cl.invoice_id}
    invoices = Invoice.objects.with_lines().in_bulk(invoice_ids)

    from ..finance import queries as finance_queries
    paid_by_invoice = finance_queries.invoice_paid_map(invoice_ids)

    hotels, bookings = {}, []
    for cl in cls_list:
        hotels.setdefault(cl.hotel_id, {
            'id': cl.hotel_id,
            'name': cl.hotel_name,
            'city': cl.hotel.city,
            'url': reverse('hotel_detail', args=[cl.hotel_id]),
        })
        inv = invoices.get(cl.invoice_id)
        bookings.append({
            'id': cl.pk,
            'ref': cl.confirmation_number,
            'client': cl.guest_name,
            'hotel': cl.hotel_id,
            'check_in': cl.check_in.isoformat(),
            'check_out': cl.check_out.isoformat(),
            'tentative': cl.reservation_status == ReservationStatus.TENTATIVE,
            'rooms': cl.total_rooms,
            'room_types': _room_types(cl),
            'url': reverse('cl_detail', args=[cl.pk]),
            'inv_number': inv.invoice_number if inv else '',
            'inv_url': reverse('invoice_detail', args=[inv.pk]) if inv else '',
            'inv_open': float(max(inv.total_sar - paid_by_invoice.get(inv.pk, 0), 0)) if inv else None,
        })

    # Makkah before Madinah, then by name.
    city_order = {c: i for i, c in enumerate(HotelCity.values)}
    hotel_list = sorted(hotels.values(), key=lambda h: (city_order.get(h['city'], 99), h['name']))

    return inertia_render(request, "Calendar/Index", props={
        "view": view,
        "start": first.isoformat(),
        "end": last.isoformat(),
        "today": today.isoformat(),
        "cities": [{'value': v, 'label': label} for v, label in HotelCity.choices],
        "hotels": hotel_list,
        "bookings": bookings,
    })
