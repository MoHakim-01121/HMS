from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse

from ..models import Client, ConfirmationLetter, Hotel, Invoice, PaymentRecord
from ..branch_scope import scope
from ..permissions import can


@login_required
def global_search(request):
    """Search across CLs, invoices, payments, clients and hotels — each only
    for a user who may view that module, and only the branch they look at.
    Each row carries `num` (the document number, if any) and `name` for the
    topbar's two-part row; `sub`/`label` stay for older callers."""
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

    pay_qs = (
        scope(PaymentRecord.objects.select_related('client', 'receiving_account'), user)
        .filter(Q(payment_number__icontains=q) | Q(client__name__icontains=q) | Q(client__brand__icontains=q))
        .order_by('-payment_date')
    )[:8] if can(user, "payments", "view") else []

    client_qs = (
        scope(Client.objects.all(), user)
        .filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(city__icontains=q))
        .order_by('name')
    )[:8] if can(user, "clients", "view") else []

    hotel_qs = (
        Hotel.objects.filter(is_active=True).filter(Q(name__icontains=q) | Q(area__icontains=q))
        .order_by('name')
    )[:8] if can(user, "hotels", "view") else []

    results = []
    for cl in cl_qs:
        results.append({
            "type": "CL",
            "label": cl.confirmation_number,
            "num": cl.confirmation_number,
            "name": cl.guest_name,
            "sub": cl.guest_name,
            "meta": cl.hotel_name or "",
            "url": reverse("cl_detail", args=[cl.pk]),
        })
    for inv in inv_qs:
        results.append({
            "type": "INV",
            "label": inv.invoice_number,
            "num": inv.invoice_number,
            "name": inv.customer_name,
            "sub": inv.customer_name,
            "meta": "Lunas" if inv.remaining_sar == 0 else f"Sisa {inv.remaining_sar:,} SAR",
            "url": reverse("invoice_detail", args=[inv.pk]),
        })
    for p in pay_qs:
        results.append({
            "type": "PAY",
            "label": p.payment_number,
            "num": p.payment_number,
            "name": p.client.name,
            "sub": p.client.name,
            "meta": f"{p.currency} {p.amount:,}",
            "url": reverse("payment_detail", args=[p.pk]),
        })
    for c in client_qs:
        results.append({
            "type": "CLIENT",
            "label": c.brand or c.name,
            "num": "",
            "name": c.brand or c.name,
            "sub": c.name,
            "meta": c.city,
            "url": reverse("client_detail", args=[c.pk]),
        })
    for h in hotel_qs:
        results.append({
            "type": "HOTEL",
            "label": h.name,
            "num": "",
            "name": h.name,
            "sub": h.area,
            "meta": f"{h.get_city_display()}, {h.stars} star",
            "url": reverse("hotel_detail", args=[h.pk]),
        })

    return JsonResponse({"results": results, "q": q})
