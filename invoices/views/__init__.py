import json

from django.contrib.auth.decorators import login_required
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


@login_required
def company_select(request):
    if request.method == "POST":
        company = request.POST.get("company")
        if company in ("konoz", "ijabah"):
            request.session["active_company"] = company
            request.session.modified = True
            return redirect("home")
    return render(request, "invoices/company_select.html")


@login_required
def company_switch(request):
    request.session.pop("active_company", None)
    return redirect("company_select")


@login_required
@require_POST
def company_quick_set(request):
    company = request.POST.get("company")
    if company in ("konoz", "ijabah"):
        request.session["active_company"] = company
        request.session.modified = True
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
def home(request):
    if not request.session.get("active_company"):
        request.session["active_company"] = "konoz"
        request.session.modified = True
    return render(request, "invoices/home.html")


@login_required
@require_POST
def ai_draft_message(request):
    try:
        data = json.loads(request.body)
        invoice_type = data.get("type", "invoice")
        pk = int(data.get("pk"))
    except Exception:
        return JsonResponse({"error": "Request tidak valid."}, status=400)

    from ..models import Invoice
    from ..ai import generate_draft_message
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

    from ..ai import get_chat_reply
    active_company = request.session.get("active_company")
    reply = get_chat_reply(message, company=active_company)
    return JsonResponse({"reply": reply or "Maaf, tidak dapat memproses pertanyaan saat ini."})
