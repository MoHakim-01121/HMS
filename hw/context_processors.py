from datetime import date, timedelta

from django.core.cache import cache
from django.urls import reverse

from .models import Invoice


def due_soon(request):
    if not request.user.is_authenticated:
        return {}
    active_company = request.session.get("active_company")
    cache_key = f'due_soon_u{request.user.id}_{active_company}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    today = date.today()
    threshold = today + timedelta(days=7)
    qs = (
        Invoice.objects
        .filter(due_date__lte=threshold, due_date__gte=today)
        .prefetch_related('reservations', 'payments')
    )
    if active_company:
        qs = qs.filter(company=active_company)

    notifs = []
    for inv in qs.order_by("due_date")[:20]:
        if inv.remaining_sar <= 0:
            continue
        days = (inv.due_date - today).days
        if days == 0:
            label = "Jatuh tempo hari ini"
        elif days == 1:
            label = "Besok"
        else:
            label = f"{days} hari lagi"
        notifs.append({
            "inv_number": inv.invoice_number,
            "customer": inv.customer_name,
            "remaining": inv.remaining_sar,
            "days": days,
            "label": label,
            "url": reverse("invoice_detail", args=[inv.pk]),
        })

    result = {
        "due_soon_count": len(notifs),
        "due_soon_notifs": notifs,
    }
    cache.set(cache_key, result, 300)  # cache 5 menit
    return result
