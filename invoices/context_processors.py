from datetime import date, timedelta

from .models import Invoice


def due_soon(request):
    if not request.user.is_authenticated:
        return {}
    active_company = request.session.get("active_company")
    today = date.today()
    threshold = today + timedelta(days=7)
    qs = Invoice.objects.filter(due_date__lte=threshold, due_date__gte=today)
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
            "url": f"/invoice/{inv.pk}/",
        })

    return {
        "due_soon_count": len(notifs),
        "due_soon_notifs": notifs,
    }
