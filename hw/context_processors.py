from datetime import date, timedelta

from django.core.cache import cache
from django.urls import reverse

from .models import ConfirmationLetter, Invoice
from .permissions import can


def _cl_notifs(kind, field, today, threshold, limit):
    qs = (
        ConfirmationLetter.objects
        .filter(**{f"{field}__lte": threshold, f"{field}__gte": today})
        .exclude(reservation_status='CANCELLED')
        .order_by(field)
    )

    notifs = []
    for cl in qs[:limit]:
        days = (getattr(cl, field) - today).days
        notifs.append({
            "type": kind,
            "ref": cl.confirmation_number,
            "days": days,
            "title": cl.guest_name,
            "meta": cl.hotel_name,
            "url": reverse("cl_detail", args=[cl.pk]),
        })
    return notifs


def _invoice_notifs(today, threshold, limit, invoice_types):
    qs = Invoice.objects.filter(due_date__lte=threshold, due_date__gte=today, invoice_type__in=invoice_types)

    notifs = []
    for inv in qs.with_lines().order_by("due_date")[:limit]:
        if inv.remaining_sar <= 0:
            continue
        days = (inv.due_date - today).days
        notifs.append({
            "type": "invoice_due",
            "ref": inv.invoice_number,
            "days": days,
            "title": inv.customer_name,
            "remaining": round(inv.remaining_sar),
            "url": reverse("invoice_detail", args=[inv.pk]),
        })
    return notifs


def due_soon(request):
    if not request.user.is_authenticated:
        return {}
    cache_key = f'due_soon_u{request.user.id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    today = date.today()
    threshold = today + timedelta(days=7)
    limit = 20

    # Only what the user may view: hotel invoices (invoice), services
    # invoices (services), CL check-ins (cl).
    user = request.user
    invoice_types = [t for t, module in (('hotel', 'invoice'), ('visa', 'services')) if can(user, module, 'view')]
    notifs = []
    if invoice_types:
        notifs += _invoice_notifs(today, threshold, limit, invoice_types)
    if can(user, 'cl', 'view'):
        notifs += _cl_notifs('check_in', 'check_in', today, threshold, limit)
    notifs.sort(key=lambda n: n["days"])

    result = {
        "due_soon_count": len(notifs),
        "due_soon_notifs": notifs,
    }
    cache.set(cache_key, result, 300)  # cache 5 menit
    return result
