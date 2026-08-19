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
