from datetime import datetime
import magic

from django.http import HttpResponse

PROOF_MAX_SIZE = 10 * 1024 * 1024  # 10 MB, matches attachment_upload
PROOF_ALLOWED_MIME = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
}


def validate_proof_file(f):
    """Reject a payment/remittance/refund proof upload that's oversized or
    isn't actually an image/PDF -- content is sniffed the same way
    attachment_upload does it, rather than trusting the client-supplied
    content-type. Returns an error message, or None if the file is fine."""
    if f.size > PROOF_MAX_SIZE:
        return "File too large (max 10 MB)."
    header = f.read(2048)
    f.seek(0)
    if magic.from_buffer(header, mime=True) not in PROOF_ALLOWED_MIME:
        return "File type not allowed. Use PDF or image (JPG/PNG/GIF/WEBP)."
    return None


def get_active_company(request):
    """Return the session's active company, clamped to what the user may see.

    Callers must always apply this as an unconditional filter, never skip
    filtering when the session key is missing — that gap used to let
    cross-company data leak through list/detail/PDF/CSV views.

    A stored session value the user is no longer allowed to use (access
    revoked while logged in, or a session carried over from before RBAC)
    falls back to their first permitted company instead of being trusted.
    """
    from ..permissions import can_use_company, default_company

    user = getattr(request, "user", None)
    company = request.session.get("active_company")
    if company and can_use_company(user, company):
        return company
    return default_company(user)


def _is_mobile(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    return any(t in ua for t in ('mobi', 'android', 'iphone', 'ipod', 'windows phone'))


def _page_range_display(page_obj):
    current = page_obj.number
    last = page_obj.paginator.num_pages
    result = []
    for i in range(1, last + 1):
        if i == 1 or i == last or abs(i - current) <= 2:
            result.append(i)
        elif result and result[-1] is not None:
            result.append(None)
    return result



def _render_list_pdf(request, qs, template, filename, extra_ctx=None):
    from datetime import datetime as _dt
    from django.conf import settings
    from django.template.loader import render_to_string
    from weasyprint import HTML
    active_company = get_active_company(request)
    q = request.GET.get('q', '').strip()
    ctx = {
        "q": q,
        "company_filter": active_company,
        "now": _dt.now(),
    }
    if extra_ctx:
        ctx.update(extra_ctx)
    html = render_to_string(template, ctx)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def _parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(val, default=0.0):
    try:
        if isinstance(val, str):
            val = val.replace(',', '').strip()
        return float(val) if val not in (None, '') else default
    except (ValueError, TypeError):
        return default


def pagination_props(page_obj):
    """Standard Inertia props describing a Paginator page."""
    return {
        "number": page_obj.number,
        "num_pages": page_obj.paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
        "has_other_pages": page_obj.has_other_pages(),
        "range": _page_range_display(page_obj),
        "start_index": page_obj.start_index(),
        "end_index": page_obj.end_index(),
        "count": page_obj.paginator.count,
    }


def period_label(date_from=None, date_to=None):
    """Human-readable label for an optional from/to date range."""
    if date_from and date_to:
        return f"{date_from.strftime('%d %b %Y')} — {date_to.strftime('%d %b %Y')}"
    if date_from:
        return f"Sejak {date_from.strftime('%d %b %Y')}"
    if date_to:
        return f"Sampai {date_to.strftime('%d %b %Y')}"
    return 'Semua transaksi'


def _client_options(active_company):
    """Active clients of a company as [{id, name}] options for form dropdowns."""
    from ..models import Client
    return list(
        Client.objects.filter(company=active_company, is_active=True)
        .order_by('name').values('id', 'name')
    )


def serialize_journal_entry(entry, **extra):
    """Base dict for a JournalEntry used across finance/payment/period views.

    Always includes the common 6 fields; callers pass optional extras
    (total_debit, total_credit, is_balanced, etc.) via keyword arguments.
    """
    base = {
        'id': entry.pk,
        'entry_number': entry.entry_number,
        'entry_type': entry.entry_type,
        'entry_type_display': entry.get_entry_type_display(),
        'description': entry.description,
        'entry_date': entry.entry_date.isoformat(),
    }
    if extra:
        base.update(extra)
    return base


def journal_line_dimension(line):
    """Resolve a JournalLine's FK references into a human-readable label.

    Returns the first matching dimension (client, invoice, reservation,
    service, or penalty) rather than concatenating all, matching the
    original per-line display convention.
    """
    if getattr(line, 'client_id', None):
        return line.client.name
    if getattr(line, 'invoice_id', None):
        return line.invoice.invoice_number
    if getattr(line, 'reservation_id', None):
        return line.reservation.reservation_number
    if getattr(line, 'service_item_id', None):
        return f"Service #{line.service_item_id}"
    if getattr(line, 'penalty_id', None):
        return line.penalty.penalty_number
    return ''
