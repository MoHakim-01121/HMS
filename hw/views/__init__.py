import json
from datetime import date, timedelta
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import redirect
from django.templatetags.static import static
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from inertia import render as inertia_render

from .cl_views import (
    cl_delete, cl_detail, cl_duplicate, cl_edit, cl_export_csv, cl_list,
    cl_list_pdf, cl_list_pdf_v2, cl_new, cl_pdf, invoice_from_cls,
)
from .invoice_views import (
    invoice_delete, invoice_detail, invoice_duplicate, invoice_edit,
    invoice_export_csv, invoice_list, invoice_list_pdf, invoice_new, invoice_pdf,
)
from .services_views import (
    services_delete, services_detail, services_duplicate, services_edit,
    services_export_csv, services_list, services_list_pdf, services_new, services_pdf,
)
from .calendar_views import (
    calendar_view, cl_estimasi_save, calendar_send_recap,
    calendar_send_reminder_group,
    wa_target_add, wa_target_toggle, wa_target_delete,
    message_template_save, calendar_recap_settings,
    calendar_checkin_pdf,
)
from .billing_views import billing_send
from .search_views import global_search
from .attachment_views import attachment_delete, attachment_upload
from .user_views import account_profile, account_profile_update, avatar_delete, avatar_upload, user_credential_card, user_delete, user_edit, user_list, user_new, set_language
from .role_views import role_delete, role_edit, role_list, role_new
from .client_views import (
    client_list, client_new, client_edit, client_delete,
    client_detail, client_map, client_map_data,
    client_transfer, client_refund, client_statement_pdf,
)
from .hotel_views import (
    hotel_list, hotel_new, hotel_edit, hotel_delete,
    hotel_detail, hotel_map, hotel_map_data,
)
from .remittance_views import (
    remittance_list, remittance_new, remittance_detail, remittance_edit,
    remittance_pdf, remittance_delete, remittance_upload_proof, remittance_export_csv,
    remittance_mark_received, remittance_recap, remittance_period_pdf,
    remittance_ledger_pdf,
)
from .penalty_views import (
    penalty_new, penalty_detail, penalty_edit, penalty_delete, penalty_pdf,
)
from .period_views import (
    period_list, period_detail, period_close, period_lock, period_create,
)
from .payment_views import (
    payment_list, payment_detail, payment_record_new, payment_record,
    payment_confirm, payment_reject, payment_reverse,
    client_finance_statement, payment_export_csv,
)
from .dev_views import style_guide
from .visit_views import (
    visit_cancel, visit_complete, visit_detail, visit_edit, visit_list,
    visit_new, visit_pdf, visit_photo_delete, visit_photo_upload, visit_recap,
)
from .landing_views import (
    landing_manage, team_new, team_edit, team_delete,
    pricelist_new, pricelist_edit, pricelist_delete,
)

from ..ai import generate_draft_message, get_chat_reply
from ..models import ActivityLog, ConfirmationLetter, Hotel, Invoice, Pricelist, Remittance, TeamMember, log_activity
from ..models.choices import Company
from ..permissions import can, can_use_company, default_company, hide_unless
from .helpers import get_active_company



@login_required
@require_POST
def company_quick_set(request):
    company = request.POST.get("company")
    # Silently ignore a company the user has no access to — the switcher never
    # offers it, so a request for one is either a stale tab or a hand-crafted
    # POST. Either way the session must not adopt it.
    if company in Company.values and can_use_company(request.user, company):
        request.session["active_company"] = company
        request.session.modified = True
    else:
        company = get_active_company(request)

    referer = request.META.get("HTTP_REFERER", "/dashboard/")
    try:
        parsed = urlparse(referer)
        # Reject external redirects — only allow same host
        if parsed.netloc and parsed.netloc != request.get_host():
            safe_url = "/dashboard/"
        else:
            safe_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    except Exception:
        safe_url = "/dashboard/"

    sep = "&" if "?" in safe_url else "?"
    return redirect(f"{safe_url}{sep}company_changed={company}")


