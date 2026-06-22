from datetime import datetime
import json

from django.http import HttpResponse

from ..models import ConfirmationLetter, Payment


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
    active_company = request.session.get("active_company")
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


def _save_payments(invoice, request, ref_field, default_currency):
    """Create Payment objects from a JSON `payments` array (one object per row).

    Each row: {ref, date, method, amount, currency, exchange, note, proof_keep}.
    New proof uploads arrive as multipart files keyed `payment_proof_<index>`,
    where <index> is the row's position in the array. Sets cl FK when ref
    matches a CL number.
    """
    try:
        rows = json.loads(request.POST.get('payments', '[]'))
    except (ValueError, TypeError):
        rows = []

    # Pre-fetch CLs that match any of the ref numbers (one query instead of N)
    ref_set = {(r.get('ref') or '').strip() for r in rows if (r.get('ref') or '').strip()}
    cl_by_number = {
        cl.confirmation_number: cl
        for cl in ConfirmationLetter.objects.filter(confirmation_number__in=ref_set)
    } if ref_set else {}

    for i, r in enumerate(rows):
        proof = request.FILES.get(f"payment_proof_{i}")
        keep  = (r.get('proof_keep') or '').strip()
        ref_clean = (r.get('ref') or '').strip()
        currency = (r.get('currency') or default_currency)
        p = Payment.objects.create(
            invoice=invoice,
            cl=cl_by_number.get(ref_clean),
            linked_number=ref_clean,
            payment_date=_parse_date(r.get('date')),
            method=(r.get('method') or '').strip(),
            amount=_to_float(r.get('amount')),
            currency=currency.upper() if currency else default_currency,
            exchange_rate=_to_float(r.get('exchange'), 1) or 1,
            note=(r.get('note') or '').strip(),
        )
        if proof:
            p.proof = proof
            p.save()
        elif keep:
            p.proof = keep
            p.save()


def _save_hotel_payments(invoice, request):
    _save_payments(invoice, request, 'payment_reservation_no', 'SAR')


def _save_service_payments(invoice, request):
    _save_payments(invoice, request, 'payment_service_no', invoice.currency)
