import calendar
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from inertia import render as inertia_render

from ..models import ConfirmationLetter, Invoice

_MONTH_NAMES = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

_CL_COLORS = {
    'DEFINITE': 'blue',
    'TENTATIVE': 'yellow',
    'CANCELLED': 'red',
}


def _inv_color(remaining, total):
    if remaining <= 0:
        return 'green', 'Lunas'
    if remaining < total:
        return 'yellow', 'Partial'
    return 'red', 'Belum Bayar'


def _clip_day(d, month, year, days_in_month, is_start):
    if d.year == year and d.month == month:
        return d.day
    return 1 if is_start else days_in_month


@login_required
def calendar_view(request):
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    active_company = request.session.get("active_company")
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    hotel_map = {}

    cl_qs = (
        ConfirmationLetter.objects
        .filter(check_in__lte=month_end, check_out__gt=month_start)
        .exclude(check_in=None).exclude(check_out=None)
        .select_related('invoice')
        .prefetch_related('invoice__payments', 'invoice__reservations')
    )
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)

    for cl in cl_qs:
        start = _clip_day(cl.check_in, month, year, days_in_month, is_start=True)
        end = _clip_day(cl.check_out, month, year, days_in_month, is_start=False)
        if end <= start:
            end = start
        hotel = cl.hotel_name or "—"

        inv = cl.invoice
        inv_number = inv.invoice_number if inv else ''
        inv_remaining = f"{inv.remaining_sar:,.0f} SAR" if inv else ''
        inv_url = reverse('invoice_detail', args=[inv.pk]) if inv else ''

        hotel_map.setdefault(hotel, []).append({
            'guest': cl.guest_name,
            'ref': cl.confirmation_number,
            'start': start,
            'end': end,
            'span': end - start + 1,
            'color': _CL_COLORS.get(cl.reservation_status, 'blue'),
            'status': cl.reservation_status,
            'total': f"{cl.total_price:,.0f} SAR",
            'url': reverse('cl_detail', args=[cl.pk]),
            'nights': cl.num_nights,
            'inv_number': inv_number,
            'inv_remaining': inv_remaining,
            'inv_url': inv_url,
            'check_in': cl.check_in.isoformat(),
        })

    hotels = [{'name': k, 'reservations': sorted(v, key=lambda x: x['start'])}
              for k, v in sorted(hotel_map.items())]

    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)

    today_day = today.day if today.year == year and today.month == month else None

    # Summary counts
    all_res = [r for h in hotels for r in h['reservations']]
    checkins_today   = sum(1 for r in all_res if r['start'] == today_day) if today_day else 0
    checkouts_today  = sum(1 for r in all_res if r['end'] == today_day) if today_day else 0
    tentative_count  = sum(1 for r in all_res if r['color'] == 'yellow')
    active_today     = sum(1 for r in all_res if today_day and r['start'] <= today_day <= r['end']) if today_day else 0

    return inertia_render(request, "Calendar/Index", props={
        "year": year,
        "month": month,
        "month_name": _MONTH_NAMES[month],
        "days_in_month": days_in_month,
        "days": list(range(1, days_in_month + 1)),
        "today_day": today_day,
        "hotels": hotels,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "total_reservations": sum(len(h['reservations']) for h in hotels),
        "checkins_today": checkins_today,
        "checkouts_today": checkouts_today,
        "tentative_count": tentative_count,
        "active_today": active_today,
    })
