import calendar
from collections import Counter
from datetime import date, timedelta
from itertools import groupby

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override
from inertia import render as inertia_render

from ..branch_scope import scope
from ..models import ConfirmationLetter, Invoice
from ..models.choices import HotelCity
from ..models.confirmation import ReservationStatus
from ..models.hotel import room_type_name
from ..permissions import require_perm

# The two-week timeline opens on the Sunday of the week holding the anchor day.
WEEK_DAYS = 14

# Guests per room of the room columns the check-in recap always prints.
RECAP_CAPACITIES = (2, 3, 4, 5)


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
    today = timezone.localdate()
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


def _recap_rows(cls_of_hotel, capacities):
    """A hotel's rows: rooms counted per column of `capacities`. A client with
    several CLs there is named on the first only."""
    rows, previous = [], None
    for cl in cls_of_hotel:
        counts = Counter()
        for room in cl.rooms.all():
            counts[room.room_type_ref.capacity] += room.quantity
        rows.append({
            'client_name': cl.client.display_name,
            'show_client': cl.client_id != previous,
            'confirmation_number': cl.confirmation_number,
            'tentative': cl.reservation_status == ReservationStatus.TENTATIVE,
            'counts': [counts[c] for c in capacities],
            'rooms': sum(counts.values()),
            'pax': cl.num_guests,
            'meal': ', '.join(m for m in dict.fromkeys(r.meals for r in cl.rooms.all()) if m),
            'check_in': cl.check_in,
            'check_out': cl.check_out,
            'nights': cl.num_nights,
            'note': cl.note,
        })
        previous = cl.client_id
    return rows


@require_perm('calendar', 'export')
def calendar_checkin_pdf(request):
    """Check-in recap for one day or a range, by date, then hotel. The counts
    match the calendar: two CLs of one client at one hotel are one check-in."""
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url

    first = _parse_date(request.GET.get('start'), timezone.localdate())
    last = max(_parse_date(request.GET.get('end'), first), first)

    cls_list = list(
        scope(ConfirmationLetter.objects.all(), request.user)
        .filter(check_in__range=(first, last))
        .exclude(reservation_status=ReservationStatus.CANCELLED)
        .select_related('client', 'hotel')
        .prefetch_related('rooms__room_type_ref')
    )
    # Makkah before Madinah, as on the calendar.
    city_order = {c: i for i, c in enumerate(HotelCity.values)}
    cls_list.sort(key=lambda cl: (
        cl.check_in, city_order.get(cl.hotel.city, 99), cl.hotel_name,
        cl.client.display_name.casefold(), cl.client_id, cl.confirmation_number,
    ))

    # Double to Quint always have a column; any other size gets one when booked.
    capacities = sorted(set(RECAP_CAPACITIES) | {r.room_type_ref.capacity for cl in cls_list for r in cl.rooms.all()})

    groups = []
    for day, of_day in groupby(cls_list, key=lambda cl: cl.check_in):
        of_day = list(of_day)
        groups.append({
            'date': day,
            'total': len({(cl.client_id, cl.hotel_id) for cl in of_day}),
            'rooms': sum(cl.total_rooms for cl in of_day),
            'pax': sum(cl.num_guests for cl in of_day),
            'hotels': [
                {'name': hotel.name, 'rows': _recap_rows(of_hotel, capacities)}
                for hotel, of_hotel in groupby(of_day, key=lambda cl: cl.hotel)
            ],
        })

    # The PDF is in English whichever language the user works in.
    with override('en'):
        return _render_list_pdf(
            request, ConfirmationLetter.objects.none(),
            template='hw/calendar/checkin_recap_pdf.html',
            filename=f'checkin-recap-{first}.pdf' if first == last else f'checkin-recap-{first}-to-{last}.pdf',
            extra_ctx={
                'first': first,
                'last': last,
                'groups': groups,
                'columns': [room_type_name(c) for c in capacities],
                'colspan': len(capacities) + 6,
                'total_checkins': sum(g['total'] for g in groups),
                'total_hotels': len({cl.hotel_id for cl in cls_list}),
                'total_rooms': sum(cl.total_rooms for cl in cls_list),
                'total_pax': sum(cl.num_guests for cl in cls_list),
                'logo_rel_path': _logo_file_url(),
            },
        )
