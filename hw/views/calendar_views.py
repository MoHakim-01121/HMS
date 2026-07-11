import calendar
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django_q.tasks import async_task

from inertia import render as inertia_render

from ..models import ConfirmationLetter, Invoice, RecapLog, WATarget, MessageTemplate
from ..permissions import require_perm
from ..i18n import tr, user_language
from .helpers import get_active_company
from .pdf import _render_checkin_pdf
from ..services.recap import (
    build_recap_message,
    build_grouped_reminder_message, resolve_reminder_targets, resolve_guest_target, group_guests,
    TEMPLATE_H0_CLIENT, TEMPLATE_H1_CLIENT, TEMPLATE_RECAP,
)

_MONTH_NAMES_EN = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
_MONTH_NAMES_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
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
        .select_related('client')
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
            'client_id': cl.client_id,
            'client_name': cl.client.name if cl.client_id else None,
            'url': cl.get_absolute_url(),
        })
    return result


def _get_message_templates():
    def _fetch():
        rows = {r.template_type: r.body for r in MessageTemplate.objects.all()}
        return {
            'h1_template':    rows.get('H1_GUEST',  TEMPLATE_H1_CLIENT),
            'h0_template':    rows.get('H0_GUEST',  TEMPLATE_H0_CLIENT),
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

    active_company = get_active_company(request)
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
        .filter(company=active_company)
    )

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
        "upcoming_checkins": _get_upcoming_checkins(active_company),
        "last_recap": _get_last_recap(),
    })


