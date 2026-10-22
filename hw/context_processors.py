from datetime import date, timedelta

from django.core.cache import cache
from django.urls import reverse

from .branch_scope import scope
from .models import ConfirmationLetter, Invoice
from .permissions import can


def _cl_notifs(user, kind, field, today, threshold, limit):
    qs = (
        scope(ConfirmationLetter.objects.all(), user)
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


def _invoice_notifs(user, today, threshold, limit, invoice_types):
    qs = scope(Invoice.objects.all(), user).filter(
        due_date__lte=threshold, due_date__gte=today, invoice_type__in=invoice_types)

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
    # Per branch picked too: switching branch must not show the last one's.
    cache_key = f"due_soon_u{request.user.id}_{getattr(request.user, '_active_branch', '') or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    today = date.today()
    threshold = today + timedelta(days=7)
    limit = 20

    # Only what the user may view: hotel invoices (invoice), CL check-ins
    # (cl) — of the user's branches.
    user = request.user
    invoice_types = ['hotel'] if can(user, 'invoice', 'view') else []
    notifs = []
    if invoice_types:
        notifs += _invoice_notifs(user, today, threshold, limit, invoice_types)
    if can(user, 'cl', 'view'):
        notifs += _cl_notifs(user, 'check_in', 'check_in', today, threshold, limit)
    notifs.sort(key=lambda n: n["days"])

    result = {
        "due_soon_count": len(notifs),
        "due_soon_notifs": notifs,
    }
    cache.set(cache_key, result, 300)  # cache 5 menit
    return result
