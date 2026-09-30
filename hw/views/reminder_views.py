"""WhatsApp reminder, recap, dan target management views.

Dipesah dari calendar_views.py agar file view selaras dengan satu fitur.
Router (hw/views/__init__.py) me-re-export nama-nama ini sehingga URL dan
frontend tidak berubah -- hanya lokasi backend yang dirapikan.

Aplikasi tidak mengirim WhatsApp sendiri: endpoint di bawah hanya menyusun
teks pesan (via hw/services/recap.py) untuk disalin/dikirim manual oleh
operator.
"""
from datetime import date, timedelta

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from inertia import render as inertia_render

from ..models import ConfirmationLetter, WATarget, MessageTemplate
from ..models.confirmation import guest_name_expr
from ..permissions import require_perm
from ..i18n import tr
from ..services.recap import (
    build_recap_message,
    build_grouped_reminder_message, resolve_reminder_targets,
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
        .filter(**date_filter)
        .exclude(reservation_status='CANCELLED')
        .with_parties().prefetch_related('rooms__room_type_ref')
        .order_by('check_in', 'hotel__name', guest_name_expr().asc())
    )
    cls = list(qs)
    if not cls:
        return JsonResponse({'ok': False, 'message': tr(request, f'No check-in guests in the {err_label}', f'Tidak ada tamu check-in {err_label}')})
    message = build_recap_message(cls, recap_date)
    return JsonResponse({'ok': True, 'message': message, 'cl_count': len(cls)})


@require_perm('calendar', 'edit')
def calendar_send_reminder_group(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    cl_ids = request.POST.getlist('cl_ids')
    if not cl_ids:
        return JsonResponse({'ok': False, 'message': tr(request, 'No bookings selected', 'Tidak ada booking dipilih')})
    cls = list(
        ConfirmationLetter.objects
        .filter(pk__in=cl_ids)
        .exclude(reservation_status='CANCELLED')
        .select_related('client')
        .prefetch_related('rooms')
    )
    if len(cls) != len(cl_ids):
        return JsonResponse({'ok': False, 'message': tr(request, 'Some bookings were not found', 'Sebagian booking tidak ditemukan')})
    # Every reservation belongs to a client (schema v2), so a group is simply
    # the bookings of one client.
    if len({cl.client_id for cl in cls}) != 1:
        return JsonResponse({'ok': False, 'message': tr(request, 'Bookings must be for the same client', 'Booking harus dari 1 client yang sama')})
    client = cls[0].client
    recipient_name = client.name
    resolve_targets = lambda cl_list: resolve_reminder_targets(client, cl_list)
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
    targets = resolve_targets(cls)
    message = build_grouped_reminder_message(cls, reminder_type, recipient_name=recipient_name)
    # A resolved phone (if any) drives the wa.me deep link in the modal; a
    # missing number is not an error here — the operator can still copy the text.
    phone = next((p for _channel, p in targets), '') if targets else ''
    return JsonResponse({'ok': True, 'message': message, 'phone': phone, 'reminder_type': reminder_type})


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
