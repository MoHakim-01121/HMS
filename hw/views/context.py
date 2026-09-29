import math

from ..finance import queries as fq
from ..utils import format_currency


def _credited_by_line(invoice):
    """{('r'|'s', pk): SAR no longer billed} — active credit notes per line;
    a void invoice bills nothing, so every line counts as fully credited."""
    if invoice.is_void:
        out = {('r', r.pk): int(r.total_sar or 0) for r in invoice.reservations.all()}
        out.update({('s', s.pk): int(s.total or 0) for s in invoice.service_items.all()})
        return out
    from ..finance.credit_note_service import _credited_by_line as active
    return active(invoice)


def _build_reservation_context(invoice):

    # Kredit Piutang per reservasi dari general ledger — payment lewat jalur
    # mana pun (Finance page / form invoice) menempel dimensi reservation di
    # baris CR Piutang-nya.
    paid_by_reservation_id = fq.reservation_paid_map(invoice.id)
    credited = _credited_by_line(invoice)

    cl_by_number = {
        cl.confirmation_number: cl.pk
        for cl in invoice.confirmation_letters.all()
    }

    result = []
    for res in invoice.reservations.all():
        paid = paid_by_reservation_id.get(res.pk, 0)
        credited_int = credited.get(('r', res.pk), 0)
        remaining = res.total_sar - credited_int - paid
        if remaining == 0:
            cls = "remaining-paid"
        elif remaining > res.total_sar * 0.5:
            cls = "remaining-unpaid"
        else:
            cls = "remaining-partial"
        cl_pk = cl_by_number.get(res.reservation_number)
        result.append({
            "id": res.pk,
            "number": res.reservation_number,
            "hotel": res.hotel,
            "check_in": res.check_in,
            "check_out": res.check_out,
            "total": format_currency(res.total_sar),
            "total_int": res.total_sar,
            "paid_int": paid,
            "credited_int": credited_int,
            "remaining": format_currency(remaining),
            "remaining_int": remaining,
            "remaining_class": cls,
            "cl_pk": cl_pk,
        })
    return result


def _build_invoice_unallocated_context(invoice):
    """Info pembayaran yang diterima tapi belum dialokasikan ke reservasi.

    Dipakai invoice detail & payment record dialog supaya user tahu ada sisa
    yang mengambang (belum tentukan alokasinya) dan bisa dialokasikan nanti."""
    unallocated = fq.invoice_unallocated_sar(invoice.id)
    return {
        "unallocated_int": unallocated,
    }


def _build_visa_services_context(invoice):
    main_currency = invoice.currency
    payments_by_svc = {}
    for p in fq.payment_history_rows(invoice):
        if p['currency'] == main_currency:
            amt_main = float(p['amount'])
        else:
            exch = p['exchange_rate'] or 1
            amt_main = math.floor(float(p['amount']) / exch)
        for svc_no in p['svc_nos']:
            try:
                svc_no = int(svc_no)
            except (ValueError, TypeError):
                continue
            payments_by_svc[svc_no] = payments_by_svc.get(svc_no, 0) + amt_main

    credited = _credited_by_line(invoice)
    result = []
    for item in invoice.service_items.all():
        total = int(item.qty * float(item.price))
        paid = int(payments_by_svc.get(item.service_number, 0))
        credited_int = credited.get(('s', item.pk), 0)
        remaining = total - credited_int - paid
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
            "paid_int": paid,
            "credited_int": credited_int,
            "remaining": remaining,
            "remaining_class": cls,
        })
    return result


def _build_visa_payments_context(invoice):
    main_currency = invoice.currency
    result = []
    for p in fq.payment_history_rows(invoice):
        amt = float(p['amount'])
        exch = p['exchange_rate'] or 1
        if p['currency'] == main_currency:
            amt_main = amt
        else:
            if p['currency'] == "IDR" and main_currency == "USD":
                amt_main = math.floor(amt / exch)
            else:
                amt_main = amt / exch
        result.append({
            # The service_number(s) this payment settles -- the only reference
            # a services payment carries. _build_visa_services_context above
            # keys its per-service paid totals off the same field.
            "linked_number": p['ref'],
            "svc_nos": p['svc_nos'],
            "payment_date": p['payment_date'],
            "payment_method": p['method'],
            "payment_amount": amt,
            "payment_currency": p['currency'],
            "payment_exchange": exch,
            "payment_note": p['note'],
            "payment_amount_main": amt_main,
            "proof": p['proof'],
        })
    return result
