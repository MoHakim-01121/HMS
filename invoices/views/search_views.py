from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

from ..models import ConfirmationLetter, Invoice


@login_required
def global_search(request):
    q = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"results": [], "q": q})

    active_company = request.session.get("active_company")

    def _co(qs):
        return qs.filter(company=active_company) if active_company else qs

    cl_qs = _co(ConfirmationLetter.objects.filter(
        Q(confirmation_number__icontains=q) |
        Q(guest_name__icontains=q) |
        Q(hotel_name__icontains=q)
    ))[:8]

    inv_qs = _co(Invoice.objects.filter(invoice_type="hotel").filter(
        Q(invoice_number__icontains=q) | Q(customer_name__icontains=q)
    ))[:8]

    svc_qs = _co(Invoice.objects.filter(invoice_type="visa").filter(
        Q(invoice_number__icontains=q) | Q(customer_name__icontains=q)
    ))[:8]

    results = []
    for cl in cl_qs:
        results.append({
            "type": "CL",
            "label": cl.confirmation_number,
            "sub": cl.guest_name,
            "meta": cl.hotel_name or "",
            "url": f"/cl/{cl.pk}/",
        })
    for inv in inv_qs:
        results.append({
            "type": "INV",
            "label": inv.invoice_number,
            "sub": inv.customer_name,
            "meta": "Lunas" if inv.remaining_sar == 0 else f"Sisa {inv.remaining_sar:,} SAR",
            "url": f"/invoice/{inv.pk}/",
        })
    for svc in svc_qs:
        results.append({
            "type": "SVC",
            "label": svc.invoice_number,
            "sub": svc.customer_name,
            "meta": "Lunas" if svc.remaining_sar == 0 else f"Sisa {svc.remaining_sar:,} SAR",
            "url": f"/services/{svc.pk}/",
        })

    return JsonResponse({"results": results, "q": q})
