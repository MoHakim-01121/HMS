import json

from django.http import JsonResponse
from django_q.tasks import async_task

from ..models import Invoice
from ..permissions import require_perm
from ..i18n import tr
from .helpers import get_active_company
from .invoice_billing import _billing_client


@require_perm('invoice', 'edit')
def billing_send(request):
    """Queue one billing WA message for an invoice (Fonnte via django-q)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        data = json.loads(request.body)
        pk = int(data.get('pk'))
    except Exception:
        return JsonResponse({'ok': False, 'message': tr(request, 'Invalid request', 'Permintaan tidak valid')}, status=400)

    invoice = (
        Invoice.objects
        .filter(pk=pk, company=get_active_company(request))
        .first()
    )
    if not invoice:
        return JsonResponse({'ok': False, 'message': tr(request, 'Invoice not found', 'Invoice tidak ditemukan')}, status=404)

    message = (data.get('message') or '').strip()
    if not message:
        return JsonResponse({'ok': False, 'message': tr(request, 'Message must not be empty', 'Pesan tidak boleh kosong')})

    # Target selalu di-resolve di server; nilai nomor dari browser tidak dipercaya.
    target_kind = data.get('target_kind')
    client = _billing_client(invoice)
    if target_kind == 'client_wa':
        target = client.wa if client else ''
        no_target_message = tr(request, 'Client has no WA number', 'Client belum punya nomor WA')
    elif target_kind == 'client_group':
        target = client.wa_group if client else ''
        no_target_message = tr(request, 'Client has no WA Group', 'Client belum punya WA Group')
    elif target_kind == 'manual':
        target = (data.get('manual_target') or '').strip()
        no_target_message = tr(request, 'Target number is required', 'Nomor tujuan wajib diisi')
    else:
        return JsonResponse({'ok': False, 'message': tr(request, 'Invalid target', 'Target tidak valid')})
    if not target:
        return JsonResponse({'ok': False, 'message': no_target_message})

    async_task('hw.tasks.send_billing_task', invoice.pk, target, message, bool(data.get('with_pdf')))
    return JsonResponse({'ok': True, 'queued': True})
