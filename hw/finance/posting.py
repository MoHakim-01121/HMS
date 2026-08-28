"""Posting layer — satu-satunya cara menulis ke general ledger.

`post_entry()` adalah primitive: bikin satu JournalEntry immutable + baris-
barisnya, balance per currency, dengan seq monoton + rantai hash +
idempotency. Semua fungsi posting per-event (Fase 3) dibangun di atasnya.
"""
from django.db import models, transaction
from django.utils import timezone

from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..models.choices import Company, InvoiceType
from ..finance_helpers import (
    FinanceError, JournalImbalanceError, PeriodLockedError,
    get_period_for_date, check_period_postable,
)
from . import accounts as coa
from .accounts import resolve_account_code
from .hashing import entry_hash

_DIMS = ("client", "invoice", "reservation", "service_item", "penalty", "remittance")


class MissingDimensionError(FinanceError):
    """Baris akun piutang/titipan wajib punya dimensi client."""


def _norm_line(spec, line_no):
    """LineSpec → dict siap jadi JournalLine. Terima {debit,credit} atau
    {amount_sar} (signed)."""
    if "amount_sar" in spec and "debit" not in spec and "credit" not in spec:
        amt = spec["amount_sar"]
        debit, credit = (amt, 0) if amt > 0 else (0, -amt)
    else:
        debit = int(spec.get("debit", 0) or 0)
        credit = int(spec.get("credit", 0) or 0)
    if (debit > 0) == (credit > 0):
        raise JournalImbalanceError(
            f"Baris {line_no}: tepat satu dari debit/credit harus > 0 "
            f"(debit={debit}, credit={credit})"
        )
    code = resolve_account_code(str(spec["account"]))
    row = {
        "line_no": line_no,
        "account_id": code,
        "debit": debit,
        "credit": credit,
        "currency": spec.get("currency", "SAR"),
        "orig_amount": spec.get("orig_amount"),
        "orig_currency": spec.get("orig_currency", ""),
        "fx_rate": spec.get("fx_rate"),
        "note": spec.get("note", ""),
    }
    for dim in _DIMS:
        v = spec.get(dim)
        row[f"{dim}_id"] = getattr(v, "pk", v)
    return row


def _validate_balance(rows):
    per_ccy = {}
    for r in rows:
        d, c = per_ccy.get(r["currency"], (0, 0))
        per_ccy[r["currency"]] = (d + r["debit"], c + r["credit"])
    for ccy, (d, c) in per_ccy.items():
        if d != c:
            raise JournalImbalanceError(
                f"Journal entry tidak balance ({ccy}): debit {d:,} != credit {c:,}"
            )


_AR_LIKE = None  # diisi lazily; akun yang wajib punya dimensi client


def _needs_client(account_id):
    global _AR_LIKE
    if _AR_LIKE is None:
        from .accounts import AR, CUST_CREDIT
        _AR_LIKE = {AR, CUST_CREDIT}
    return account_id in _AR_LIKE


