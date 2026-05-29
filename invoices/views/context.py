import math

from ..utils import format_currency


def _build_reservation_context(invoice):
    payments_by_res = {}
    for p in invoice.payments.all():
        key = p.linked_number
        payments_by_res[key] = payments_by_res.get(key, 0) + p.amount_sar

    cl_by_number = {
        cl.confirmation_number: cl.pk
        for cl in invoice.confirmation_letters.all()
    }

    result = []
    for res in invoice.reservations.all():
        paid = payments_by_res.get(res.reservation_number, 0)
        remaining = res.total_sar - paid
        if remaining == 0:
            cls = "remaining-paid"
        elif remaining > res.total_sar * 0.5:
            cls = "remaining-unpaid"
        else:
            cls = "remaining-partial"
        cl_pk = cl_by_number.get(res.reservation_number)
        result.append({
            "number": res.reservation_number,
            "hotel": res.hotel,
            "check_in": res.check_in,
            "check_out": res.check_out,
            "total": format_currency(res.total_sar),
            "total_int": res.total_sar,
            "remaining": format_currency(remaining),
            "remaining_class": cls,
            "cl_pk": cl_pk,
        })
    return result


def _build_visa_services_context(invoice):
    main_currency = invoice.currency
    payments_by_svc = {}
    for p in invoice.payments.all():
        try:
            svc_no = int(p.linked_number)
        except (ValueError, TypeError):
            continue
        if p.currency == main_currency:
            amt_main = float(p.amount)
        else:
            exch = float(p.exchange_rate) or 1
            amt_main = math.floor(float(p.amount) / exch)
        payments_by_svc[svc_no] = payments_by_svc.get(svc_no, 0) + amt_main

    result = []
    for item in invoice.service_items.all():
        total = int(item.qty * float(item.price))
        paid = int(payments_by_svc.get(item.service_number, 0))
        remaining = total - paid
        if remaining == 0:
            cls = "remaining-paid"
        elif 0 < remaining < total:
            cls = "remaining-partial"
        else:
            cls = "remaining-unpaid"
        result.append({
            "service_no": item.service_number,
            "product": item.name,
            "qty": item.qty,
            "price": math.floor(float(item.price)),
            "total": total,
            "remaining": remaining,
            "remaining_class": cls,
        })
    return result


def _build_visa_payments_context(invoice):
    main_currency = invoice.currency
    result = []
    for p in invoice.payments.all():
        amt = float(p.amount)
        exch = float(p.exchange_rate) or 1
        if p.currency == main_currency:
            amt_main = amt
        else:
            if p.currency == "IDR" and main_currency == "USD":
                amt_main = math.floor(amt / exch)
            else:
                amt_main = amt / exch
        result.append({
            "payment_date": p.payment_date,
            "payment_method": p.method,
            "payment_amount": amt,
            "payment_currency": p.currency,
            "payment_exchange": exch,
            "payment_note": p.note,
            "payment_amount_main": amt_main,
            "proof": p.proof,
        })
    return result
