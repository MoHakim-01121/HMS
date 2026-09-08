"""WhatsApp reminder, recap, dan target management views.

Dipesah dari calendar_views.py agar file view selaras dengan satu fitur.
Router (hw/views/__init__.py) me-re-export nama-nama ini sehingga URL dan
frontend tidak berubah -- hanya lokasi backend yang dirapikan.

Logika pengolahan pesan / kirim berada di hw/services/recap.py & hw/services/fonnte.py;
modul ini hanya handler HTTP (request/response).
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django_q.tasks import async_task

from inertia import render as inertia_render

from ..models import ConfirmationLetter, WATarget, MessageTemplate
from ..permissions import require_perm
from ..i18n import tr
from .helpers import get_active_company
from ..services.recap import (
    build_recap_message,
    build_grouped_reminder_message, resolve_reminder_targets, resolve_guest_target, group_guests,
)


from ..services.recap import (
    build_recap_message,
    build_grouped_reminder_message, resolve_reminder_targets, resolve_guest_target, group_guests,
    TEMPLATE_H0_CLIENT, TEMPLATE_H1_CLIENT, TEMPLATE_RECAP,
)


def _get_message_templates():
    def _fetch():
        rows = {r.template_type: r.body for r in MessageTemplate.objects.all()}
        return {
            'h1_template':    rows.get('H1_GUEST',  TEMPLATE_H1_CLIENT),
            'h0_template':    rows.get('H0_GUEST',  TEMPLATE_H0_CLIENT),
            'recap_template': rows.get('RECAP_OPS', TEMPLATE_RECAP),
        }
    return cache.get_or_set('message_templates', _fetch, 300)


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