def landing(request):
    # A signed-in staff member has no reason to see the marketing page —
    # bookmarks and links to "/" (old dashboard URL, error-page "Back to
    # Home" links, LOGIN_REDIRECT_URL fallbacks) should still land them on
    # their dashboard. Staff who manage the landing page's content can add
    # ?preview=1 to see the live public page instead of being bounced.
    preview = request.GET.get('preview') == '1' and can(request.user, 'landing', 'view')
    if request.user.is_authenticated and not preview:
        return redirect('home')

    active_hotels = Hotel.objects.filter(is_active=True)
    featured_hotels = [
        {
            "id": h.id,
            "name": h.name,
            "city": h.city,
            "city_display": h.get_city_display(),
            "area": h.area,
            "stars": h.stars,
            "distance_label": h.distance_label,
            "walk_label": h.walk_label,
            "note": h.note,
        }
        for h in active_hotels.order_by("-stars", "name")[:6]
    ]
    team_members = [
        {
            "id": m.id,
            "name": m.name,
            "position": m.position,
            "wa": m.wa,
            "photo_url": m.photo.url if m.photo else None,
        }
        for m in TeamMember.objects.filter(is_active=True).order_by("order", "id")
    ]
    pricelist = Pricelist.objects.filter(is_active=True).order_by("-updated_at").first()
    return inertia_render(request, "Landing/Index", props={
        "stats": {
            "total_hotels": active_hotels.count(),
            "cities_covered": active_hotels.values_list("city", flat=True).distinct().count(),
        },
        "featured_hotels": featured_hotels,
        "team_members": team_members,
        "pricelist": {
            "id": pricelist.id,
            "title": pricelist.title,
            "file_url": pricelist.file.url if pricelist.file else None,
        } if pricelist else None,
    }, template_data={
        # Server-rendered (not JS-injected) so link-preview crawlers that
        # never execute JS — WhatsApp, Telegram, Facebook — see a real
        # title/image instead of the generic "Workspace" shell default.
        "page_title": "Konoz United — Broker Hotel Umrah & Haji di Makkah & Madinah",
        "meta_description": (
            "Konoz United melayani agen travel Umrah & Haji dengan inventori hotel "
            "berkontrak langsung di Makkah & Madinah: reservasi, Confirmation Letter, "
            "hingga pembayaran."
        ),
        "og_image": request.build_absolute_uri(static("hw/img/og-landing.jpg")),
    })


def public_hotels(request):
    active_hotels = Hotel.objects.filter(is_active=True)
    qs = active_hotels
    q            = request.GET.get('q', '').strip()
    city_filter  = request.GET.get('city', '').strip()
    stars_filter = request.GET.get('stars', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(area__icontains=q))
    if city_filter in ('makkah', 'madinah'):
        qs = qs.filter(city=city_filter)
    if stars_filter.isdigit():
        qs = qs.filter(stars=int(stars_filter))
    qs = qs.order_by('city', '-stars', 'name')

    hotels = [{
        "id": h.id,
        "name": h.name,
        "city": h.city,
        "city_display": h.get_city_display(),
        "area": h.area,
        "stars": h.stars,
        "distance": h.distance_to_haram,
        "distance_label": h.distance_label,
        "walk_label": h.walk_label,
        "note": h.note,
    } for h in qs]

    pricelist = Pricelist.objects.filter(is_active=True).order_by('-updated_at').first()

    # Facet counts — Booking.com/Trivago pattern: each facet is counted over
    # the current query with that facet itself removed, so the numbers stay
    # stable and meaningful while the user narrows down.
    base = active_hotels
    if q:
        base = base.filter(Q(name__icontains=q) | Q(area__icontains=q))
    base_for_city   = base.filter(stars=int(stars_filter)) if stars_filter.isdigit() else base
    base_for_star   = base.filter(city=city_filter) if city_filter in ('makkah', 'madinah') else base

    count_by_star = {}
    for s in (3, 4, 5):
        count_by_star[str(s)] = base_for_star.filter(stars=s).count()

    dist_hotels = list(base_for_star)
    count_by_distance = {
        "500": sum(1 for h in dist_hotels if h.distance_to_haram is not None and h.distance_to_haram <= 500),
        "1000": sum(1 for h in dist_hotels if h.distance_to_haram is not None and h.distance_to_haram <= 1000),
        "2000": sum(1 for h in dist_hotels if h.distance_to_haram is not None and h.distance_to_haram <= 2000),
    }

    return inertia_render(request, "Landing/Hotels", props={
        "hotels": hotels,
        "q": q,
        "city_filter": city_filter,
        "stars_filter": stars_filter,
        "stats": {
            "total_hotels": active_hotels.count(),
            "cities_covered": active_hotels.values_list("city", flat=True).distinct().count(),
            "count_by_city": {
                "makkah": base_for_city.filter(city="makkah").count(),
                "madinah": base_for_city.filter(city="madinah").count(),
            },
            "count_by_star": count_by_star,
            "count_by_distance": count_by_distance,
        },
        "pricelist": {
            "id": pricelist.id,
            "title": pricelist.title,
            "file_url": pricelist.file.url if pricelist.file else None,
        } if pricelist else None,
    }, template_data={
        "page_title": "Hotel Kami — Konoz United",
        "meta_description": (
            "Jelajahi seluruh hotel partner Konoz United di Makkah & Madinah — "
            "reservasi hotel berkontrak langsung untuk agen travel Umrah & Haji."
        ),
        "og_image": request.build_absolute_uri(static("hw/img/og-landing.jpg")),
    })


