from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse

from ..models import ConfirmationLetter, Invoice
from ..branch_scope import scope
from ..permissions import can


@login_required
def global_search(request):
    """Search across CLs, hotel invoices and services — each only for a user
    who may view that module, and only the user's branches' records."""
    q = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"results": [], "q": q})

    user = request.user
    cl_qs = scope(ConfirmationLetter.objects.with_parties(), user).filter(
        ConfirmationLetter.objects.name_matches(q)
    )[:8] if can(user, "cl", "view") else []

    inv_qs = (
        scope(Invoice.objects.all(), user).filter(invoice_type="hotel")
        .filter(Invoice.objects.name_matches(q))
        .with_lines()
    )[:8] if can(user, "invoice", "view") else []

    svc_qs = (
        scope(Invoice.objects.all(), user).filter(invoice_type="visa")
        .filter(Invoice.objects.name_matches(q))
        .with_lines()
    )[:8] if can(user, "services", "view") else []

    results = []
    for cl in cl_qs:
        results.append({
            "type": "CL",
            "label": cl.confirmation_number,
            "sub": cl.guest_name,
            "meta": cl.hotel_name or "",
            "url": reverse("cl_detail", args=[cl.pk]),
        })
    for inv in inv_qs:
        results.append({
            "type": "INV",
            "label": inv.invoice_number,
            "sub": inv.customer_name,
            "meta": "Lunas" if inv.remaining_sar == 0 else f"Sisa {inv.remaining_sar:,} SAR",
            "url": reverse("invoice_detail", args=[inv.pk]),
        })
    for svc in svc_qs:
        results.append({
            "type": "SVC",
            "label": svc.invoice_number,
            "sub": svc.customer_name,
            "meta": "Lunas" if svc.remaining_sar == 0 else f"Sisa {svc.remaining_sar:,} SAR",
            "url": reverse("services_detail", args=[svc.pk]),
        })

    return JsonResponse({"results": results, "q": q})
