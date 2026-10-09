"""Dashboard (home) view and its widget helpers.

One feature only: the signed-in landing screen at /dashboard/. Marketing
pages live in landing_views.py.
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth

from inertia import render as inertia_render

from ..finance import queries as finance_queries
from ..models import ConfirmationLetter, Invoice, Remittance
from ..models.choices import InvoiceType
from ..branch_scope import covers_all, scope
from ..permissions import can


def _pct(cur, prev):
    if not prev:
        return None
    pct = round(((cur - prev) / prev) * 100)
    return {"dir": "flat" if pct == 0 else ("up" if pct > 0 else "down"),
            "pct": abs(pct), "cur": cur, "prev": prev}


def _home_invoice_totals(month_start, invoices):
    """Billed/paid/unpaid snapshot over hotel invoices.

    Paid amounts come from one bulk ledger query (invoice_paid_sar_map) --
    reading Invoice.total_paid_sar per row used to cost one query each.
    """
    hotel_invoices = list(
        invoices.filter(invoice_type=InvoiceType.HOTEL).with_lines()
    )
    paid_map = finance_queries.invoice_paid_map([inv.pk for inv in hotel_invoices])

    total_billed = 0
    total_paid = 0
    unpaid_count = 0
    unpaid_total = 0
    for inv in hotel_invoices:
        paid = paid_map.get(inv.pk, 0)
        billed = inv.total_sar
        total_billed += billed
        total_paid += paid
        remaining = billed - paid
        if remaining > 0:
            unpaid_count += 1
            unpaid_total += remaining

    # Outstanding SAR as of the end of last month — bills issued before this
    # month minus payments dated before this month. Powers the unpaid delta.
    prev_unpaid_total = 0
    prev_invoices = list(invoices.filter(
        invoice_type=InvoiceType.HOTEL,
        created_at__date__lt=month_start,
    ).with_lines())
    if prev_invoices:
        prev_paid_map = finance_queries.invoice_paid_map_before(
            [inv.pk for inv in prev_invoices], month_start,
        )
        for inv in prev_invoices:
            remaining = max(inv.total_sar - prev_paid_map.get(inv.pk, 0), 0)
            if remaining > 0:
                prev_unpaid_total += remaining

    return {
        "billed": total_billed,
        "paid": total_paid,
        "unpaid_count": unpaid_count,
        "unpaid_total": unpaid_total,
        "prev_unpaid_total": prev_unpaid_total,
    }


def _home_cl_trends(today, cls):
    """CL volume series for the dashboard chart: monthly for 12 months and
    daily for 30 days, both zero-filled so quiet spans still show a labeled
    baseline instead of a gap. Also returns counts_by_month so the deltas can
    reuse it without a second aggregate."""
    twelve_months_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    for _ in range(11):
        twelve_months_start = (twelve_months_start - timedelta(days=1)).replace(day=1)
    monthly_counts = (
        cls.filter(created_at__date__gte=twelve_months_start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
    )
    counts_by_month = {row["month"].strftime("%Y-%m"): row["count"] for row in monthly_counts}
    cl_trend = []
    cursor = twelve_months_start
    for _ in range(12):
        key = cursor.strftime("%Y-%m")
        cl_trend.append({"label": cursor.strftime("%b"), "count": counts_by_month.get(key, 0)})
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    thirty_days_start = today - timedelta(days=29)
    daily_counts = (
        cls.filter(created_at__date__gte=thirty_days_start)
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_by_day = {row["created_at__date"]: row["count"] for row in daily_counts}
    cl_daily = []
    for i in range(30):
        d = thirty_days_start + timedelta(days=i)
        cl_daily.append({"label": d.strftime("%b %d"), "count": counts_by_day.get(d, 0)})

    return counts_by_month, cl_trend, cl_daily


def _home_widgets(today, cls):
    """Third-row dashboard widgets: top hotels by CL volume, client-region
    heat map, reservation lifecycle funnel, and the six most recent CLs."""
    top_hotels = [
        {"hotel": row["hotel__name"], "count": row["n"]}
        for row in (
            cls
            .values("hotel__name")
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        )
    ]
    top_hotels_total = cls.count()

    region_data = [
        {"province": row["client__province"], "count": row["n"]}
        for row in (
            cls
            .exclude(client__isnull=True)
            .exclude(client__province="")
            .values("client__province")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
    ]

    # Each funnel stage is a strict subset of the previous one so the bars
    # shrink monotonically: every CL → confirmed (DEFINITE) → completed.
    funnel_cls = cls
    reservation_funnel = [
        {"label": "total", "value": funnel_cls.count()},
        {"label": "confirmed", "value": funnel_cls.filter(reservation_status="DEFINITE").count()},
        {"label": "completed", "value": funnel_cls.filter(reservation_status="DEFINITE", check_out__lte=today).count()},
    ]

    recent_cls = [
        {
            "id": cl.pk,
            "guest_name": cl.guest_name,
            "confirmation_number": cl.confirmation_number,
            "hotel_name": cl.hotel_name,
            "check_in": cl.check_in.isoformat() if cl.check_in else None,
            "reservation_status": cl.reservation_status,
        }
        for cl in cls.order_by("-created_at")[:6]
    ]

    return top_hotels, top_hotels_total, region_data, reservation_funnel, recent_cls


def _home_finance_summary():
    from ..finance import accounts as coa
    from ..finance_helpers import kas_saldo
    from ..models.payment import PaymentRecord

    today = date.today()
    return {
        'kas_sby': kas_saldo(coa.CASH_SBY),
        'kas_pusat': kas_saldo(coa.CASH_PUSAT),
        'total_piutang': kas_saldo(coa.AR),
        'payments_pending': PaymentRecord.objects.filter(status=PaymentRecord.STATUS_PENDING).count(),
        'payments_this_month': PaymentRecord.objects.filter(
            created_at__year=today.year,
            created_at__month=today.month,
        ).count(),
    }


@login_required
def home(request):
    """Dashboard. Each panel is computed only for a user who may view the
    module it comes from, over the user's branches; the rest arrive as None
    and are not drawn."""
    user = request.user
    cls = scope(ConfirmationLetter.objects.all(), user)
    can_cl = can(user, 'cl', 'view')
    can_invoice = can(user, 'invoice', 'view')
    today = date.today()
    week_ahead = today + timedelta(days=7)
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    next_month_start = (month_start + timedelta(days=31)).replace(day=1)

    deltas = {}
    cl_month_count = upcoming_checkins = None
    cl_trend = cl_daily = recent_cls = None
    top_hotels = top_hotels_total = region_data = reservation_funnel = None
    if can_cl:
        cl_month_count = cls.filter(
            created_at__year=today.year, created_at__month=today.month,
        ).count()
        upcoming_checkins = cls.filter(
            check_in__gte=today, check_in__lte=week_ahead,
        ).count()
        # Prior 7-day window (actual check-ins) — the reference for the
        # "Check-ins Next 7 Days" MoM-style delta.
        prev_checkins = cls.filter(
            check_in__gte=today - timedelta(days=7), check_in__lt=today,
        ).count()
        counts_by_month, cl_trend, cl_daily = _home_cl_trends(today, cls)
        deltas["cl_month"] = _pct(cl_month_count, counts_by_month.get(prev_month_start.strftime("%Y-%m"), 0))
        deltas["checkins"] = _pct(upcoming_checkins, prev_checkins)
        # Third-row widgets — Homlu "Top countries" becomes top hotels by total CL
        # volume (all-time), "World map" becomes an Indonesia client-region heat
        # map, and "Conversion funnel" becomes the reservation lifecycle. All are
        # honest to current data: quiet panels simply show their empty state and
        # light up as hotels/provinces/statuses get recorded.
        top_hotels, top_hotels_total, region_data, reservation_funnel, recent_cls = _home_widgets(today, cls)

    unpaid_invoices = unpaid_total = payment_snapshot = None
    if can_invoice:
        invoice_totals = _home_invoice_totals(month_start, scope(Invoice.objects.all(), user))
        unpaid_invoices = invoice_totals["unpaid_count"]
        unpaid_total = invoice_totals["unpaid_total"]
        deltas["unpaid"] = _pct(invoice_totals["unpaid_total"], invoice_totals["prev_unpaid_total"])
        payment_snapshot = {
            "billed": invoice_totals["billed"],
            "collected": invoice_totals["paid"],
            "outstanding": max(invoice_totals["billed"] - invoice_totals["paid"], 0),
        }

    remittance_pending = None
    if can(user, 'remittance', 'view'):
        remittance_pending = len(Remittance.objects.pending())
        # Remittance MoM: pending remittances dated this month vs last month.
        rem_pending_this = len(Remittance.objects.filter(date__gte=month_start, date__lt=next_month_start).pending())
        rem_pending_prev = len(Remittance.objects.filter(date__gte=prev_month_start, date__lt=month_start).pending())
        deltas["remittance"] = _pct(rem_pending_this, rem_pending_prev)

    # Cash balances and receivables of the whole organisation, as the Bank
    # Balances page shows them: head office only.
    finance_summary = (_home_finance_summary()
                       if can(user, 'statements', 'view') and covers_all(user) else None)

    return inertia_render(request, "Home/Index", props={
        "kpis": {
            "cl_month": cl_month_count,
            "upcoming_checkins": upcoming_checkins,
            "unpaid_invoices": unpaid_invoices,
            "unpaid_total": unpaid_total,
            "remittance_pending": remittance_pending,
            "deltas": deltas,
        },
        "cl_trend": cl_trend,
        "cl_daily": cl_daily,
        "recent_cls": recent_cls,
        "payment_snapshot": payment_snapshot,
        "top_hotels": top_hotels,
        "top_hotels_total": top_hotels_total,
        "region_data": region_data,
        "reservation_funnel": reservation_funnel,
        "finance_summary": finance_summary,
    })