@login_required
def home(request):
    company = get_active_company(request)
    if request.session.get("active_company") != company:
        # Either unset, or pointing at a company this user may no longer use.
        request.session["active_company"] = company
        request.session.modified = True

    today = date.today()
    week_ahead = today + timedelta(days=7)
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    next_month_start = (month_start + timedelta(days=31)).replace(day=1)

    cl_month_count = ConfirmationLetter.objects.filter(
        company=company, created_at__year=today.year, created_at__month=today.month,
    ).count()

    upcoming_checkins = ConfirmationLetter.objects.filter(
        company=company, check_in__gte=today, check_in__lte=week_ahead,
    ).count()

    # Prior 7-day window (actual check-ins) — the reference for the
    # "Check-ins Next 7 Days" MoM-style delta.
    prev_checkins = ConfirmationLetter.objects.filter(
        company=company, check_in__gte=today - timedelta(days=7), check_in__lt=today,
    ).count()

    unpaid_count = 0
    unpaid_total = 0
    total_billed = 0
    total_paid = 0
    hotel_invoices = Invoice.objects.filter(
        invoice_type="hotel", company=company,
    ).prefetch_related('reservations', 'payments')
    for inv in hotel_invoices:
        total_billed += inv.total_sar
        total_paid += inv.total_paid_sar
        remaining = inv.remaining_sar
        if remaining > 0:
            unpaid_count += 1
            unpaid_total += remaining

    # Outstanding SAR as of the end of last month — bills issued before this
    # month minus payments dated before this month. Powers the unpaid delta.
    prev_unpaid_total = 0
    for inv in hotel_invoices.filter(created_at__date__lt=month_start):
        paid_before = sum(
            p.amount_sar for p in inv.payments.all()
            if p.payment_date and p.payment_date < month_start
        )
        remaining = max(inv.total_sar - paid_before, 0)
        if remaining > 0:
            prev_unpaid_total += remaining

    remittance_pending = (
        Remittance.objects.filter(company=Company.KONOZ, status=Remittance.STATUS_PENDING).count()
        if company == Company.KONOZ and can(request.user, 'remittance', 'view') else None
    )

    # Remittance MoM: pending remittances dated this month vs last month.
    rem_pending_this = Remittance.objects.filter(
        company=Company.KONOZ, status=Remittance.STATUS_PENDING,
        date__gte=month_start, date__lt=next_month_start,
    ).count()
    rem_pending_prev = Remittance.objects.filter(
        company=Company.KONOZ, status=Remittance.STATUS_PENDING,
        date__gte=prev_month_start, date__lt=month_start,
    ).count()

    # Dashboard trend chart (Homlu-style Dashboard & Analytics section): CL
    # volume for the trailing 6 months, oldest first, zero-filled so months
    # with no CLs still show a labeled bar instead of a gap.
    # CL trend series for the chart period toggle: monthly for 6M/12M, daily
    # for 7D/30D. Both are zero-filled so quiet spans still show a labeled
    # baseline instead of a gap.
    twelve_months_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    for _ in range(11):
        twelve_months_start = (twelve_months_start - timedelta(days=1)).replace(day=1)
    monthly_counts = (
        ConfirmationLetter.objects.filter(company=company, created_at__date__gte=twelve_months_start)
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
        ConfirmationLetter.objects.filter(company=company, created_at__date__gte=thirty_days_start)
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_by_day = {row["created_at__date"]: row["count"] for row in daily_counts}
    cl_daily = []
    for i in range(30):
        d = thirty_days_start + timedelta(days=i)
        cl_daily.append({"label": d.strftime("%b %d"), "count": counts_by_day.get(d, 0)})

    def _pct(cur, prev):
        if not prev:
            return None
        pct = round(((cur - prev) / prev) * 100)
        return {"dir": "flat" if pct == 0 else ("up" if pct > 0 else "down"),
                "pct": abs(pct), "cur": cur, "prev": prev}

    deltas = {
        "cl_month": _pct(cl_month_count, counts_by_month.get(prev_month_start.strftime("%Y-%m"), 0)),
        "checkins": _pct(upcoming_checkins, prev_checkins),
        "unpaid": _pct(unpaid_total, prev_unpaid_total),
        "remittance": _pct(rem_pending_this, rem_pending_prev) if remittance_pending is not None else None,
    }

    # Third-row widgets — Homlu "Top countries" becomes top hotels by total CL
    # volume (all-time), "World map" becomes an Indonesia client-region heat
    # map, and "Conversion funnel" becomes the reservation lifecycle. All are
    # honest to current data: quiet panels simply show their empty state and
    # light up as hotels/provinces/statuses get recorded.
    payment_snapshot = {
        "billed": total_billed,
        "collected": total_paid,
        "outstanding": max(total_billed - total_paid, 0),
    }
    top_hotels = [
        {"hotel": row["hotel_name"], "count": row["n"]}
        for row in (
            ConfirmationLetter.objects.filter(company=company)
            .values("hotel_name")
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        )
    ]
    top_hotels_total = ConfirmationLetter.objects.filter(company=company).count()

    region_data = [
        {"province": row["client__province"], "count": row["n"]}
        for row in (
            ConfirmationLetter.objects.filter(company=company)
            .exclude(client__isnull=True)
            .exclude(client__province="")
            .values("client__province")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
    ]

    # Each funnel stage is a strict subset of the previous one so the bars
    # shrink monotonically: every CL → confirmed (DEFINITE) → completed.
    funnel_cls = ConfirmationLetter.objects.filter(company=company)
    reservation_funnel = [
        {"label": "total", "value": funnel_cls.count()},
        {"label": "confirmed", "value": funnel_cls.filter(reservation_status="DEFINITE").count()},
        {"label": "completed", "value": funnel_cls.filter(reservation_status="DEFINITE", check_out__lte=today).count()},
    ]

    recent_cls = [
        {
            "id": cl.id,
            "confirmation_number": cl.confirmation_number,
            "guest_name": cl.guest_name,
            "hotel_name": cl.hotel_name,
            "check_in": cl.check_in.isoformat() if cl.check_in else None,
            "reservation_status": cl.reservation_status,
        }
        for cl in ConfirmationLetter.objects.filter(company=company).order_by("-created_at")[:6]
    ]

    return inertia_render(request, "Home/Index", props={
        "kpis": {
            "cl_month": cl_month_count,
            "upcoming_checkins": upcoming_checkins,
            "unpaid_invoices": unpaid_count,
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
    })


@login_required
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def ai_draft_message(request):
    try:
        data = json.loads(request.body)
        invoice_type = data.get("type", "invoice")
        pk = int(data.get("pk"))
    except Exception:
        return JsonResponse({"error": "Invalid request."}, status=400)

    invoice = Invoice.objects.filter(pk=pk, company=get_active_company(request)).first()
    if not invoice:
        return JsonResponse({"error": "Invoice not found."}, status=404)

    result = generate_draft_message(invoice_type, invoice)
    log_activity(request.user, ActivityLog.ACTION_PDF, f'AI Draft: {invoice_type}', invoice.invoice_number, invoice.company)
    return JsonResponse({"message": result or "Failed to generate message."})


@login_required
@require_POST
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def ai_chat(request):
    try:
        data = json.loads(request.body)
        message = data.get("message", "").strip()
    except Exception:
        return JsonResponse({"reply": "Invalid request."}, status=400)

    if not message:
        return JsonResponse({"reply": "Question cannot be empty."})

    active_company = get_active_company(request)
    history = request.session.get("ai_history", [])

    reply = get_chat_reply(message, company=active_company, history=history)

    if reply:
        history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]
        request.session["ai_history"] = history[-6:]  # keep last 3 exchanges
        log_activity(request.user, ActivityLog.ACTION_PDF, 'AI Chat', message[:100], active_company)

    return JsonResponse({"reply": reply or "Sorry, unable to process your question right now."})


@hide_unless('dev', 'view')
def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({"status": "ok", "db": "ok"})
    except Exception:
        return JsonResponse({"status": "error", "db": "unreachable"}, status=500)