@transaction.atomic
def post_entry(
    *,
    entry_type,
    description,
    entry_date,
    lines,
    company=Company.KONOZ,
    source_type="",
    source_id=None,
    idempotency_key=None,
    created_by=None,
    is_reversal=False,
    reverses=None,
):
    """Bikin satu JournalEntry immutable + baris-barisnya.

    lines: list LineSpec (dict). Kunci wajib: `account` (kode v2/v1),
    dan `debit`+`credit` ATAU `amount_sar` (signed). Opsional: `currency`,
    `orig_amount`/`orig_currency`/`fx_rate`, `note`, dimensi
    (client/invoice/reservation/service_item/penalty/remittance).

    Idempotent terhadap `idempotency_key`: pemanggilan ulang mengembalikan
    entry yang sudah ada, tidak dobel-posting.
    """
    if idempotency_key:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    rows = [_norm_line(spec, i) for i, spec in enumerate(lines, start=1)]
    if len(rows) < 2:
        raise JournalImbalanceError("Journal entry butuh minimal 2 baris")
    _validate_balance(rows)
    for r in rows:
        if _needs_client(r["account_id"]) and r.get("client_id") is None:
            raise MissingDimensionError(
                f"Baris {r['line_no']} ({r['account_id']}) wajib punya dimensi client"
            )

    period = get_period_for_date(entry_date)
    check_period_postable(period)

    # seq monoton per company + prev_hash dari entry terakhir
    last = (
        JournalEntry.objects.select_for_update()
        .filter(company=company, seq__isnull=False)
        .order_by("-seq").first()
    )
    seq = (last.seq if last else 0) + 1
    prev_hash = last.entry_hash if last else ""

    entry = JournalEntry(
        entry_number=JournalEntry.generate_number(),
        entry_type=entry_type,
        description=description,
        entry_date=entry_date,
        seq=seq,
        prev_hash=prev_hash,
        reference_type=source_type,
        reference_id=source_id,
        idempotency_key=idempotency_key or None,
        is_reversal=is_reversal,
        reverses=reverses,
        period=period,
        company=company,
        created_by=created_by,
    )
    entry.entry_hash = entry_hash(entry, rows, prev_hash)
    entry.save()

    JournalLine.objects.bulk_create([
        JournalLine(journal_entry=entry, **r) for r in rows
    ])

    agg = JournalLine.objects.filter(journal_entry=entry).aggregate(
        d=models.Sum("debit"), c=models.Sum("credit"),
    )
    if (agg["d"] or 0) != (agg["c"] or 0):
        raise JournalImbalanceError("Balance check gagal setelah simpan")

    return entry


@transaction.atomic
def reverse_entry(original, *, reversal_date, created_by, note=""):
    """Entry pembalik: tukar debit↔credit tiap baris, tautkan via `reverses`."""
    if original.is_reversal:
        raise FinanceError("Tidak bisa me-reverse entry yang sudah reversal")
    if JournalEntry.objects.filter(reverses=original).exists():
        raise FinanceError(f"{original.entry_number} sudah pernah di-reverse")

    lines = []
    for ln in original.lines.all():
        spec = {
            "account": ln.account_id,
            "debit": ln.credit,
            "credit": ln.debit,
            "currency": ln.currency,
            "note": note or f"Reversal of {original.entry_number}",
        }
        for dim in _DIMS:
            spec[dim] = getattr(ln, f"{dim}_id", None)
        lines.append(spec)

    return post_entry(
        entry_type=JournalEntry.TYPE_REVERSAL,
        description=f"Reversal: {original.description}",
        entry_date=reversal_date,
        lines=lines,
        company=original.company,
        source_type="JournalEntry",
        source_id=original.pk,
        created_by=created_by,
        is_reversal=True,
        reverses=original,
    )


# ── Helpers ────────────────────────────────────────────────────

def _live_entries(source_type, source_id, entry_type):
    """Entry non-reversal untuk sumber ini yang BELUM di-reverse."""
    reversed_ids = JournalEntry.objects.filter(
        reverses__isnull=False,
    ).values_list("reverses_id", flat=True)
    return list(
        JournalEntry.objects.filter(
            reference_type=source_type, reference_id=source_id,
            entry_type=entry_type, is_reversal=False,
        ).exclude(pk__in=reversed_ids)
    )


def _ar_debit_total(entries):
    if not entries:
        return 0
    agg = JournalLine.objects.filter(
        journal_entry__in=entries, account_id=coa.AR,
    ).aggregate(d=models.Sum("debit"))
    return agg["d"] or 0


# ── Charge-side (Fase 3 Group A) ───────────────────────────────

