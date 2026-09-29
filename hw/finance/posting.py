"""Posting layer — satu-satunya cara menulis ke general ledger.

`post_entry()` adalah primitive: bikin satu JournalEntry immutable + baris-
barisnya, balance per currency, dengan seq monoton + rantai hash +
idempotency. Semua fungsi posting per-event (Fase 3) dibangun di atasnya.
"""
import logging

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from ..models.journal import JournalEntry, JournalLine
from ..models.payment import PaymentRecord, PaymentLog
from ..models.period import FinancialPeriod
from ..models.choices import InvoiceType
from .errors import (
    FinanceError, JournalImbalanceError, PeriodLockedError,
)
from . import accounts as coa
from .accounts import resolve_account_code
from .hashing import entry_hash

logger = logging.getLogger(__name__)

_DIMS = ("branch", "client", "invoice", "reservation", "service_item", "penalty", "remittance")


class MissingDimensionError(FinanceError):
    """Baris akun piutang/titipan wajib punya dimensi client."""


# ── Period helpers ─────────────────────────────────────────────

def get_current_period():
    """Return the current open period (with row lock). Raises PeriodLockedError if none open."""
    now = timezone.now().date()
    period = FinancialPeriod.objects.select_for_update().filter(
        date_from__lte=now,
        date_to__gte=now,
        status=FinancialPeriod.STATUS_OPEN,
    ).first()
    if not period:
        raise PeriodLockedError("Tidak ada periode terbuka untuk tanggal saat ini")
    return period


def get_period_for_date(date):
    """Return the period that contains the given date (with row lock)."""
    period = FinancialPeriod.objects.select_for_update().filter(
        date_from__lte=date,
        date_to__gte=date,
    ).first()
    if not period:
        raise PeriodLockedError(f"Tidak ada periode untuk tanggal {date}")
    return period


def check_period_postable(period):
    """Verify period allows posting.  Period is already locked by callers
    (get_period_for_date / get_current_period), so the status check is
    stable within the same transaction."""
    if not period.is_postable:
        raise PeriodLockedError(
            f"Periode {period.name} sudah {period.get_status_display()}, "
            "tidak bisa posting journal entry"
        )


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
    source_type="",
    source_id=None,
    idempotency_key=None,
    created_by=None,
    is_reversal=False,
    reverses=None,
    proof=None,
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
        existing = (
            JournalEntry.objects
            .filter(idempotency_key=idempotency_key, is_reversal=False)
            .exclude(
                pk__in=JournalEntry.objects.filter(
                    reverses__isnull=False,
                ).values_list("reverses_id", flat=True),
            )
            .first()
        )
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

    # seq monoton global + prev_hash dari entry terakhir.
    # select_for_update() memastikan dua transaksi paralel tidak menghasilkan
    # seq yang sama. Untuk tabel kosong (entry pertama), kita menggunakan
    # 0 + 1 = 1. IntegrityError (seq) ditangkap sebagai fallback
    # untuk race condition extremely-narrow-window.
    last = (
        JournalEntry.objects.select_for_update()
        .filter(seq__isnull=False)
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
        created_by=created_by,
        proof=proof,
    )
    entry.entry_hash = entry_hash(entry, rows, prev_hash)

    try:
        entry.save()
    except IntegrityError as exc:
        if 'journal_entry_seq' in str(exc) or 'unique' in str(exc).lower():
            logger.warning("post_entry seq race detected, retrying")
            return post_entry(
                entry_type=entry_type, description=description,
                entry_date=entry_date, lines=lines,
                source_type=source_type, source_id=source_id,
                idempotency_key=idempotency_key, created_by=created_by,
                is_reversal=is_reversal, reverses=reverses, proof=proof,
            )
        raise

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
    """Entry pembalik: tukar debit↔credit tiap baris, tautkan via `reverses`.

    `original` di-lock (select_for_update) supaya dua reversal paralel tidak
    bisa dobel-reverse entry yang sama. Meneruskan FX/currency-origin fields
    supaya jejak audit multi-currency tetap utuh.
    """
    # Lock the original row for the duration of this transaction so two
    # concurrent reversals cannot both pass the "already reversed" guard below.
    from ..models.journal import JournalEntry as _JE
    try:
        original = _JE.objects.select_for_update().get(pk=original.pk)
    except _JE.DoesNotExist:
        raise FinanceError(f"Entry {getattr(original, 'entry_number', original.pk)} tidak ditemukan") from None

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
            "orig_amount": ln.orig_amount,
            "orig_currency": ln.orig_currency,
            "fx_rate": ln.fx_rate,
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
        br = r.owner_branch_id
        lines.append({"account": coa.AR, "debit": amt, "client": client_id,
                      "invoice": invoice.pk, "reservation": r.pk, "branch": br})
        # Receivable stays with the owning branch; hotel revenue is HQ's.
        lines.append({"account": income, "credit": amt,
                      "invoice": invoice.pk, "reservation": r.pk,
                      "branch": coa.HQ_BRANCH if income == coa.INC_HOTEL else br})
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
    if invoice.status == invoice.STATUS_VOID:
        return None  # a void invoice bills nothing; its charge was reversed
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
        source_type="Invoice",
        source_id=invoice.pk,
        created_by=created_by,
    )


