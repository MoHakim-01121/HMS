import calendar
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from inertia import render as inertia_render

from ..models import ConfirmationLetter, Invoice, ReminderLog, RecapLog, WATarget, MessageTemplate
from ..services.fonnte import send_wa
from ..services.recap import (
    build_recap_message, build_reminder_message,
    TEMPLATE_H0, TEMPLATE_H1, TEMPLATE_RECAP,
)

_MONTH_NAMES = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

_CL_COLORS = {
    'DEFINITE': 'blue',
    'TENTATIVE': 'yellow',
    'CANCELLED': 'red',
}


def _get_upcoming_checkins(active_company):
    today = date.today()
    week_end = today + timedelta(days=6)
    qs = (
        ConfirmationLetter.objects
        .filter(check_in__gte=today, check_in__lte=week_end)
        .exclude(reservation_status='CANCELLED')
        .prefetch_related('rooms', 'reminder_logs')
        .order_by('check_in', 'hotel_name')
    )
    if active_company:
        qs = qs.filter(company=active_company)
    result = []
    for cl in qs:
        rooms_str = ', '.join(f"{r.quantity} {r.room_type}" for r in cl.rooms.all()) or '-'
        logs = list(cl.reminder_logs.all())
        h0_sent = any(
            l.reminder_type == 'H0_GUEST' and l.status == 'SENT'
            and cl.check_in and l.sent_at.date() == cl.check_in
            for l in logs
        )
        h1_sent = any(
            l.reminder_type == 'H1_GUEST' and l.status == 'SENT'
            and cl.check_in and l.sent_at.date() == cl.check_in - timedelta(days=1)
            for l in logs
        )
        h0_failed = (not h0_sent) and any(
            l.reminder_type == 'H0_GUEST' and l.status == 'FAILED'
            and cl.check_in and l.sent_at.date() == cl.check_in
            for l in logs
        )
        h1_failed = (not h1_sent) and any(
            l.reminder_type == 'H1_GUEST' and l.status == 'FAILED'
            and cl.check_in and l.sent_at.date() == cl.check_in - timedelta(days=1)
            for l in logs
        )
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
            'h0_sent': h0_sent,
            'h1_sent': h1_sent,
            'h0_failed': h0_failed,
            'h1_failed': h1_failed,
            'url': cl.get_absolute_url(),
        })
    return result


def _get_message_templates():
    def _fetch():
        rows = {r.template_type: r.body for r in MessageTemplate.objects.all()}
        return {
            'h1_template':    rows.get('H1_GUEST',  TEMPLATE_H1),
            'h0_template':    rows.get('H0_GUEST',  TEMPLATE_H0),
            'recap_template': rows.get('RECAP_OPS', TEMPLATE_RECAP),
        }
    return cache.get_or_set('message_templates', _fetch, 300)


def _get_last_recap():
    def _fetch():
        log = RecapLog.objects.filter(status='SENT').order_by('-sent_at').first()
        if not log:
            return None
        return {
            'sent_at': log.sent_at.strftime('%d %b %Y %H:%M'),
            'target': log.target,
            'cl_count': log.cl_count,
            'triggered_by': log.triggered_by,
        }
    return cache.get_or_set('last_recap', _fetch, 60)


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
        "upcoming_checkins": _get_upcoming_checkins(active_company),
        "last_recap": _get_last_recap(),
    })


@login_required
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