def _invoice_charge_lines(invoice):
    income = coa.INC_HOTEL if invoice.invoice_type == InvoiceType.HOTEL else coa.INC_SERVICE
    client_id = invoice.client_id
    lines = []
    for r in invoice.reservations.all():
        amt = int(r.total_sar or 0)
        if not amt:
            continue
        lines.append({"account": coa.AR, "debit": amt, "client": client_id,
                      "invoice": invoice.pk, "reservation": r.pk})
        lines.append({"account": income, "credit": amt,
                      "invoice": invoice.pk, "reservation": r.pk})
    for s in invoice.service_items.all():
        amt = int(s.total or 0)
        if not amt:
            continue
        lines.append({"account": coa.AR, "debit": amt, "client": client_id,
                      "invoice": invoice.pk, "service_item": s.pk})
        lines.append({"account": income, "credit": amt,
                      "invoice": invoice.pk, "service_item": s.pk})
    return lines


@transaction.atomic
def post_invoice_charge(invoice, *, created_by, entry_date=None):
    """DR Piutang / CR Pendapatan per reservation/service_item.

    Idempotent-by-content: kalau charge invoice ini sudah terposting dengan
    total yang sama → no-op; kalau total berubah (revisi) → reversal charge
    lama lalu post ulang; kalau invoice tak punya baris → None.
    """
    entry_date = entry_date or invoice.issued_date or timezone.now().date()
    lines = _invoice_charge_lines(invoice)
    expected = sum(l["debit"] for l in lines if l["account"] == coa.AR)

    live = _live_entries("Invoice", invoice.pk, JournalEntry.TYPE_CHARGE)
    if live and _ar_debit_total(live) == expected:
        return live[-1]
    for e in live:
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)
    if not lines:
        return None
    return post_entry(
        entry_type=JournalEntry.TYPE_CHARGE,
        description=f"Charge {invoice.invoice_number}",
        entry_date=entry_date,
        lines=lines,
        company=invoice.company,
        source_type="Invoice",
        source_id=invoice.pk,
        created_by=created_by,
    )


@transaction.atomic
def void_invoice_charge(invoice, *, created_by, entry_date=None):
    """Reverse semua charge entry invoice yang masih hidup (invoice void)."""
    entry_date = entry_date or timezone.now().date()
    for e in _live_entries("Invoice", invoice.pk, JournalEntry.TYPE_CHARGE):
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)


def _penalty_client_id(penalty):
    return penalty.client_id or (penalty.cl.client_id if penalty.cl_id else None)


def _penalty_amount(penalty):
    return int(penalty.amount_sar or penalty.penalty_amount_sar or 0)


@transaction.atomic
def post_penalty_charge(penalty, *, created_by, entry_date=None):
    """DR Piutang / CR Pendapatan Penalty."""
    amt = _penalty_amount(penalty)
    if not amt:
        return None
    entry_date = entry_date or penalty.cancellation_date or timezone.now().date()
    key = f"penalty:{penalty.penalty_number}:charge"
    return post_entry(
        entry_type=JournalEntry.TYPE_PENALTY,
        description=f"Penalty {penalty.penalty_number}",
        entry_date=entry_date,
        lines=[
            {"account": coa.AR, "debit": amt, "client": _penalty_client_id(penalty),
             "penalty": penalty.pk, "invoice": penalty.invoice_id},
            {"account": coa.INC_PENALTY, "credit": amt,
             "penalty": penalty.pk, "invoice": penalty.invoice_id},
        ],
        company=penalty.cl.company if penalty.cl_id else Company.KONOZ,
        source_type="CancellationPenalty",
        source_id=penalty.pk,
        idempotency_key=key,
        created_by=created_by,
    )


# ── Payment-side (Fase 3 Group B) ──────────────────────────────

_CASH_BY_LOCATION = {"sby": coa.CASH_SBY, "jkt": coa.CASH_JKT, "pusat": coa.CASH_PUSAT}


def _payment_dims(payment):
    dims = {"client": payment.client_id, "invoice": payment.invoice_id}
    if payment.reservation_id:
        dims["reservation"] = payment.reservation_id
    if payment.service_item_id:
        dims["service_item"] = payment.service_item_id
    return dims