@transaction.atomic
def clear_payment_allocations(payment):
    """Drop a dead payment's analytic allocations. Returns what was removed.

    Allocations are analytic rows, not accounting (see PaymentAllocation). Once
    a payment is rejected, voided or reversed its money is gone, but surviving
    rows still report allocated_sar and make invoice_views._reservation_has_money
    refuse to delete those reservations. Callers log the returned rows in the
    PaymentLog they write, so no audit trail is lost.
    """
    rows = [
        {
            "reservation_id": a.reservation_id,
            "service_item_id": a.service_item_id,
            "penalty_id": a.penalty_id,
            "amount_sar": a.amount_sar,
        }
        for a in payment.allocations.all()
    ]
    if rows:
        payment.allocations.all().delete()
    return rows


@transaction.atomic
def reverse_invoice_payments(invoice, *, created_by, entry_date=None):
    """Reverse journal entry payment dari PaymentRecord ber-reference
    'invoice-form' milik invoice ini, DAN tandai PaymentRecord-nya REVERSED.

    Form invoice full delete-recreate daftar pembayaran; PaymentRecord
    append-only jadi baris lama tak dihapus — kalau statusnya tidak di-flip,
    baris pembayaran basi ikut tampil di riwayat & bikin
    Σ PaymentRecord ≠ paid_sar jurnal."""
    entry_date = entry_date or timezone.now().date()
    old_prs = list(
        invoice.payment_records.filter(
            reference="invoice-form",
            status__in=PaymentRecord.EFFECTIVE_STATUSES,
        )
    )
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)
    for e in JournalEntry.objects.filter(
        reference_type="PaymentRecord", reference_id__in=[p.pk for p in old_prs],
        entry_type=JournalEntry.TYPE_PAYMENT, is_reversal=False,
    ).exclude(pk__in=reversed_ids):
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)

    from .bank_ledger import void_bank_transactions
    for pr in old_prs:
        pr.status = PaymentRecord.STATUS_REVERSED
        pr.save(update_fields=["status"])
        void_bank_transactions("PaymentRecord", pr.pk)
        dropped = clear_payment_allocations(pr)
        PaymentLog.objects.create(
            payment=pr,
            action=PaymentLog.ACTION_REVERSED,
            before_state={"status": PaymentRecord.STATUS_ALLOCATED, "allocations": dropped},
            after_state={"status": PaymentRecord.STATUS_REVERSED},
            performed_by=created_by,
            note="Superseded by invoice-form payment re-sync",
        )


@transaction.atomic
def void_invoice_charge(invoice, *, created_by, entry_date=None):
    """Reverse semua charge entry invoice yang masih hidup (invoice void)."""
    entry_date = entry_date or timezone.now().date()
    for e in _live_entries("Invoice", invoice.pk, JournalEntry.TYPE_CHARGE):
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)


def _penalty_client_id(penalty):
    return penalty.cl.client_id if penalty.cl_id else None


def _penalty_amount(penalty):
    return int(penalty.amount_sar or penalty.penalty_amount_sar or 0)


