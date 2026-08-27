"""Posting layer — satu-satunya cara menulis ke general ledger.

`post_entry()` adalah primitive: bikin satu JournalEntry immutable + baris-
barisnya, balance per currency, dengan seq monoton + rantai hash +
idempotency. Semua fungsi posting per-event (Fase 3) dibangun di atasnya.
"""
from django.db import models, transaction

from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..models.choices import Company
from ..finance_helpers import (
    FinanceError, JournalImbalanceError, PeriodLockedError,
    get_period_for_date, check_period_postable,
)
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
