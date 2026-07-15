import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django_q.tasks import async_task

from ..models import Invoice
from .helpers import get_active_company


@login_required
def billing_send(request):
    """Queue one billing WA message for an invoice (Fonnte via django-q)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        data = json.loads(request.body)
        pk = int(data.get('pk'))
    except Exception:
        return JsonResponse({'ok': False, 'message': 'Permintaan tidak valid'}, status=400)

    invoice = (
        Invoice.objects
        .filter(pk=pk, company=get_active_company(request))
        .select_related('client')
        .first()
    )
    if not invoice:
        return JsonResponse({'ok': False, 'message': 'Invoice tidak ditemukan'}, status=404)

    message = (data.get('message') or '').strip()
    if not message:
        return JsonResponse({'ok': False, 'message': 'Pesan tidak boleh kosong'})

    # Target selalu di-resolve di server; nilai nomor dari browser tidak dipercaya.
    target_kind = data.get('target_kind')
    if target_kind == 'client_wa':
        target = invoice.client.wa if invoice.client else ''
        no_target_message = 'Client belum punya nomor WA'
    elif target_kind == 'client_group':
        target = invoice.client.wa_group if invoice.client else ''
        no_target_message = 'Client belum punya WA Group'
    elif target_kind == 'manual':
        target = (data.get('manual_target') or '').strip()
        no_target_message = 'Nomor tujuan wajib diisi'
    else:
        return JsonResponse({'ok': False, 'message': 'Target tidak valid'})
    if not target:
        return JsonResponse({'ok': False, 'message': no_target_message})

    async_task('hw.tasks.send_billing_task', invoice.pk, target, message)
    return JsonResponse({'ok': True, 'queued': True})