@transaction.atomic
def post_penalty_charge(penalty, *, created_by, entry_date=None):
    """DR Piutang / CR Pendapatan Penalty."""
    amt = _penalty_amount(penalty)
    if not amt:
        return None
    entry_date = entry_date or penalty.cancellation_date or timezone.now().date()
    return post_entry(
        entry_type=JournalEntry.TYPE_PENALTY,
        description=f"Penalty {penalty.penalty_number}",
        entry_date=entry_date,
        lines=[
            {"account": coa.AR, "debit": amt, "client": _penalty_client_id(penalty),
             "penalty": penalty.pk},
            {"account": coa.INC_PENALTY, "credit": amt, "penalty": penalty.pk},
        ],
        source_type="CancellationPenalty",
        source_id=penalty.pk,
        created_by=created_by,
    )


@transaction.atomic
def resync_penalty(penalty, *, created_by):
    """Full resync jurnal penalty: reverse semua entry penalty yang hidup,
    lalu repost charge (+ payment kalau is_paid). Idempotent-by-content."""
    entry_date = penalty.cancellation_date or timezone.now().date()
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)
    for e in JournalEntry.objects.filter(
        reference_type="CancellationPenalty", reference_id=penalty.pk,
        entry_type=JournalEntry.TYPE_PENALTY, is_reversal=False,
    ).exclude(pk__in=reversed_ids):
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)

    if not _penalty_amount(penalty) or not _penalty_client_id(penalty):
        return
    post_penalty_charge(penalty, created_by=created_by)
    if penalty.is_paid:
        received_in = "pusat" if (penalty.payment_method or "").lower() == "direct" else "sby"
        post_penalty_payment(penalty, created_by=created_by, received_in=received_in)


# ── Payment-side (Fase 3 Group B) ──────────────────────────────

_CASH_BY_LOCATION = {"sby": coa.CASH_SBY, "jkt": coa.CASH_JKT, "pusat": coa.CASH_PUSAT}
_LOCATION_BY_CASH = {v: k for k, v in _CASH_BY_LOCATION.items()}


def _pk(v):
    return getattr(v, "pk", v)


def _payment_dims(payment):
    dims = {"client": payment.client_id, "invoice": payment.invoice_id}
    if payment.reservation_id:
        dims["reservation"] = payment.reservation_id
    if payment.service_item_id:
        dims["service_item"] = payment.service_item_id
    return dims


def _payment_targets(payment):
    """Daftar identitas yang dibayar oleh payment ini, untuk deskripsi jurnal.

    Sumbernya dua: field langsung (payment.reservation / service_item) dan
    PaymentAllocation (satu payment bisa menutup beberapa reservasi/service).
    Nomor reservasi dipakai karena identitas stabil + konsisten dengan
    deskripsi jurnal lain (Charge/Remittance pakai nomor, bukan nama).
    """
    refs = []
    seen = set()

    def _add(spec):
        if spec is None or spec in seen:
            return
        seen.add(spec)
        refs.append(spec)

    if payment.reservation_id and payment.reservation:
        _add(payment.reservation.reservation_number)
    if payment.service_item_id and payment.service_item:
        _add(f"SVC#{payment.service_item.service_number}")

    if payment.pk:
        for pa in payment.allocations.all():
            if pa.reservation_id and pa.reservation:
                _add(pa.reservation.reservation_number)
            elif pa.service_item_id and pa.service_item:
                _add(f"SVC#{pa.service_item.service_number}")

    return refs


