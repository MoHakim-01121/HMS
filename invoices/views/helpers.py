from datetime import datetime

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render


def _paginated_list(request, qs, template, context_key, extra_ctx=None):
    q = request.GET.get('q', '').strip()
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    ctx = {
        context_key: page_obj,
        "page_obj": page_obj,
        "q": q,
        "total_count": qs.count(),
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


def _save_hotel_payments(invoice, request):
    from ..models import Payment
    payment_reservation_nos = request.POST.getlist("payment_reservation_no")
    payment_dates = request.POST.getlist("payment_date")
    payment_methods = request.POST.getlist("payment_method")
    payment_amounts = request.POST.getlist("payment_amount")
    payment_currencies = request.POST.getlist("payment_currency")
    payment_exchanges = request.POST.getlist("payment_exchange")
    payment_notes = request.POST.getlist("payment_note")

    for i, (res_no, dt, method, amount, currency, exchange, note) in enumerate(zip(
        payment_reservation_nos, payment_dates, payment_methods,
        payment_amounts, payment_currencies, payment_exchanges, payment_notes
    )):
        proof = request.FILES.get(f"payment_proof_{i}")
        keep = request.POST.get(f"payment_proof_keep_{i}", "")
        p = Payment.objects.create(
            invoice=invoice,
            linked_number=res_no.strip() if res_no else "",
            payment_date=_parse_date(dt),
            method=method.strip() if method else "",
            amount=float(amount.strip()) if amount and amount.strip() else 0,
            currency=currency.upper() if currency else "SAR",
            exchange_rate=float(exchange.strip()) if exchange and exchange.strip() else 1,
            note=note.strip() if note else "",
        )
        if proof:
            p.proof = proof
            p.save()
        elif keep:
            p.proof = keep
            p.save()


def _save_service_payments(invoice, request):
    from ..models import Payment
    service_nos = request.POST.getlist("payment_service_no")
    payment_dates = request.POST.getlist("payment_date")
    payment_methods = request.POST.getlist("payment_method")
    payment_amounts = request.POST.getlist("payment_amount")
    payment_currencies = request.POST.getlist("payment_currency")
    payment_exchanges = request.POST.getlist("payment_exchange")
    payment_notes = request.POST.getlist("payment_note")

    for i, (svc_no, dt, method, amount, currency, exchange, note) in enumerate(zip(
        service_nos, payment_dates, payment_methods,
        payment_amounts, payment_currencies, payment_exchanges, payment_notes
    )):
        proof = request.FILES.get(f"payment_proof_{i}")
        keep = request.POST.get(f"payment_proof_keep_{i}", "")
        p = Payment.objects.create(
            invoice=invoice,
            linked_number=str(svc_no).strip() if svc_no else "",
            payment_date=_parse_date(dt),
            method=method.strip() if method else "",
            amount=float(amount.strip()) if amount and amount.strip() else 0,
            currency=currency.upper() if currency else invoice.currency,
            exchange_rate=float(exchange.strip()) if exchange and exchange.strip() else 1,
            note=note.strip() if note else "",
        )
        if proof:
            p.proof = proof
            p.save()
        elif keep:
            p.proof = keep
            p.save()