@transaction.atomic
def post_payment(payment, *, created_by):
    """DR Kas (sesuai received_in) / CR Piutang. Idempotent per payment."""
    cash_acc = _CASH_BY_LOCATION.get(payment.received_in, coa.CASH_SBY)
    amt = int(payment.amount_sar)
    dims = _payment_dims(payment)
    return post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} — {payment.client}",
        entry_date=payment.payment_date,
        lines=[
            {"account": cash_acc, "debit": amt, **dims},
            {"account": coa.AR, "credit": amt, **dims},
        ],
        company=payment.company,
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=f"payment:{payment.payment_number}:confirm",
        created_by=created_by,
    )


def client_credit_balance(client_id):
    agg = JournalLine.objects.filter(
        client_id=client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=models.Sum("debit"), c=models.Sum("credit"))
    return (agg["c"] or 0) - (agg["d"] or 0)


class InsufficientCreditError(FinanceError):
    """Saldo titipan client tidak cukup."""


@transaction.atomic
def post_payment_from_credit(payment, *, created_by):
    """Bayar invoice pakai saldo titipan: DR Titipan / CR Piutang."""
    amt = int(payment.amount_sar)
    if client_credit_balance(payment.client_id) < amt:
        raise InsufficientCreditError(
            f"Saldo titipan {payment.client} tidak cukup untuk {amt:,}"
        )
    dims = _payment_dims(payment)
    return post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} (titipan) — {payment.client}",
        entry_date=payment.payment_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": amt, **dims},
            {"account": coa.AR, "credit": amt, **dims},
        ],
        company=payment.company,
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=f"payment:{payment.payment_number}:from-credit",
        created_by=created_by,
    )


@transaction.atomic
def post_penalty_payment(penalty, *, created_by, received_in="sby", entry_date=None):
    """DR Kas / CR Piutang untuk pelunasan penalty."""
    amt = _penalty_amount(penalty)
    if not amt:
        return None
    cash_acc = _CASH_BY_LOCATION.get(received_in, coa.CASH_SBY)
    entry_date = entry_date or getattr(penalty, "payment_date", None) or timezone.now().date()
    dims = {"client": _penalty_client_id(penalty), "penalty": penalty.pk,
            "invoice": penalty.invoice_id}
    return post_entry(
        entry_type=JournalEntry.TYPE_PENALTY,
        description=f"Pembayaran penalty {penalty.penalty_number}",
        entry_date=entry_date,
        lines=[
            {"account": cash_acc, "debit": amt, **dims},
            {"account": coa.AR, "credit": amt, **dims},
        ],
        company=penalty.cl.company if penalty.cl_id else Company.KONOZ,
        source_type="CancellationPenalty",
        source_id=penalty.pk,
        idempotency_key=f"penalty:{penalty.penalty_number}:pay",
        created_by=created_by,
    )


# ── Kas movement (Fase 3 Group C) ──────────────────────────────

@transaction.atomic
def post_remittance_send(remittance, *, from_location, amount_sar, created_by, entry_date=None):
    """Uang keluar dari kas cabang → Kas Dalam Perjalanan."""
    src = _CASH_BY_LOCATION.get(from_location, coa.CASH_SBY)
    entry_date = entry_date or remittance.date or timezone.now().date()
    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Remittance {remittance.remittance_number} kirim",
        entry_date=entry_date,
        lines=[
            {"account": coa.TRANSIT, "debit": amount_sar, "remittance": remittance.pk},
            {"account": src, "credit": amount_sar, "remittance": remittance.pk},
        ],
        company=remittance.company,
        source_type="Remittance",
        source_id=remittance.pk,
        idempotency_key=f"rmt:{remittance.remittance_number}:send",
        created_by=created_by,
    )


