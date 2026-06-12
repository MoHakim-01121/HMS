from datetime import datetime
import urllib.parse

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render

from ..models import ConfirmationLetter, Payment


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


def _paginated_list(request, qs, template, context_key, extra_ctx=None):
    q = request.GET.get('q', '').strip()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    params_str = urllib.parse.urlencode({k: v for k, v in request.GET.items() if k != 'page'})
    ctx = {
        context_key: page_obj,
        "page_obj": page_obj,
        "q": q,
        "total_count": paginator.count,
        "page_range_display": _page_range_display(page_obj),
        "params_str": params_str,
    }
    if extra_ctx:
        ctx.update(extra_ctx)
    return render(request, template, ctx)


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


def _save_payments(invoice, request, ref_field, default_currency):
    """Create Payment objects from POST data lists. Sets cl FK when ref matches a CL number."""
    refs      = request.POST.getlist(ref_field)
    dates     = request.POST.getlist("payment_date")
    methods   = request.POST.getlist("payment_method")
    amounts   = request.POST.getlist("payment_amount")
    currencies = request.POST.getlist("payment_currency")
    exchanges = request.POST.getlist("payment_exchange")
    notes     = request.POST.getlist("payment_note")

    # Pre-fetch CLs that match any of the ref numbers (one query instead of N)
    ref_set = {r.strip() for r in refs if r and r.strip()}
    cl_by_number = {
        cl.confirmation_number: cl
        for cl in ConfirmationLetter.objects.filter(confirmation_number__in=ref_set)
    } if ref_set else {}

    for i, (ref, dt, method, amount, currency, exchange, note) in enumerate(
        zip(refs, dates, methods, amounts, currencies, exchanges, notes)
    ):
        proof = request.FILES.get(f"payment_proof_{i}")
        keep  = request.POST.get(f"payment_proof_keep_{i}", "")
        ref_clean = ref.strip() if ref else ""
        p = Payment.objects.create(
            invoice=invoice,
            cl=cl_by_number.get(ref_clean),
            linked_number=ref_clean,
            payment_date=_parse_date(dt),
            method=method.strip() if method else "",
            amount=float(amount.strip()) if amount and amount.strip() else 0,
            currency=currency.upper() if currency else default_currency,
            exchange_rate=float(exchange.strip()) if exchange and exchange.strip() else 1,
            note=note.strip() if note else "",
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