@require_perm('calendar', 'edit')
def cl_estimasi_save(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    cl = get_object_or_404(ConfirmationLetter, pk=pk, company=get_active_company(request))
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


@require_perm('calendar', 'edit')
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
            err_label = tr(request, 'next 7 days', '7 hari ke depan')
    else:
        recap_date = None
        date_filter = {'check_in__gte': today, 'check_in__lte': today + timedelta(days=6)}
        err_label = tr(request, 'next 7 days', '7 hari ke depan')
    qs = (
        ConfirmationLetter.objects
        .filter(**date_filter, company=get_active_company(request))
        .exclude(reservation_status='CANCELLED')
        .prefetch_related('rooms')
        .order_by('check_in', 'hotel_name', 'guest_name')
    )
    cls = list(qs)
    if not cls:
        return JsonResponse({'ok': False, 'message': tr(request, f'No check-in guests in the {err_label}', f'Tidak ada tamu check-in {err_label}')})
    message = build_recap_message(cls, recap_date)
    wa_targets = list(WATarget.objects.filter(is_active=True))
    if not wa_targets:
        return JsonResponse({'ok': False, 'message': tr(request, 'No active recap recipient number yet', 'Belum ada nomor penerima rekap yang aktif')})
    for t in wa_targets:
        async_task('hw.tasks.send_recap_task', t.target_type, t.target, t.label, message, len(cls))
    cache.delete('last_recap')
    return JsonResponse({'ok': True, 'queued': len(wa_targets)})


@require_perm('calendar', 'edit')
def calendar_send_reminder_group(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if not settings.REMINDER_H1_H0_ENABLED:
        return JsonResponse({'ok': False, 'message': tr(request, 'H-1/H-0 reminders are temporarily disabled', 'Reminder H-1/H-0 sedang dinonaktifkan sementara')})
    cl_ids = request.POST.getlist('cl_ids')
    if not cl_ids:
        return JsonResponse({'ok': False, 'message': tr(request, 'No bookings selected', 'Tidak ada booking dipilih')})
    cls = list(
        ConfirmationLetter.objects
        .filter(pk__in=cl_ids, company=get_active_company(request))
        .exclude(reservation_status='CANCELLED')
        .select_related('client')
        .prefetch_related('rooms')
    )
    if len(cls) != len(cl_ids):
        return JsonResponse({'ok': False, 'message': tr(request, 'Some bookings were not found', 'Sebagian booking tidak ditemukan')})
    client_ids = {cl.client_id for cl in cls}
    if len(client_ids) == 1 and None not in client_ids:
        client = cls[0].client
        recipient_name = client.name
        resolve_targets = lambda cl_list: resolve_reminder_targets(client, cl_list)
        no_target_message = tr(request, 'Client has no active WA number/Group', 'Client belum punya nomor WA/Group yang aktif')
    elif client_ids == {None}:
        if len(group_guests(cls)) != 1:
            return JsonResponse({'ok': False, 'message': tr(request, 'Bookings must be for the same guest', 'Booking harus dari tamu yang sama')})
        recipient_name = cls[0].guest_name
        # Resolve from the whole group: the phone may live on a sibling booking.
        resolve_targets = lambda cl_list: resolve_guest_target(cl_list)
        no_target_message = tr(request, 'Guest has no WhatsApp number', 'Tamu belum punya nomor WhatsApp')
    else:
        return JsonResponse({'ok': False, 'message': tr(request, 'Bookings must be for the same client', 'Booking harus dari 1 client yang sama')})
    check_ins = {cl.check_in for cl in cls}
    if len(check_ins) != 1:
        return JsonResponse({'ok': False, 'message': tr(request, 'Bookings must have the same check-in date', 'Booking harus di tanggal check-in yang sama')})
    today = date.today()
    check_in_date = next(iter(check_ins))
    if check_in_date == today:
        reminder_type = 'H0_GUEST'
    elif check_in_date > today:
        reminder_type = 'H1_GUEST'
    else:
        return JsonResponse({'ok': False, 'message': tr(request, 'Check-in date has already passed', 'Tanggal check-in sudah lewat')})
    # Manual send never dedups against ReminderLog: the operator may need to
    # resend a reminder that was already sent today (e.g. after editing the
    # booking). Only the scheduled command (send_checkin_reminders) is
    # idempotent per day.
    targets = resolve_targets(cls)
    if not targets:
        return JsonResponse({'ok': False, 'message': no_target_message})
    message = build_grouped_reminder_message(cls, reminder_type, recipient_name=recipient_name)
    cl_pks = [cl.pk for cl in cls]
    for channel, phone in targets:
        async_task('hw.tasks.send_reminder_group_task', cl_pks, reminder_type, phone, message)
    return JsonResponse({'ok': True, 'queued': True})


@require_perm('calendar', 'edit')
def wa_target_add(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    label  = request.POST.get('label', '').strip()
    target = request.POST.get('target', '').strip()
    if not label or not target:
        return JsonResponse({'ok': False, 'error': tr(request, 'Label and number are required', 'Label dan nomor wajib diisi')})
    if WATarget.objects.filter(target=target).exists():
        return JsonResponse({'ok': False, 'error': tr(request, 'Number already registered', 'Nomor sudah terdaftar')})
    t = WATarget.objects.create(label=label, target=target)
    return JsonResponse({
        'ok': True, 'id': t.pk, 'label': t.label,
        'target': t.target, 'target_type': t.target_type,
    })


@require_perm('calendar', 'edit')
def wa_target_toggle(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    t = get_object_or_404(WATarget, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=['is_active'])
    return JsonResponse({'ok': True, 'is_active': t.is_active})


@require_perm('calendar', 'edit')
def wa_target_delete(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    t = get_object_or_404(WATarget, pk=pk)
    t.delete()
    return JsonResponse({'ok': True})


@require_perm('calendar', 'edit')
def calendar_recap_settings(request):
    return inertia_render(request, 'Calendar/RecapSettings', {
        'wa_targets': list(WATarget.objects.values('id', 'label', 'target', 'target_type', 'is_active')),
        **_get_message_templates(),
    })


@require_perm('calendar', 'edit')
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


@require_perm('calendar', 'export')
def calendar_checkin_pdf(request):
    today = date.today()
    active_company = get_active_company(request)
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
        .prefetch_related('rooms')
        .order_by('check_in', 'hotel_name', 'guest_name')
        .filter(company=active_company)
    )

    return _render_checkin_pdf(list(qs), title, active_company, filename,
                               date_start=date_start, date_end=date_end)
