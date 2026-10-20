
from ..utils import format_currency


def _credited_by_line(invoice):
    """{('r'|'p', pk): SAR no longer billed} — active credit notes per line;
    a void invoice bills nothing, so every line counts as fully credited."""
    from ..finance.credit_note_service import _credited_by_line as active, _line_key
    if invoice.is_void:
        return {
            _line_key(line): int(line.amount or 0)
            for line in invoice.billed_lines()
        }
    return active(invoice)


def _build_reservation_context(invoice, *, credited=None, paid_map=None):
    """One row per reservation billed on the invoice.

    A row covers the reservation's hotel line and, when it was cancelled with
    a penalty, its penalty line: `total` is what the reservation costs now,
    and payments recorded against the reservation cover the penalty first
    (finance.penalty_billing). A negative `remaining_int` is an overpayment.
    """
    from ..finance.penalty_billing import reservation_balances

    result = []
    balances = reservation_balances(invoice, credited=credited, paid_map=paid_map)
    for row in sorted(balances.values(), key=lambda r: r['line'].line_no):
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