@transaction.atomic
def post_payment(payment, *, created_by, idempotency_key=None):
    """DR Kas (sesuai received_in) / CR Piutang. Idempotent per payment.

    Kalau payment punya PaymentAllocation → CR Piutang dipecah per alokasi
    (dimensi reservation/service_item) supaya piutang & mengendap per-
    reservasi akurat; sisa yang belum dialokasikan jadi satu baris CR
    Piutang bertingkat client/invoice saja.

    `idempotency_key` (opsional) meng-override key default. Dipakai realokasi,
    di mana jurnal lama sudah di-reverse (key default sudah terpakai & unik).
    """
    if idempotency_key is None:
        default_key = f"payment:{payment.payment_number}:confirm"
        existing = JournalEntry.objects.filter(idempotency_key=default_key).first()
        if existing is not None:
            reversed_ids = JournalEntry.objects.filter(
                reverses__isnull=False,
            ).values_list("reverses_id", flat=True)
            if existing.pk in reversed_ids:
                # Entry lama sudah di-reverse: idempotency key default tetap
                # tertombstone (reversal melepas baris, bukan unique key-nya).
                # Re-post (mis. re-confirm setelah reverse) butuh key baru agar
                # tidak menabrak UNIQUE constraint.
                n = 2
                while JournalEntry.objects.filter(
                    idempotency_key=f"{default_key}#{n}",
                ).exists():
                    n += 1
                idempotency_key = f"{default_key}#{n}"

    # Akun kas: kalau ada receiving_account konkret pakai ledger-nya, kalau
    # tidak fallback ke peta received_in lama.
    acc = payment.receiving_account
    cash_acc = acc.ledger_account_id if acc else _CASH_BY_LOCATION.get(payment.received_in, coa.CASH_SBY)
    amt = int(payment.amount_sar)
    base = {"client": payment.client_id, "invoice": payment.invoice_id,
            "branch": payment.receiving_branch_code}

    # Segmen (nominal, dimensi target) — dari PaymentAllocation kalau ada,
    # kalau tidak dari payment.reservation/service_item, kalau tidak satu
    # segmen polos. Tiap segmen = DR Kas + CR Piutang berpasangan.
    segments = []
    allocs = list(payment.allocations.all()) if payment.pk else []
    if allocs:
        used = 0
        for pa in allocs:
            dim = ({"reservation": pa.reservation_id} if pa.reservation_id
                   else {"service_item": pa.service_item_id} if pa.service_item_id
                   else {"penalty": pa.penalty_id} if pa.penalty_id else {})
            segments.append((int(pa.amount_sar), dim))
            used += int(pa.amount_sar)
        if used < amt:
            segments.append((amt - used, {}))
    else:
        dim = ({"reservation": payment.reservation_id} if payment.reservation_id
               else {"service_item": payment.service_item_id} if payment.service_item_id else {})
        segments.append((amt, dim))

    lines = []
    for seg_amt, dim in segments:
        lines.append({"account": cash_acc, "debit": seg_amt, **base, **dim})
        lines.append({"account": coa.AR, "credit": seg_amt, **base, **dim})

    entry = post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} - {', '.join(_payment_targets(payment)) or 'unallocated'}",
        entry_date=payment.payment_date,
        lines=lines,
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=idempotency_key or f"payment:{payment.payment_number}:confirm",
        created_by=created_by,
    )
    # Traceable movement log (v2.0 §25-28) — no-op for legacy payments with no
    # concrete receiving_account (received_in-only rows).
    from .bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=acc, direction="in", amount_sar=amt,
        source_type="PaymentRecord", source_id=payment.pk,
        transaction_date=payment.payment_date, currency=payment.currency,
        amount=payment.amount, reference=payment.reference,
    )
    return entry


def client_credit_balance(client_id):
    agg = JournalLine.objects.filter(
        client_id=client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=models.Sum("debit"), c=models.Sum("credit"))
    return (agg["c"] or 0) - (agg["d"] or 0)


class InsufficientCreditError(FinanceError):
    """Saldo titipan client tidak cukup."""


@transaction.atomic
def post_payment_from_credit(payment, *, created_by):
    """Bayar invoice pakai saldo titipan: DR Titipan / CR Piutang.

    Mengunci baris titipan terkait (via client_credit_balance dengan select_
    for_update) supaya dua pembayaran dari-titipan paralel tidak double-spend
    saldo yang sama (lost update).
    """
    amt = int(payment.amount_sar)
    if not amt:
        raise FinanceError("Jumlah pembayaran harus > 0")
    # Lock the client's titipan rows inside the transaction so two concurrent
    # from-credit payments serialize on the current balance.
    JournalLine.objects.select_for_update().filter(
        client_id=payment.client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=models.Sum("debit"), c=models.Sum("credit"))
    balance = client_credit_balance(payment.client_id)
    if balance < amt:
        raise InsufficientCreditError(
            f"Saldo titipan {payment.client} tidak cukup untuk {amt:,}"
        )
    dims = _payment_dims(payment)
    return post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} (titipan) - {', '.join(_payment_targets(payment)) or 'unallocated'}",
        entry_date=payment.payment_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": amt, **dims},
            {"account": coa.AR, "credit": amt, **dims},
        ],
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=f"payment:{payment.payment_number}:from-credit",
        created_by=created_by,
    )


