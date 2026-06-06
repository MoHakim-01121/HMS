import os

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from ..models import Attachment, ConfirmationLetter, Invoice

_ALLOWED_MIME = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv', 'text/plain',
}


@login_required
@require_POST
def attachment_upload(request):
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "No file"}, status=400)

    invoice_id = request.POST.get("invoice_id")
    cl_id = request.POST.get("cl_id")
    if not invoice_id and not cl_id:
        return JsonResponse({"error": "No target"}, status=400)

    if f.size > 10 * 1024 * 1024:
        return JsonResponse({"error": "File terlalu besar (maks 10 MB)"}, status=400)

    if f.content_type not in _ALLOWED_MIME:
        return JsonResponse({"error": "Tipe file tidak diizinkan. Gunakan PDF, gambar, Excel, atau CSV."}, status=400)

    att = Attachment(name=f.name, size=f.size)
    if invoice_id:
        att.invoice = get_object_or_404(Invoice, pk=invoice_id)
    else:
        att.cl = get_object_or_404(ConfirmationLetter, pk=cl_id)
    att.file = f
    att.save()

    return JsonResponse({
        "id": att.pk,
        "name": att.name,
        "size": att.size,
        "url": att.file.url,
        "icon": att.icon,
        "is_image": att.is_image,
    })


@login_required
@require_POST
def attachment_delete(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    try:
        if att.file and os.path.isfile(att.file.path):
            os.remove(att.file.path)
    except Exception:
        pass
    att.delete()
    return JsonResponse({"ok": True})
