import math

from ..finance import queries as fq
from ..utils import format_currency


def _credited_by_line(invoice):
    """{('r'|'s', pk): SAR no longer billed} — active credit notes per line;
    a void invoice bills nothing, so every line counts as fully credited."""
    from ..finance.credit_note_service import _credited_by_line as active, _line_key
    if invoice.is_void:
        return {
            _line_key(line): int(line.amount or 0)
            for line in invoice.billed_lines()
        }
    return active(invoice)


def _build_reservation_context(invoice):
    """One row per reservation billed on the invoice.

    A row covers the reservation's hotel line and, when it was cancelled with
    a penalty, its penalty line: `total` is what the reservation costs now,
    and payments recorded against the reservation cover the penalty first
    (finance.penalty_billing). A negative `remaining_int` is an overpayment.
    """
    from ..finance.penalty_billing import reservation_balances

    result = []
    for row in sorted(reservation_balances(invoice).values(), key=lambda r: r['line'].line_no):
        res, pen_line = row['line'], row['penalty_line']
        total, remaining = row['total'], row['remaining']
        if remaining == 0:
            cls = "remaining-paid"
        elif remaining > total * 0.5:
            cls = "remaining-unpaid"
        else:
            cls = "remaining-partial"
        result.append({
            "id": res.pk,
            "number": res.reservation_number,
            "hotel": res.hotel,
            "check_in": res.check_in,
            "check_out": res.check_out,
            "total": format_currency(total),
            "total_int": total,
            "paid_int": row['paid'],
            "credited_int": row['credited'],
            "remaining": format_currency(remaining),
            "remaining_int": remaining,
            "remaining_class": cls,
            # A void invoice no longer bills its reservations, so it does not link to them.
            "cl_pk": None if invoice.is_void else res.confirmation_letter_id,
            "penalty_int": row['penalty_amount'],
            "penalty_number": pen_line.penalty.penalty_number if pen_line else None,
            "penalty_pk": pen_line.penalty_id if pen_line else None,
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
    from django.db.models import Sum
    from ..models.expense import ExpenseLine
    vendor_cost = {
        row['service_line']: int(row['t'] or 0)
        for row in ExpenseLine.objects.filter(
            service_line__invoice=invoice, expense__status='posted',
        ).values('service_line').annotate(t=Sum('amount_sar'))
    }
    result = []
    for item in invoice.service_items:
        total = int(item.total)
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
            # What the branch pays its vendor for this line (SAR, posted expenses).
            "vendor_cost_sar": vendor_cost.get(item.pk, 0),
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