@transaction.atomic
def post_penalty_payment(penalty, *, created_by, received_in="sby", entry_date=None):
    """DR Kas / CR Piutang untuk pelunasan penalty."""
    from .bank_ledger import ensure_hq_receives_sar
    ensure_hq_receives_sar(received_in, getattr(penalty, "penalty_currency", "SAR") or "SAR")
    amt = _penalty_amount(penalty)
    if not amt:
        return None
    cash_acc = _CASH_BY_LOCATION.get(received_in, coa.CASH_SBY)
    entry_date = entry_date or getattr(penalty, "payment_date", None) or timezone.now().date()
    dims = {"client": _penalty_client_id(penalty), "penalty": penalty.pk, "branch": received_in}
    return post_entry(
        entry_type=JournalEntry.TYPE_PENALTY,
        description=f"Pembayaran penalty {penalty.penalty_number}",
        entry_date=entry_date,
        lines=[
            {"account": cash_acc, "debit": amt, **dims},
            {"account": coa.AR, "credit": amt, **dims},
        ],
        source_type="CancellationPenalty",
        source_id=penalty.pk,
        created_by=created_by,
    )


# ── Kas movement (Fase 3 Group C) ──────────────────────────────

@transaction.atomic
def post_remittance_send(remittance, *, from_location, amount_sar, created_by, entry_date=None,
                         reservation=None, invoice=None, client=None):
    """Uang keluar dari kas cabang → Kas Dalam Perjalanan.

    Opsional dimensi `reservation`/`client` supaya `mengendap_per_reservation`
    bisa turun setelah diremit (kas SBY di-credit per reservasi, bukan hanya
    aggregate remittance).
    """
    src = _CASH_BY_LOCATION.get(from_location, coa.CASH_SBY)
    entry_date = entry_date or remittance.date or timezone.now().date()
    dims = {"remittance": remittance.pk, "branch": from_location}
    if reservation is not None:
        dims["reservation"] = getattr(reservation, "pk", reservation)
    if invoice is not None:
        dims["invoice"] = getattr(invoice, "pk", invoice)
    if client is not None:
        dims["client"] = getattr(client, "pk", client)
    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Remittance {remittance.remittance_number} kirim",
        entry_date=entry_date,
        lines=[
            {"account": coa.TRANSIT, "debit": amount_sar, **dims},
            {"account": src, "credit": amount_sar, **dims},
        ],
        source_type="Remittance",
        source_id=remittance.pk,
        created_by=created_by,
    )


@transaction.atomic
def post_remittance_receive(remittance, *, expected_sar, received_sar, created_by, entry_date=None):
    """Kas Pusat terima; selisih expected vs received → beban bank."""
    entry_date = entry_date or remittance.date or timezone.now().date()
    lines = [
        {"account": coa.CASH_PUSAT, "debit": received_sar, "remittance": remittance.pk, "branch": "pusat"},
        {"account": coa.TRANSIT, "credit": expected_sar, "remittance": remittance.pk},
    ]
    diff = expected_sar - received_sar
    if diff > 0:
        lines.append({"account": coa.EXP_BANKFEE, "debit": diff, "remittance": remittance.pk, "branch": "pusat"})
    elif diff < 0:
        lines.append({"account": coa.INC_FX_GAIN, "credit": -diff, "remittance": remittance.pk, "branch": "pusat"})
    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Remittance {remittance.remittance_number} diterima",
        entry_date=entry_date,
        lines=lines,
        source_type="Remittance",
        source_id=remittance.pk,
        created_by=created_by,
    )


def _normalize_send_segments(remittance, send_segments):
    """→ list tuple (reservation_id, invoice_id, client_id, from_location, amount).

    `send_segments` kosong → lump-sum: satu segmen tanpa dimensi reservasi.
    Nominal, urut prioritas: expected_sar (dari amount_idr/exchange_rate --
    fakta SISI KIRIM, uang yang keluar dari bank cabang; 2026-09-14: ini jadi
    basis utama karena received_amount_sar tidak pernah diisi lagi untuk
    remittance baru) -> received_amount_sar (jalur lama, dipertahankan utuh
    untuk remittance lama yang tak punya amount_idr) -> total kirim yang
    sudah tercatat di jurnal."""
    if send_segments:
        out = []
        for seg in send_segments:
            amt = int(seg.get("amount_sar") or 0)
            if not amt:
                continue
            out.append((
                _pk(seg.get("reservation")), _pk(seg.get("invoice")),
                _pk(seg.get("client")), seg.get("from_location", "sby"), amt,
            ))
        # Segmen yang belum menutup seluruh transfer: sisanya tetap tercatat
        # sebagai lump-sum. Tanpa ini, alokasi sebagian membuat sisa yang masih
        # di jalan seolah kembali ke Kas SBY dan basis status RMT ikut mengecil.
        expected = remittance.expected_sar
        remainder = (expected or 0) - sum(seg[-1] for seg in out)
        if expected is not None and remainder > 0:
            out.append((None, None, None, "sby", remainder))
        return out
    total = int(
        (remittance.expected_sar or 0)
        or (remittance.received_amount_sar or 0)
        or remittance.total_sar or 0
    )
    return [(None, None, None, "sby", total)] if total else []