@login_required
def calendar_send_recap(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    from datetime import datetime as _dt
    today = date.today()
    date_str = request.POST.get('date', '').strip()
    if date_str:
        try:
            recap_date = _dt.strptime(date_str, '%Y-%m-%d').date()
            date_filter = {'check_in': recap_date}
            err_label = recap_date.strftime('%d %b %Y')
        except ValueError:
            recap_date = None
            date_filter = {'check_in__gte': today, 'check_in__lte': today + timedelta(days=6)}
            err_label = '7 hari ke depan'
    else:
        recap_date = None
        date_filter = {'check_in__gte': today, 'check_in__lte': today + timedelta(days=6)}
        err_label = '7 hari ke depan'
    active_company = request.session.get('active_company')
    qs = (
        ConfirmationLetter.objects
        .filter(**date_filter, estimasi_tiba__isnull=False)
        .exclude(reservation_status='CANCELLED')
        .prefetch_related('rooms')
        .order_by('check_in', 'hotel_name', 'guest_name')
    )
    if active_company:
        qs = qs.filter(company=active_company)
    cls = list(qs)
    if not cls:
        return JsonResponse({'ok': False, 'message': f'Tidak ada tamu check-in {err_label} dengan estimasi terisi'})
    message = build_recap_message(cls, recap_date)
    wa_targets = list(WATarget.objects.filter(is_active=True))
    if not wa_targets:
        return JsonResponse({'ok': False, 'message': 'Belum ada nomor penerima rekap yang aktif'})
    errors = []
    for t in wa_targets:
        try:
            result = send_wa(t.target, message)
            status = 'SENT' if result.get('status') else 'FAILED'
            error  = result.get('reason', '') if not result.get('status') else ''
        except Exception as exc:
            status, error = 'FAILED', str(exc)
        RecapLog.objects.create(
            target_type=t.target_type, target=t.target,
            cl_count=len(cls), message=message,
            status=status, triggered_by='MANUAL', error=error,
        )
        if status == 'FAILED':
            errors.append(f"{t.label}: {error}")
    cache.delete('last_recap')
    return JsonResponse({'ok': not errors, 'errors': errors})


@login_required
def calendar_send_reminder(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    cl = get_object_or_404(ConfirmationLetter, pk=pk)
    if not cl.guest_phone:
        return JsonResponse({'ok': False, 'message': 'Nomor telepon tamu tidak ada'})
    today = date.today()
    reminder_type = 'H0_GUEST' if cl.check_in == today else 'H1_GUEST'
    message = build_reminder_message(cl, reminder_type)
    try:
        result = send_wa(cl.guest_phone, message)
        status = 'SENT' if result.get('status') else 'FAILED'
        error  = result.get('reason', '') if not result.get('status') else ''
    except Exception as exc:
        status, error = 'FAILED', str(exc)
    ReminderLog.objects.create(
        cl=cl, reminder_type=reminder_type,
        phone=cl.guest_phone, status=status, error=error,
    )
    return JsonResponse({'ok': status == 'SENT', 'status': status})


@login_required
def wa_target_add(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    label  = request.POST.get('label', '').strip()
    target = request.POST.get('target', '').strip()
    if not label or not target:
        return JsonResponse({'ok': False, 'error': 'Label dan nomor wajib diisi'})
    if WATarget.objects.filter(target=target).exists():
        return JsonResponse({'ok': False, 'error': 'Nomor sudah terdaftar'})
    t = WATarget.objects.create(label=label, target=target)
    return JsonResponse({
        'ok': True, 'id': t.pk, 'label': t.label,
        'target': t.target, 'target_type': t.target_type,
    })


@login_required
def wa_target_toggle(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    t = get_object_or_404(WATarget, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=['is_active'])
    return JsonResponse({'ok': True, 'is_active': t.is_active})


@login_required
def wa_target_delete(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    t = get_object_or_404(WATarget, pk=pk)
    t.delete()
    return JsonResponse({'ok': True})


@login_required
def calendar_recap_settings(request):
    return inertia_render(request, 'Calendar/RecapSettings', {
        'wa_targets': list(WATarget.objects.values('id', 'label', 'target', 'target_type', 'is_active')),
        **_get_message_templates(),
    })


@login_required
def message_template_save(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    for ttype, key in [
        ('H1_GUEST',  'h1_template'),
        ('H0_GUEST',  'h0_template'),
        ('RECAP_OPS', 'recap_template'),
    ]:
        body = request.POST.get(key, '').strip()
        if body:
            MessageTemplate.objects.update_or_create(
                template_type=ttype, defaults={'body': body},
            )
    cache.delete('message_templates')
    return JsonResponse({'ok': True})
