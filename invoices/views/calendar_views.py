import calendar
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import ConfirmationLetter, Invoice

_MONTH_NAMES = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

_CL_COLORS = {
    'DEFINITE': 'blue',
    'TENTATIVE': 'yellow',
    'CANCELLED': 'red',
}


def _clip_day(d, month, year, days_in_month, is_start):
    if d.year == year and d.month == month:
        return d.day
    return 1 if is_start else days_in_month


@login_required
def calendar_view(request):
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    active_company = request.session.get("active_company")
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    hotel_map = {}

    # CL reservations
    cl_qs = ConfirmationLetter.objects.filter(
        check_in__lte=month_end,
        check_out__gt=month_start,
    ).exclude(check_in=None).exclude(check_out=None)
    if active_company:
        cl_qs = cl_qs.filter(company=active_company)

    for cl in cl_qs:
        start = _clip_day(cl.check_in, month, year, days_in_month, is_start=True)
        end = _clip_day(cl.check_out, month, year, days_in_month, is_start=False)
        if end <= start:
            end = start
        hotel = cl.hotel_name or "—"
        hotel_map.setdefault(hotel, []).append({
            'guest': cl.guest_name,
            'ref': cl.confirmation_number,
            'start': start,
            'end': end,
            'span': end - start + 1,
            'color': _CL_COLORS.get(cl.reservation_status, 'blue'),
            'status': cl.reservation_status,
            'total': f"{cl.total_price:,.0f} SAR",
            'url': f"/cl/{cl.pk}/",
            'type': 'CL',
            'nights': cl.num_nights,
        })

    # Invoice Hotel reservations
    inv_qs = Invoice.objects.filter(invoice_type="hotel").prefetch_related('reservations')
    if active_company:
        inv_qs = inv_qs.filter(company=active_company)

    for inv in inv_qs:
        remaining = inv.remaining_sar
        total_sar = inv.total_sar
        inv_color = 'green' if remaining == 0 else 'yellow' if remaining < total_sar else 'red'
        inv_status = 'Lunas' if remaining == 0 else 'Partial' if remaining < total_sar else 'Belum Bayar'

        for res in inv.reservations.all():
            if not res.check_in or not res.check_out:
                continue
            if res.check_in > month_end or res.check_out < month_start:
                continue
            start = _clip_day(res.check_in, month, year, days_in_month, is_start=True)
            end = _clip_day(res.check_out, month, year, days_in_month, is_start=False)
            if end <= start:
                end = start
            hotel = res.hotel or "—"
            hotel_map.setdefault(hotel, []).append({
                'guest': inv.customer_name,
                'ref': inv.invoice_number,
                'start': start,
                'end': end,
                'span': end - start + 1,
                'color': inv_color,
                'status': inv_status,
                'total': f"{res.total_sar:,.0f} SAR",
                'url': f"/invoice/{inv.pk}/",
                'type': 'INV',
                'nights': (res.check_out - res.check_in).days,
            })

    hotels = [{'name': k, 'reservations': sorted(v, key=lambda x: x['start'])}
              for k, v in sorted(hotel_map.items())]

    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)

    today_day = today.day if today.year == year and today.month == month else None

    # Summary counts
    all_res = [r for h in hotels for r in h['reservations']]
    checkins_today  = sum(1 for r in all_res if r['start'] == today_day) if today_day else 0
    checkouts_today = sum(1 for r in all_res if r['end'] == today_day) if today_day else 0
    unpaid_count    = sum(1 for r in all_res if r['color'] == 'red')
    active_today    = sum(1 for r in all_res if today_day and r['start'] <= today_day <= r['end']) if today_day else 0

    return render(request, "invoices/calendar.html", {
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
        "unpaid_count": unpaid_count,
        "active_today": active_today,
    })