def _remittance_leg_entries(remittance):
    """(send_entries, receive_entries) yang masih hidup untuk remittance ini —
    tiap item (entry, list[line]). Entry dengan debit Kas Pusat = sisi terima."""
    send, receive = [], []
    for e in _live_entries("Remittance", remittance.pk, JournalEntry.TYPE_REMITTANCE):
        lines = list(e.lines.all())
        if any(ln.account_id == coa.CASH_PUSAT and ln.debit for ln in lines):
            receive.append((e, lines))
        else:
            send.append((e, lines))
    return send, receive


def _send_entry_signature(lines):
    transit = next(ln for ln in lines if ln.account_id == coa.TRANSIT and ln.debit)
    src = next(ln for ln in lines if ln.credit)
    return (
        transit.reservation_id, transit.invoice_id, transit.client_id,
        _LOCATION_BY_CASH.get(src.account_id, "sby"), int(transit.debit),
    )


def _send_sort_key(sig):
    """Urutkan tuple segmen kirim yang bisa mengandung None (dimensi kosong)."""
    return (sig[0] or 0, sig[1] or 0, sig[2] or 0, sig[3], sig[4])


@transaction.atomic
def resync_remittance(remittance, *, created_by, send_segments=None,
                      received_sar=None, touch_receive=False):
    """Samakan jurnal remittance dengan keadaan sekarang. Idempotent-by-content:
    kalau sisi yang disentuh sudah cocok → no-op (tidak menambah reversal).

    send_segments: iterable {reservation, invoice, client, amount_sar,
        from_location?} — satu entry kirim per segmen supaya
        `mengendap_per_reservation` turun per reservasi. Kosong → lump-sum.

    touch_receive: False (default) = jangan sentuh sisi terima sama sekali.
        True = sinkronkan sisi terima ke `received_sar` (None = RMT belum
        diterima, sisi terima dibalik tanpa re-post; int = post/re-post).
    """
    entry_date = remittance.date or timezone.now().date()
    desired_send = _normalize_send_segments(remittance, send_segments)
    send_entries, receive_entries = _remittance_leg_entries(remittance)

    send_matches = (
        sorted((_send_entry_signature(lines) for _, lines in send_entries), key=_send_sort_key)
        == sorted(desired_send, key=_send_sort_key)
    )
    receive_matches = True
    if touch_receive:
        current_received = sum(
            int(next(ln.debit for ln in lines if ln.account_id == coa.CASH_PUSAT))
            for _, lines in receive_entries
        )
        want_received = int(received_sar) if received_sar is not None else 0
        # `expected` pada entry terima diturunkan dari total kirim, jadi kalau
        # sisi kirim berubah, sisi terima wajib diposting ulang juga.
        receive_matches = current_received == want_received and send_matches

    if send_matches and receive_matches:
        return

    sent_total = sum(amt for *_, amt in desired_send)
    if not send_matches:
        for e, _ in send_entries:
            reverse_entry(e, reversal_date=entry_date, created_by=created_by)
        for reservation_id, invoice_id, client_id, from_location, amt in desired_send:
            post_remittance_send(
                remittance, from_location=from_location, amount_sar=amt,
                created_by=created_by, entry_date=entry_date,
                reservation=reservation_id, invoice=invoice_id, client=client_id,
            )

    if touch_receive and not receive_matches:
        for e, _ in receive_entries:
            reverse_entry(e, reversal_date=entry_date, created_by=created_by)
        if received_sar is not None:
            expected = (remittance.expected_sar if remittance.expected_sar is not None
                        else sent_total)
            post_remittance_receive(
                remittance, expected_sar=expected, received_sar=int(received_sar),
                created_by=created_by, entry_date=entry_date,
            )


