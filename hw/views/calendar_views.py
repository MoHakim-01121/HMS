import calendar
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse

from inertia import render as inertia_render

from ..models import ConfirmationLetter
from ..models.confirmation import guest_name_expr
from ..permissions import require_perm
from ..i18n import tr, user_language
from .pdf import _render_checkin_pdf

_MONTH_NAMES_EN = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
_MONTH_NAMES_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                   'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

_CL_COLORS = {
    'DEFINITE': 'blue',
    'TENTATIVE': 'yellow',
    'CANCELLED': 'red',
}


def _get_upcoming_checkins():
    today = date.today()
    week_end = today + timedelta(days=6)
    qs = (
        ConfirmationLetter.objects
        .filter(check_in__gte=today, check_in__lte=week_end)
        .exclude(reservation_status='CANCELLED')
        .select_related('client', 'hotel')
        .prefetch_related('rooms__room_type_ref')
        .order_by('check_in', 'hotel__name')
    )
    result = []
    for cl in qs:
        rooms_str = ', '.join(f"{r.quantity} {r.room_type}" for r in cl.rooms.all()) or '-'
        result.append({
            'pk': cl.pk,
            'guest_name': cl.guest_name,
            'confirmation_number': cl.confirmation_number,
            'hotel_name': cl.hotel_name,
            'check_in': cl.check_in.isoformat() if cl.check_in else '',
            'rooms': rooms_str,
            'guest_phone': cl.guest_phone,
            'estimasi_tiba': cl.estimasi_tiba.strftime('%H:%M') if cl.estimasi_tiba is not None else '',
            'pic_name': cl.pic_name,
            'pic_phone': cl.pic_phone,
            'client_id': cl.client_id,
            'client_name': cl.client.name if cl.client_id else None,
            'url': cl.get_absolute_url(),
        })
    return result


def _inv_color(request, remaining, total):
    if remaining <= 0:
        return 'green', tr(request, 'Paid', 'Lunas')
    if remaining < total:
        return 'yellow', tr(request, 'Partial', 'Sebagian')
    return 'red', tr(request, 'Unpaid', 'Belum Bayar')


def _clip_day(d, month, year, days_in_month, is_start):
    if d.year == year and d.month == month:
        return d.day
    return 1 if is_start else days_in_month


@require_perm('calendar', 'view')
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

    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    hotel_map = {}

    cl_qs = (
        ConfirmationLetter.objects
        .filter(check_in__lte=month_end, check_out__gt=month_start)
        .exclude(check_in=None).exclude(check_out=None)
        .select_related('invoice')
        .prefetch_related('invoice__reservations', 'invoice__service_items')
    )
    cls_list = list(cl_qs)

    from ..finance import queries as finance_queries
    paid_by_invoice = finance_queries.invoice_paid_map(
        {cl.invoice_id for cl in cls_list if cl.invoice_id}
    )

    for cl in cls_list:
        start = _clip_day(cl.check_in, month, year, days_in_month, is_start=True)
        end = _clip_day(cl.check_out, month, year, days_in_month, is_start=False)
        if end <= start:
            end = start
        hotel = cl.hotel_name or "—"

        inv = cl.invoice
        inv_number = inv.invoice_number if inv else ''
        inv_remaining = (
            f"{inv.total_sar - paid_by_invoice.get(inv.pk, 0):,.0f} SAR" if inv else ''
        )
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
        "month_name": (_MONTH_NAMES_ID if user_language(request) == 'id' else _MONTH_NAMES_EN)[month],
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
        "upcoming_checkins": _get_upcoming_checkins(),
    })


@require_perm('calendar', 'edit')
def cl_estimasi_save(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    cl = get_object_or_404(ConfirmationLetter, pk=pk)
    estimasi_str = request.POST.get('estimasi_tiba', '').strip()
    cl.pic_name  = request.POST.get('pic_name', '').strip()
    cl.pic_phone = request.POST.get('pic_phone', '').strip()
    if estimasi_str:
        from datetime import datetime as _dt
        try:
            cl.estimasi_tiba = _dt.strptime(estimasi_str, '%H:%M').time()
        except ValueError:
            cl.estimasi_tiba = None
    else:
        cl.estimasi_tiba = None
    cl.save(update_fields=['estimasi_tiba', 'pic_name', 'pic_phone'])
    return JsonResponse({'ok': True})


@require_perm('calendar', 'export')
def calendar_checkin_pdf(request):
    today = date.today()
    date_str = request.GET.get('date', '').strip()

    if date_str:
        try:
            from datetime import datetime as _dt
            filter_date = _dt.strptime(date_str, '%Y-%m-%d').date()
            date_filter = {'check_in': filter_date}
            title = f"Check-in – {filter_date.strftime('%d %B %Y')}"
            filename = f"checkin-{date_str}.pdf"
            date_start = date_end = filter_date
        except ValueError:
            date_start, date_end = today, today + timedelta(days=6)
            date_filter = {'check_in__gte': date_start, 'check_in__lte': date_end}
            title = "Upcoming Check-in Recap"
            filename = f"checkin-rekap-{today.isoformat()}.pdf"
    else:
        date_start, date_end = today, today + timedelta(days=6)
        date_filter = {'check_in__gte': date_start, 'check_in__lte': date_end}
        title = "Upcoming Check-in Recap"
        filename = f"checkin-rekap-{today.isoformat()}.pdf"

    qs = (
        ConfirmationLetter.objects
        .filter(**date_filter)
        .exclude(reservation_status='CANCELLED')
        .with_parties().prefetch_related('rooms__room_type_ref')
        .order_by('check_in', 'hotel__name', guest_name_expr().asc())
    )

    return _render_checkin_pdf(list(qs), title, filename,
                               date_start=date_start, date_end=date_end)