@transaction.atomic
def post_remittance_receive(remittance, *, expected_sar, received_sar, created_by, entry_date=None):
    """Kas Pusat terima; selisih expected vs received → beban bank."""
    entry_date = entry_date or remittance.date or timezone.now().date()
    lines = [
        {"account": coa.CASH_PUSAT, "debit": received_sar, "remittance": remittance.pk},
        {"account": coa.TRANSIT, "credit": expected_sar, "remittance": remittance.pk},
    ]
    diff = expected_sar - received_sar
    if diff > 0:
        lines.append({"account": coa.EXP_BANKFEE, "debit": diff, "remittance": remittance.pk})
    elif diff < 0:
        lines.append({"account": coa.INC_FX_GAIN, "credit": -diff, "remittance": remittance.pk})
    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Remittance {remittance.remittance_number} diterima",
        entry_date=entry_date,
        lines=lines,
        company=remittance.company,
        source_type="Remittance",
        source_id=remittance.pk,
        idempotency_key=f"rmt:{remittance.remittance_number}:receive",
        created_by=created_by,
    )


@transaction.atomic
def post_refund(client, *, from_location, amount_sar, created_by, entry_date,
                use_credit=True, company=Company.KONOZ):
    """Refund ke client: DR Titipan (atau Piutang) / CR Kas."""
    src = _CASH_BY_LOCATION.get(from_location, coa.CASH_PUSAT)
    debit_acc = coa.CUST_CREDIT if use_credit else coa.AR
    return post_entry(
        entry_type=JournalEntry.TYPE_REFUND,
        description=f"Refund ke {client}",
        entry_date=entry_date,
        lines=[
            {"account": debit_acc, "debit": amount_sar, "client": client.pk},
            {"account": src, "credit": amount_sar, "client": client.pk},
        ],
        company=company,
        source_type="Client",
        source_id=client.pk,
        created_by=created_by,
    )


@transaction.atomic
def post_fund_transfer(client, *, from_reservation, to_reservation, amount_sar,
                       created_by, entry_date, company=Company.KONOZ):
    """Pindah piutang antar reservasi (re-tag), total piutang klien tetap."""
    return post_entry(
        entry_type=JournalEntry.TYPE_TRANSFER,
        description=f"Transfer dana {from_reservation} → {to_reservation}",
        entry_date=entry_date,
        lines=[
            {"account": coa.AR, "debit": amount_sar, "client": client.pk,
             "reservation": getattr(to_reservation, "pk", to_reservation)},
            {"account": coa.AR, "credit": amount_sar, "client": client.pk,
             "reservation": getattr(from_reservation, "pk", from_reservation)},
        ],
        company=company,
        created_by=created_by,
    )


@transaction.atomic
def allocate_payment(payment, allocations, *, created_by=None):
    """Tulis PaymentAllocation (analitik) — TANPA journal entry.

    allocations: iterable (target, amount_sar) di mana target adalah
    instance Reservation / ServiceItem / CancellationPenalty.
    """
    from ..models import CancellationPenalty, Reservation, ServiceItem
    from ..models.payment import PaymentAllocation

    allocations = list(allocations)
    total = sum(int(a) for _, a in allocations)
    if total > int(payment.amount_sar):
        raise FinanceError(
            f"Alokasi {total:,} melebihi pembayaran {payment.amount_sar:,}"
        )
    rows = []
    for target, amt in allocations:
        kw = {"reservation": None, "service_item": None, "penalty": None}
        if isinstance(target, Reservation):
            kw["reservation"] = target
        elif isinstance(target, ServiceItem):
            kw["service_item"] = target
        elif isinstance(target, CancellationPenalty):
            kw["penalty"] = target
        else:
            raise FinanceError(f"Target alokasi tidak dikenali: {target!r}")
        rows.append(PaymentAllocation(payment=payment, amount_sar=int(amt), **kw))
    PaymentAllocation.objects.bulk_create(rows)
    return rows


@transaction.atomic
def post_adjustment(*, lines, description, entry_date, created_by,
                    company=Company.KONOZ, idempotency_key=None):
    """Entry adjustment manual bebas — wajib balance + deskripsi."""
    if not description:
        raise FinanceError("Adjustment wajib punya deskripsi")
    return post_entry(
        entry_type=JournalEntry.TYPE_ADJUSTMENT,
        description=description,
        entry_date=entry_date,
        lines=lines,
        company=company,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
