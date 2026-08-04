import os
import magic

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from django.db.models import Q

from ..models import Attachment, ConfirmationLetter, Invoice
from ..permissions import require_perm
from .helpers import get_active_company

_ALLOWED_MIME = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv', 'text/plain',
}

_MIME_TO_EXT = {
    'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp',
    'application/pdf': '.pdf',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'text/csv': '.csv', 'text/plain': '.txt',
}


@require_perm('invoice', 'edit')
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
        return JsonResponse({"error": "File too large (max 10 MB)"}, status=400)

    # Read first 2048 bytes for magic detection
    header = f.read(2048)
    f.seek(0)
    detected_mime = magic.from_buffer(header, mime=True)

    if detected_mime not in _ALLOWED_MIME:
        return JsonResponse({"error": "File type not allowed. Use PDF, image, Excel, or CSV."}, status=400)

    # Optional: verify extension matches detected type
    ext = os.path.splitext(f.name)[1].lower()
    expected_ext = _MIME_TO_EXT.get(detected_mime)
    if expected_ext and ext != expected_ext:
        return JsonResponse({"error": f"File extension {ext} does not match content type {detected_mime}."}, status=400)

    active_company = get_active_company(request)
    att = Attachment(name=f.name, size=f.size)
    if invoice_id:
        att.invoice = get_object_or_404(Invoice, pk=invoice_id, company=active_company)
    else:
        att.cl = get_object_or_404(ConfirmationLetter, pk=cl_id, company=active_company)
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


@require_perm('invoice', 'edit')
@require_POST
def attachment_delete(request, pk):
    active_company = get_active_company(request)
    qs = Attachment.objects.filter(Q(invoice__company=active_company) | Q(cl__company=active_company))
    att = get_object_or_404(qs, pk=pk)
    try:
        if att.file and os.path.isfile(att.file.path):
            os.remove(att.file.path)
    except Exception:
        pass
    att.delete()
    return JsonResponse({"ok": True})
