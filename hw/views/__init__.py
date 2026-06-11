import json
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .cl_views import (
    cl_delete, cl_detail, cl_duplicate, cl_edit, cl_export_csv, cl_list,
    cl_list_pdf, cl_new, cl_pdf, invoice_from_cls,
)
from .invoice_views import (
    invoice_delete, invoice_detail, invoice_duplicate, invoice_edit,
    invoice_export_csv, invoice_list, invoice_list_pdf, invoice_new, invoice_pdf,
)
from .services_views import (
    services_delete, services_detail, services_duplicate, services_edit,
    services_export_csv, services_list, services_list_pdf, services_new, services_pdf,
)
from .calendar_views import calendar_view
from .search_views import global_search
from .attachment_views import attachment_delete, attachment_upload
from .user_views import account_profile, avatar_delete, avatar_upload, user_delete, user_edit, user_list, user_new
from .client_views import (
    client_list, client_new, client_edit, client_delete,
    client_detail, client_map, client_map_data,
)
from .hotel_views import (
    hotel_list, hotel_new, hotel_edit, hotel_delete,
    hotel_detail, hotel_map, hotel_map_data,
)
from .remittance_views import (
    remittance_list, remittance_new, remittance_detail, remittance_edit,
    remittance_pdf, remittance_delete, remittance_upload_proof, remittance_export_csv,
    remittance_mark_received, remittance_recap, remittance_period_pdf,
)
from .penalty_views import (
    penalty_list, penalty_new, penalty_detail, penalty_edit, penalty_delete, penalty_pdf,
)

from ..ai import generate_draft_message, get_chat_reply
from ..models import Invoice



@login_required
@require_POST
def company_quick_set(request):
    company = request.POST.get("company")
    if company in ("konoz", "ijabah"):
        request.session["active_company"] = company
        request.session.modified = True

    referer = request.META.get("HTTP_REFERER", "/")
    try:
        parsed = urlparse(referer)
        # Reject external redirects — only allow same host
        if parsed.netloc and parsed.netloc != request.get_host():
            safe_url = "/"
        else:
            safe_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    except Exception:
        safe_url = "/"

    sep = "&" if "?" in safe_url else "?"
    return redirect(f"{safe_url}{sep}company_changed={company}")


@login_required
def home(request):
    if not request.session.get("active_company"):
        request.session["active_company"] = "konoz"
        request.session.modified = True
    return render(request, "hw/home.html")


@login_required
@require_POST
def ai_draft_message(request):
    try:
        data = json.loads(request.body)
        invoice_type = data.get("type", "invoice")
        pk = int(data.get("pk"))
    except Exception:
        return JsonResponse({"error": "Request tidak valid."}, status=400)

    invoice = Invoice.objects.filter(pk=pk).first()
    if not invoice:
        return JsonResponse({"error": "Invoice tidak ditemukan."}, status=404)

    result = generate_draft_message(invoice_type, invoice)
    return JsonResponse({"message": result or "Gagal generate pesan."})


@login_required
@require_POST
def ai_chat(request):
    try:
        data = json.loads(request.body)
        message = data.get("message", "").strip()
    except Exception:
        return JsonResponse({"reply": "Request tidak valid."}, status=400)

    if not message:
        return JsonResponse({"reply": "Pertanyaan tidak boleh kosong."})

    active_company = request.session.get("active_company")
    history = request.session.get("ai_history", [])

    reply = get_chat_reply(message, company=active_company, history=history)

    if reply:
        history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]
        request.session["ai_history"] = history[-6:]  # simpan 3 exchange terakhir

    return JsonResponse({"reply": reply or "Maaf, tidak dapat memproses pertanyaan saat ini."})


def health_check(request):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/health/')
    if not request.user.is_superuser:
        from django.http import Http404
        raise Http404
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "ok", "db": "ok"})
    except Exception:
        return JsonResponse({"status": "error", "db": "unreachable"}, status=500)