@transaction.atomic
def post_refund(client, *, from_location, amount_sar, created_by, entry_date,
                use_credit=True, idempotency_key=None, proof=None):
    """Refund ke client: DR Titipan (atau Piutang) / CR Kas.

    `idempotency_key` opsional: kasus baris event tunggal (dua kaki REFUND
    punya source yang sama) biar pemanggilan ulang tidak dobel-posting.
    `proof` (FileField value) opsional: bukti transfer yang dibawa entry ini.
    """
    src = _CASH_BY_LOCATION.get(from_location, coa.CASH_PUSAT)
    debit_acc = coa.CUST_CREDIT if use_credit else coa.AR
    return post_entry(
        entry_type=JournalEntry.TYPE_REFUND,
        description=f"Refund ke {client}",
        entry_date=entry_date,
        lines=[
            {"account": debit_acc, "debit": amount_sar, "client": client.pk, "branch": from_location},
            {"account": src, "credit": amount_sar, "client": client.pk, "branch": from_location},
        ],
        source_type="Client",
        source_id=client.pk,
        idempotency_key=idempotency_key,
        created_by=created_by,
        proof=proof,
    )


@transaction.atomic
def post_fund_transfer(client, *, from_reservation, to_reservation, amount_sar,
                       created_by, entry_date, idempotency_key=None):
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
        idempotency_key=idempotency_key,
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
                    idempotency_key=None):
    """Entry adjustment manual bebas — wajib balance + deskripsi."""
    if not description:
        raise FinanceError("Adjustment wajib punya deskripsi")
    return post_entry(
        entry_type=JournalEntry.TYPE_ADJUSTMENT,
        description=description,
        entry_date=entry_date,
        lines=lines,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )


@transaction.atomic
def reallocate_payment(payment, allocations, *, created_by):
    """Ubah alokasi payment yang sudah efektif (confirmed/allocated).

    Append-only ledger: jurnal payment yang live di-reverse, PaymentAllocation
    lama diganti, lalu diposting ulang dengan dimensi baru supaya baris CR
    Piutang menempel ke reservasi/service yang benar.

    `allocations`: iterable (target, amount_sar) — lihat allocate_payment.
    Total alokasi baru tidak boleh melebihi amount_sar payment.
    """
    from .errors import PaymentAlreadyProcessedError
    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} harus efektif dulu "
            "(confirmed/allocated) untuk direalokasi."
        )

    allocations = list(allocations)
    total = sum(int(a) for _, a in allocations)
    if total > int(payment.amount_sar):
        raise FinanceError(
            f"Alokasi {total:,} melebihi pembayaran {payment.amount_sar:,}"
        )

    # Reverse live payment journal entry(ies).
    reversed_ids = JournalEntry.objects.filter(
        reverses__isnull=False,
    ).values_list("reverses_id", flat=True)
    live = JournalEntry.objects.filter(
        reference_type="PaymentRecord", reference_id=payment.pk,
        entry_type=JournalEntry.TYPE_PAYMENT, is_reversal=False,
    ).exclude(pk__in=reversed_ids)
    for entry in live:
        reverse_entry(
            entry, reversal_date=payment.payment_date or timezone.now().date(),
            created_by=created_by,
            note=f"Reallocation of {payment.payment_number}",
        )

    # Replace PaymentAllocation rows.
    from ..models import CancellationPenalty, Reservation, ServiceItem
    from ..models.payment import PaymentAllocation
    payment.allocations.all().delete()
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
        PaymentAllocation.objects.create(payment=payment, amount_sar=int(amt), **kw)

    # Repost with the new allocation dims. Fresh idempotency key because the
    # default key (payment:...:confirm) is still held by the now-reversed
    # original entry, and idempotency_key is unique.
    repost_key = f"payment:{payment.payment_number}:realloc:{timezone.now().timestamp()}"
    post_payment(payment, created_by=created_by, idempotency_key=repost_key)

    # Re-sync invoice status.
    if payment.invoice_id:
        payment.invoice.sync_status()

    PaymentLog.objects.create(
        payment=payment,
        action=PaymentLog.ACTION_ALLOCATED,
        performed_by=created_by,
        note=f"Reallocated {payment.payment_number}",
    )
    return payment
