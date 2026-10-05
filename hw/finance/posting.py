"""Posting layer — satu-satunya cara menulis ke general ledger.

`post_entry()` adalah primitive: bikin satu JournalEntry immutable + baris-
barisnya, balance per currency, dengan seq monoton + rantai hash +
idempotency. Semua fungsi posting per-event (Fase 3) dibangun di atasnya.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

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
from ..utils import round_half_up

logger = logging.getLogger(__name__)

_DIMS = ("branch", "client", "invoice", "invoice_line", "penalty", "remittance")
_FX_PLACES = Decimal("0.00000001")


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
        "currency": spec.get("currency") or "SAR",
        "amount_txn": spec.get("amount_txn"),
        "fx_rate": _fx(spec.get("fx_rate")),
        "note": spec.get("note", ""),
    }
    for dim in _DIMS:
        v = spec.get(dim)
        row[f"{dim}_id"] = getattr(v, "pk", v)
    if row["invoice_line_id"] is not None:
        from ..models.invoice import InvoiceLine
        line_invoice = InvoiceLine.objects.filter(pk=row["invoice_line_id"]).values_list("invoice_id", flat=True).first()
        if row["invoice_id"] is None:
            row["invoice_id"] = line_invoice
        elif row["invoice_id"] != line_invoice:
            raise FinanceError(f"Baris {line_no}: baris invoice {row['invoice_line_id']} bukan milik invoice {row['invoice_id']}")
    return row


def _fx(rate):
    """Kurs disimpan 8 desimal; dibulatkan di sini supaya yang di-hash sama
    dengan yang tersimpan."""
    if rate in (None, ""):
        return None
    return Decimal(str(rate)).quantize(_FX_PLACES, rounding=ROUND_HALF_UP)


def native(account, amount, rate=None):
    """Kolom nominal asli untuk kaki kas/bank `account` (kosong untuk SAR)."""
    if account.currency == "SAR" or not amount:
        return {}
    return {"currency": account.currency, "amount_txn": int(amount), "fx_rate": rate}


def _split_native(total_native, parts):
    """Bagi nominal asli `total_native` sebanding dengan `parts` (SAR); sisa
    pembulatan masuk bagian terakhir."""
    total = sum(parts)
    if not total:
        return [0 for _ in parts]
    out, used = [], 0
    for i, p in enumerate(parts):
        share = total_native - used if i == len(parts) - 1 else round_half_up(Decimal(total_native) * p / total)
        out.append(share)
        used += share
    return out


def _validate_balance(rows):
    """Debit dan kredit dalam SAR; mata uang transaksi tidak memecah neraca."""
    d = sum(r["debit"] for r in rows)
    c = sum(r["credit"] for r in rows)
    if d != c:
        raise JournalImbalanceError(f"Journal entry tidak balance: debit {d:,} != credit {c:,}")


_AR_LIKE = None  # diisi lazily; akun yang wajib punya dimensi client


def _needs_client(account_id):
    global _AR_LIKE
    if _AR_LIKE is None:
        from .accounts import AR, CUST_CREDIT
        _AR_LIKE = {AR, CUST_CREDIT}
    return account_id in _AR_LIKE


def _lock_journal_sequence():
    """Baris counter 'JE-SEQ', dikunci. Dibuat saat pertama dipakai dengan
    nilai awal = seq tertinggi yang sudah ada."""
    from ..models.sequence import DocumentSequence
    row = DocumentSequence.objects.select_for_update().filter(key="JE-SEQ").first()
    if row is None:
        start = JournalEntry.objects.aggregate(m=models.Max("seq"))["m"] or 0
        try:
            with transaction.atomic():
                DocumentSequence.objects.create(key="JE-SEQ", last_value=start)
        except IntegrityError:
            pass  # dibuat transaksi lain lebih dulu; tunggu kuncinya di bawah
        row = DocumentSequence.objects.select_for_update().get(key="JE-SEQ")
    return row


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
    reverses=None,
    proof=None,
):
    """Bikin satu JournalEntry immutable + baris-barisnya.

    lines: list LineSpec (dict). Kunci wajib: `account` (kode v2/v1),
    dan `debit`+`credit` ATAU `amount_sar` (signed). Opsional: `currency`,
    `amount_txn`/`fx_rate` (nominal asli, lihat native()), `note`, dimensi
    (branch/client/invoice/invoice_line/penalty/remittance).

    `source_type`/`source_id`: dokumen sumber (kunci JournalEntry.SOURCE_FIELDS
    atau SOURCE_ALIASES); kosong untuk jurnal manual dan entry pembalik.

    Idempotent terhadap `idempotency_key`: pemanggilan ulang mengembalikan
    entry yang sudah ada, tidak dobel-posting.
    """
    if idempotency_key:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).live().first()
        if existing:
            return existing
    source = _source_columns(source_type, source_id, entry_type)

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

    # Semua posting jurnal berbaris di satu baris counter (DocumentSequence
    # 'JE-SEQ', dikunci FOR UPDATE sampai transaksi ini selesai). Karena itu
    # seq tidak bisa kembar dan rantai hash tidak bisa bercabang: prev_hash
    # dibaca SETELAH kunci didapat, jadi selalu entry yang terakhir commit.
    # (Versi lama mengunci baris entry terakhir lalu "retry" saat bentrok —
    # retry di transaksi PostgreSQL yang sudah gagal tidak pernah berhasil.)
    seq_row = _lock_journal_sequence()
    if idempotency_key:
        # Cek ulang di bawah kunci: panggilan paralel dengan key yang sama
        # menunggu kunci di atas, lalu melihat entry yang baru commit di sini
        # — bukan menabrak UNIQUE dan berakhir 500.
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).live().first()
        if existing:
            return existing
    seq = seq_row.last_value + 1
    last = JournalEntry.objects.filter(seq__isnull=False).order_by("-seq").first()
    prev_hash = last.entry_hash if last else ""

    from ..numbering import generate_sequential_number
    entry = JournalEntry(
        entry_number=generate_sequential_number(JournalEntry, 'JE', field='entry_number', padding=6),
        entry_type=entry_type,
        description=description,
        entry_date=entry_date,
        seq=seq,
        prev_hash=prev_hash,
        idempotency_key=idempotency_key or None,
        reverses=reverses,
        **source,
        period=period,
        created_by=created_by,
        proof=proof,
    )
    entry.entry_hash = entry_hash(entry, rows, prev_hash)
    entry.save()
    seq_row.last_value = seq
    seq_row.save(update_fields=["last_value"])

    JournalLine.objects.bulk_create([
        JournalLine(journal_entry=entry, **r) for r in rows
    ])

    agg = JournalLine.objects.filter(journal_entry=entry).aggregate(
        d=models.Sum("debit"), c=models.Sum("credit"),
    )
    if (agg["d"] or 0) != (agg["c"] or 0):
        raise JournalImbalanceError("Balance check gagal setelah simpan")

    return entry


def _source_columns(source_type, source_id, entry_type):
    if not source_type or source_type == "JournalEntry":
        return {}
    name, alias_type = JournalEntry.SOURCE_ALIASES.get(source_type, (source_type, None))
    if name not in JournalEntry.SOURCE_FIELDS:
        raise FinanceError(f"Sumber jurnal tidak dikenal: {source_type}")
    if alias_type is not None and entry_type != alias_type:
        raise FinanceError(f"Sumber {source_type} hanya untuk entry {alias_type}")
    if source_id is None:
        raise FinanceError(f"Sumber {source_type} tanpa id")
    return {f"{JournalEntry.SOURCE_FIELDS[name]}_id": source_id}


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
            "amount_txn": ln.amount_txn,
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
        created_by=created_by,
        reverses=original,
    )


# ── Helpers ────────────────────────────────────────────────────

def _live_entries(source_type, source_id, entry_type):
    """Entry non-reversal untuk sumber ini yang BELUM di-reverse."""
    return list(
        JournalEntry.objects.for_source(source_type, source_id).filter(entry_type=entry_type).live()
        .order_by("seq", "pk")
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
    from ..models.invoice import InvoiceLine

    income = coa.INC_HOTEL if invoice.invoice_type == InvoiceType.HOTEL else coa.INC_SERVICE
    client_id = invoice.client_id
    lines = []
    billed = invoice.billed_lines()
    hotel_by_cl = {l.confirmation_letter_id: l.pk for l in billed if l.kind == InvoiceLine.KIND_HOTEL}
    for line in billed:
        amt = int(line.amount or 0)
        if not amt:
            continue
        if line.kind == InvoiceLine.KIND_HOTEL:
            br = invoice.branch_id
            lines.append({"account": coa.AR, "debit": amt, "client": client_id,
                          "invoice": invoice.pk, "invoice_line": line.pk, "branch": br})
            # Receivable stays with the issuing branch; hotel revenue is HQ's.
            lines.append({"account": income, "credit": amt,
                          "invoice": invoice.pk, "invoice_line": line.pk,
                          "branch": coa.HQ_BRANCH if income == coa.INC_HOTEL else br})
        elif line.kind == InvoiceLine.KIND_SERVICE:
            lines.append({"account": coa.AR, "debit": amt, "client": client_id,
                          "invoice": invoice.pk, "invoice_line": line.pk})
            lines.append({"account": income, "credit": amt,
                          "invoice": invoice.pk, "invoice_line": line.pk})
        elif line.kind == InvoiceLine.KIND_PENALTY:
            # Denda ditagih pada dimensi reservasinya: uang yang sudah masuk
            # untuk reservasi itu menutup denda lebih dulu. Pendapatannya Pusat.
            hotel_pk = hotel_by_cl.get(line.penalty.cl_id)
            lines.append({"account": coa.AR, "debit": amt, "client": client_id, "invoice": invoice.pk,
                          "invoice_line": hotel_pk, "penalty": line.penalty_id, "branch": invoice.branch_id})
            lines.append({"account": coa.INC_PENALTY, "credit": amt, "invoice": invoice.pk,
                          "invoice_line": hotel_pk, "penalty": line.penalty_id, "branch": coa.HQ_BRANCH})
    return lines


def _charge_key(penalty, invoice_line, client, branch):
    return ("penalty" if penalty else "line", penalty or invoice_line, client, branch)


def _charge_signature(lines):
    """{(dimensi, pk, client, cabang): nilai} dari kaki Piutang sebuah charge."""
    sig = {}
    for l in lines:
        if l["account"] != coa.AR:
            continue
        key = _charge_key(l.get("penalty"), l.get("invoice_line"), l.get("client"), l.get("branch"))
        sig[key] = sig.get(key, 0) + int(l.get("debit") or 0)
    return sig


def _posted_charge_signature(entries):
    sig = {}
    for ln in JournalLine.objects.filter(journal_entry__in=entries, account_id=coa.AR):
        key = _charge_key(ln.penalty_id, ln.invoice_line_id, ln.client_id, ln.branch_id)
        sig[key] = sig.get(key, 0) + int(ln.debit or 0)
    return sig


@transaction.atomic
def post_invoice_charge(invoice, *, created_by, entry_date=None, reason=None):
    """DR Piutang / CR Pendapatan per baris invoice.

    Idempotent-by-content: kalau charge invoice ini sudah terposting dengan
    nilai per baris yang sama → no-op; kalau berubah (revisi) → reversal charge
    lama lalu post ulang; kalau invoice tak punya baris → None. Setiap
    perubahan dicatat sebagai InvoiceRevision (`reason`: InvoiceRevision.
    REASON_*; bawaan: issue untuk yang pertama, selain itu line_change).
    """
    from . import invoice_revisions

    entry_date = entry_date or invoice.issued_date or timezone.now().date()
    if invoice.status == invoice.STATUS_VOID:
        return None  # a void invoice bills nothing; its charge was reversed
    lines = _invoice_charge_lines(invoice)

    live = _live_entries("Invoice", invoice.pk, JournalEntry.TYPE_CHARGE)
    if live and _posted_charge_signature(live) == _charge_signature(lines):
        return live[-1]
    for e in live:
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)
    if lines or live:
        invoice_revisions.record(invoice, reason=reason, user=created_by)
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
    rows still report allocated_sar and make invoice_views._line_has_money
    refuse to take those lines off the invoice. Callers log the returned rows in the
    PaymentLog they write, so no audit trail is lost.
    """
    rows = [
        {
            "invoice_line_id": a.invoice_line_id,
            "reservation_id": a.reservation_id,
            "service_item_id": a.service_item_id,
            "amount_sar": a.amount_sar,
        }
        for a in payment.allocations.select_related("invoice_line")
    ]
    if rows:
        payment.allocations.all().delete()
    return rows


@transaction.atomic
def void_invoice_charge(invoice, *, created_by, entry_date=None):
    """Reverse semua charge entry invoice yang masih hidup (invoice void)."""
    entry_date = entry_date or timezone.now().date()
    for e in _live_entries("Invoice", invoice.pk, JournalEntry.TYPE_CHARGE):
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)


# ── Payment-side (Fase 3 Group B) ──────────────────────────────

_CASH_BY_LOCATION = {"sby": coa.CASH_SBY, "jkt": coa.CASH_JKT, "pusat": coa.CASH_PUSAT}
_LOCATION_BY_CASH = {v: k for k, v in _CASH_BY_LOCATION.items()}


def _pk(v):
    return getattr(v, "pk", v)


def _allocation_dim(allocation):
    """Dimensi jurnal sebuah alokasi: baris invoice yang dibayarnya, dan
    invoice baris itu -- yang bisa invoice lain milik client yang sama dengan
    invoice utama pembayaran (realokasi lintas invoice)."""
    return {"invoice_line": allocation.invoice_line_id, "invoice": allocation.invoice_line.invoice_id}


def _payment_segments(payment):
    """[(nominal, dimensi)] — satu segmen per alokasi, plus sisa yang belum
    dialokasikan (tanpa dimensi baris) bila ada."""
    amt = int(payment.amount_sar)
    segments, used = [], 0
    allocs = list(payment.allocations.select_related("invoice_line")) if payment.pk else []
    for pa in allocs:
        segments.append((int(pa.amount_sar), _allocation_dim(pa)))
        used += int(pa.amount_sar)
    if used < amt:
        segments.append((amt - used, {}))
    return segments


def _payment_targets(payment):
    """Daftar identitas yang dibayar oleh payment ini, untuk deskripsi jurnal.

    Dari PaymentAllocation (satu payment bisa menutup beberapa reservasi/
    service). Nomor reservasi dipakai karena identitas stabil + konsisten
    dengan deskripsi jurnal lain (Charge/Remittance pakai nomor, bukan nama).
    """
    refs = []
    seen = set()

    def _add(spec):
        if spec is None or spec in seen:
            return
        seen.add(spec)
        refs.append(spec)

    if payment.pk:
        for pa in payment.allocations.select_related("invoice_line__confirmation_letter"):
            if pa.reservation_id and pa.reservation:
                _add(pa.reservation.reservation_number)
            elif pa.service_item_id and pa.service_item:
                _add(f"SVC#{pa.service_item.service_number}")

    return refs


@transaction.atomic
def post_payment(payment, *, created_by, idempotency_key=None, entry_date=None):
    """DR Kas (sesuai received_in) / CR Piutang. Idempotent per payment.

    Kalau payment punya PaymentAllocation → CR Piutang dipecah per alokasi
    (dimensi baris invoice) supaya piutang & mengendap per-
    reservasi akurat; sisa yang belum dialokasikan jadi satu baris CR
    Piutang bertingkat client/invoice saja.

    `idempotency_key` (opsional) meng-override key default. Dipakai realokasi,
    di mana jurnal lama sudah di-reverse (key default sudah terpakai & unik).
    `entry_date` (opsional, bawaan tanggal pembayaran): realokasi memposting
    ulang pada tanggal koreksinya.
    """
    if idempotency_key is None:
        default_key = f"payment:{payment.payment_number}:confirm"
        existing = JournalEntry.objects.filter(idempotency_key=default_key).first()
        if existing is not None:
            if JournalEntry.objects.filter(reverses=existing).exists():
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

    # Akun kas = akun buku besar rekening penerimanya.
    cash_acc = payment.receiving_account.ledger_account_id
    amt = int(payment.amount_sar)
    base = {"client": payment.client_id, "invoice": payment.invoice_id,
            "branch": payment.receiving_branch_code}

    # Satu segmen per alokasi (nominal, dimensi baris invoice), plus sisa yang
    # belum dialokasikan. Tiap segmen = DR Kas + CR Piutang berpasangan.
    segments = _payment_segments(payment)
    natives = _split_native(int(payment.amount or 0), [s for s, _ in segments])
    lines = []
    for (seg_amt, dim), seg_native in zip(segments, natives):
        cash_native = native(payment.receiving_account, seg_native, payment.exchange_rate)
        lines.append({"account": cash_acc, "debit": seg_amt, **base, **dim, **cash_native})
        lines.append({"account": coa.AR, "credit": seg_amt, **base, **dim})

    entry = post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} - {', '.join(_payment_targets(payment)) or 'unallocated'}",
        entry_date=entry_date or payment.payment_date,
        lines=lines,
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=idempotency_key or f"payment:{payment.payment_number}:confirm",
        created_by=created_by,
    )
    # Traceable movement log (v2.0 §25-28).
    from .bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=payment.receiving_account, direction="in", amount_sar=amt,
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
    base = {"client": payment.client_id, "invoice": payment.invoice_id}
    lines = []
    for seg_amt, dim in _payment_segments(payment):
        lines.append({"account": coa.CUST_CREDIT, "debit": seg_amt, **base, **dim})
        lines.append({"account": coa.AR, "credit": seg_amt, **base, **dim})
    return post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT,
        description=f"Payment {payment.payment_number} (titipan) - {', '.join(_payment_targets(payment)) or 'unallocated'}",
        entry_date=payment.payment_date,
        lines=lines,
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=f"payment:{payment.payment_number}:from-credit",
        created_by=created_by,
    )


@transaction.atomic
def post_remittance_send(remittance, *, amount_sar, created_by, entry_date=None):
    """Uang keluar dari rekening cabang asal → Kas Dalam Perjalanan (Transit)."""
    acc = remittance.from_account
    entry_date = entry_date or remittance.date or timezone.now().date()
    dims = {"remittance": remittance.pk, "branch": acc.branch_id}
    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Remittance {remittance.remittance_number} kirim",
        entry_date=entry_date,
        lines=[
            {"account": coa.TRANSIT, "debit": amount_sar, **dims},
            {"account": acc.ledger_account_id, "credit": amount_sar, **dims,
             **native(acc, remittance.amount_sent, remittance.exchange_rate)},
        ],
        source_type="Remittance",
        source_id=remittance.pk,
        created_by=created_by,
    )


@transaction.atomic
def resync_remittance(remittance, *, created_by):
    """Samakan jurnal kirim remittance dengan transfernya sekarang: satu entry
    Transit / rekening asal sebesar expected_sar. Idempotent-by-content: bila
    nominal dan rekeningnya sudah cocok, tidak ada yang diposting."""
    entry_date = remittance.date or timezone.now().date()
    want = int(remittance.expected_sar or 0)
    source = remittance.from_account.ledger_account_id
    live = _live_entries("Remittance", remittance.pk, JournalEntry.TYPE_REMITTANCE)
    posted = [(ln.account_id, int(ln.credit), ln.amount_txn) for e in live for ln in e.lines.all() if ln.credit]
    native_sent = native(remittance.from_account, remittance.amount_sent).get("amount_txn")
    if posted == ([(source, want, native_sent)] if want else []):
        return
    for e in live:
        reverse_entry(e, reversal_date=entry_date, created_by=created_by)
    if want:
        post_remittance_send(remittance, amount_sar=want, created_by=created_by, entry_date=entry_date)


def _allocation_target(target, payment=None):
    """Kolom PaymentAllocation untuk `target`: satu baris invoice (hotel atau
    service). Denda dibayar lewat baris hotel reservasinya, bukan sendiri."""
    from ..models.invoice import InvoiceLine

    if not (isinstance(target, InvoiceLine) and target.kind in (InvoiceLine.KIND_HOTEL, InvoiceLine.KIND_SERVICE)):
        raise FinanceError(f"Target alokasi tidak dikenali: {target!r}")
    if payment is not None:
        check_allocation(payment, target)
    return {"invoice_line_id": target.pk}


def check_allocation(payment, line):
    """Aturan sebuah alokasi: pembayaran hanya melunasi invoice client-nya
    sendiri, dan Services hanya dibayar ke rekening cabang penerbitnya (B12)."""
    invoice = line.invoice
    if invoice.client_id != payment.client_id:
        raise FinanceError(
            f"Invoice {invoice.invoice_number} milik client lain; pembayaran hanya melunasi invoice client-nya sendiri."
        )
    if line.kind == line.KIND_SERVICE and payment.receiving_account.branch_id != invoice.branch_id:
        raise FinanceError(
            f"Invoice Services {invoice.invoice_number} diterbitkan cabang {invoice.branch.name}, jadi hanya "
            f"bisa dibayar ke rekening cabang itu (bukan {payment.receiving_account})."
        )


@transaction.atomic
def allocate_payment(payment, allocations, *, created_by=None):
    """Tulis PaymentAllocation (analitik) — TANPA journal entry.

    allocations: iterable (target, amount_sar) di mana target adalah
    baris invoice (hotel atau service).
    """
    from ..models.payment import PaymentAllocation

    allocations = list(allocations)
    total = sum(int(a) for _, a in allocations)
    if total + int(payment.deposited_sar) > int(payment.amount_sar):
        raise FinanceError(
            f"Alokasi {total:,} melebihi pembayaran {payment.amount_sar:,}"
        )
    check_allocation_caps(payment, allocations)
    rows = []
    for target, amt in allocations:
        rows.append(PaymentAllocation(payment=payment, amount_sar=int(amt), **_allocation_target(target, payment)))
    PaymentAllocation.objects.bulk_create(rows)
    return rows


def _own_settled_by_line(payment):
    """{pk baris invoice: yang sudah dilunasi `payment` ke baris itu} dari
    jurnal pembayarannya yang masih hidup (kosong bila belum dikonfirmasi)."""
    entries = _live_entries("PaymentRecord", payment.pk, JournalEntry.TYPE_PAYMENT)
    if not entries:
        return {}
    rows = (
        JournalLine.objects.filter(journal_entry__in=entries, account_id=coa.AR, invoice_line__isnull=False)
        .values("invoice_line_id").annotate(d=models.Sum("debit"), c=models.Sum("credit"))
    )
    return {r["invoice_line_id"]: (r["c"] or 0) - (r["d"] or 0) for r in rows}


def allocation_caps(payment, line_ids):
    """{pk baris invoice: maksimum yang boleh dialokasikan `payment` ke baris itu}.

    = sisa tagihan baris -- net seluruh baris Piutang ber-dimensi baris itu:
    charge + denda - nota kredit - semua pembayaran/pemindahan, pembalik ikut
    sehingga saling hapus -- ditambah yang sudah dilunasi payment ini sendiri
    ke baris itu (alokasinya sendiri bukan "pembayaran lain")."""
    ids = list(set(line_ids))
    if not ids:
        return {}
    net = {
        r["invoice_line_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in JournalLine.objects.filter(account_id=coa.AR, invoice_line_id__in=ids)
        .values("invoice_line_id").annotate(d=models.Sum("debit"), c=models.Sum("credit"))
    }
    own = _own_settled_by_line(payment)
    return {pk: net.get(pk, 0) + own.get(pk, 0) for pk in ids}


def check_allocation_caps(payment, allocations):
    """Alokasi ke satu baris tidak boleh melebihi sisa tagihannya -- kelebihan
    bayar tidak bisa dibuat lewat alokasi. `allocations`: [(baris, nominal)]."""
    per_line, lines = {}, {}
    for target, amt in allocations:
        per_line[target.pk] = per_line.get(target.pk, 0) + int(amt)
        lines[target.pk] = target
    caps = allocation_caps(payment, per_line)
    for pk, amt in per_line.items():
        cap = caps[pk]
        if amt > cap:
            raise FinanceError(
                f"Alokasi {amt:,} SAR ke {lines[pk].label} melebihi sisa tagihannya ({max(cap, 0):,} SAR)."
            )


def allocation_snapshot(payment):
    """Isi alokasi payment untuk PaymentLog (jejak sebelum/sesudah)."""
    return [
        {
            "invoice_line_id": a.invoice_line_id,
            "label": a.invoice_line.label,
            "invoice": a.invoice_line.invoice.invoice_number,
            "amount_sar": a.amount_sar,
        }
        for a in payment.allocations.select_related(
            "invoice_line__invoice", "invoice_line__confirmation_letter__hotel", "invoice_line__penalty",
        ).order_by("pk")
    ]


# ── Kelebihan bayar → deposit client ───────────────────────────

@transaction.atomic
def move_payment_excess_to_deposit(payment, *, created_by, entry_date=None, amount=None):
    """Pindahkan kelebihan sebuah pembayaran (bagian Z tanpa alokasi) ke
    deposit client: DR Piutang / CR Titipan. Mengembalikan nominalnya.
    `amount` (opsional) memindahkan sebagian saja; bawaannya seluruh kelebihan.

    Selama masih kelebihan, uang itu hanya bisa dialokasikan ke tagihan client
    yang sama; sebagai deposit ia bisa dipakai membayar tagihan lain,
    dipindah ke client lain, atau dikembalikan."""
    payment = PaymentRecord.objects.select_for_update().get(pk=payment.pk)
    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        raise FinanceError(f"Payment {payment.payment_number} belum efektif.")
    excess = payment.unallocated_sar
    if excess <= 0:
        raise FinanceError(f"Payment {payment.payment_number} tidak punya kelebihan untuk dipindahkan.")
    if amount is not None:
        if not 0 < amount <= excess:
            raise FinanceError(
                f"Payment {payment.payment_number}: hanya {excess:,} SAR yang belum dialokasikan."
            )
        excess = amount
    dims = {"client": payment.client_id, "invoice": payment.invoice_id}
    post_entry(
        entry_type=JournalEntry.TYPE_TRANSFER,
        description=f"Kelebihan {payment.payment_number} → deposit client",
        entry_date=entry_date or timezone.now().date(),
        lines=[
            {"account": coa.AR, "debit": excess, "branch": payment.receiving_branch_code, **dims},
            {"account": coa.CUST_CREDIT, "credit": excess, **dims},
        ],
        source_type="PaymentRecord",
        source_id=payment.pk,
        idempotency_key=f"payment:{payment.payment_number}:deposit:{payment.deposited_sar + excess}",
        created_by=created_by,
    )
    before = {"deposited_sar": payment.deposited_sar}
    payment.deposited_sar += excess
    payment.save(update_fields=["deposited_sar"])
    PaymentLog.objects.create(
        payment=payment, action=PaymentLog.ACTION_DEPOSITED, performed_by=created_by,
        before_state=before, after_state={"deposited_sar": payment.deposited_sar},
        note=f"{excess:,} SAR moved to client deposit",
    )
    return excess


@transaction.atomic
def return_payment_deposit(payment, *, created_by, entry_date=None):
    """Batalkan pemindahan ke deposit milik pembayaran ini (dipanggil sebelum
    pembayarannya di-void / di-reverse). Ditolak bila depositnya sudah dipakai."""
    if not payment.deposited_sar:
        return 0
    if client_credit_balance(payment.client_id) < payment.deposited_sar:
        raise FinanceError(
            f"{payment.deposited_sar:,} SAR dari payment {payment.payment_number} sudah dipindah ke deposit "
            "client dan sebagian sudah dipakai. Pembayarannya tidak bisa dibatalkan."
        )
    for e in _live_entries("PaymentRecord", payment.pk, JournalEntry.TYPE_TRANSFER):
        reverse_entry(e, reversal_date=entry_date or timezone.now().date(), created_by=created_by)
    returned = payment.deposited_sar
    payment.deposited_sar = 0
    payment.save(update_fields=["deposited_sar"])
    return returned


def _shift_excess_to_deposit(excess_by_line, *, created_by, entry_date=None):
    """Kelebihan bayar per baris invoice -> deposit, lewat pembayaran yang
    uangnya ada di baris itu, supaya alokasi pembayaran dan buku besar tetap
    sama: alokasinya dikurangi (realokasi), lalu bagian itu dipindah ke
    deposit (move_payment_excess_to_deposit). Pembayaran terbaru dikurangi
    lebih dulu. Satu realokasi per pembayaran, walau ia membayar beberapa
    baris yang kelebihan.

    `excess_by_line`: {baris: nominal}. Mengembalikan {baris: sisa} yang
    tidak bisa dikaitkan ke alokasi pembayaran mana pun (uang di baris itu
    berasal dari luar alokasi, mis. data lama)."""
    from ..models.payment import PaymentAllocation

    takes = {}            # payment pk -> {allocation pk: nominal}
    payments = {}
    leftover = {}
    for line, excess in excess_by_line.items():
        left = excess
        allocs = (
            PaymentAllocation.objects.filter(
                invoice_line=line, payment__status__in=PaymentRecord.EFFECTIVE_STATUSES,
            ).select_related("payment").order_by("-payment__payment_date", "-payment_id")
        )
        for alloc in allocs:
            if left <= 0:
                break
            take = min(left, alloc.amount_sar)
            takes.setdefault(alloc.payment_id, {})[alloc.pk] = take
            payments[alloc.payment_id] = alloc.payment
            left -= take
        if left > 0:
            leftover[line] = left

    for payment_id, by_alloc in takes.items():
        payment = payments[payment_id]
        moved = sum(by_alloc.values())
        kept = [
            (a.invoice_line, a.amount_sar - by_alloc.get(a.pk, 0))
            for a in payment.allocations.select_related("invoice_line__invoice").order_by("pk")
        ]
        reallocate_payment(
            payment, [(line, amt) for line, amt in kept if amt > 0], created_by=created_by,
            note=f"{moved:,} SAR kelebihan bayar dilepas ke deposit",
        )
        move_payment_excess_to_deposit(payment, created_by=created_by, entry_date=entry_date, amount=moved)
    return leftover


@transaction.atomic
def move_invoice_excess_to_deposit(invoice, *, created_by, entry_date=None):
    """Pindahkan kelebihan bayar per reservasi di sebuah invoice hotel ke
    deposit client. Kelebihan ini muncul ketika reservasi yang sudah dibayar
    nilainya turun (CL berubah, atau dibatalkan dengan denda). Mengembalikan
    total yang dipindahkan.

    Lewat pembayaran yang uangnya ada di reservasi itu (_shift_excess_to_deposit),
    jadi detail pembayaran dan kwitansinya ikut berubah. Sisa yang tidak
    berasal dari alokasi pembayaran mana pun dipindah langsung di jurnal."""
    from .penalty_billing import reservation_balances

    excess_by_line = {
        row["line"]: -row["remaining"]
        for row in reservation_balances(invoice).values() if row["remaining"] < 0
    }
    total = sum(excess_by_line.values())
    if not total:
        raise FinanceError(f"Invoice {invoice.invoice_number} tidak punya kelebihan bayar.")

    leftover = _shift_excess_to_deposit(excess_by_line, created_by=created_by, entry_date=entry_date)
    if leftover:
        rest = sum(leftover.values())
        lines = [
            {"account": coa.AR, "debit": amt, "client": invoice.client_id, "invoice": invoice.pk,
             "invoice_line": line.pk, "branch": invoice.branch_id}
            for line, amt in leftover.items()
        ]
        lines.append({"account": coa.CUST_CREDIT, "credit": rest, "client": invoice.client_id, "invoice": invoice.pk})
        post_entry(
            entry_type=JournalEntry.TYPE_TRANSFER,
            description=f"Kelebihan bayar {invoice.invoice_number} → deposit client",
            entry_date=entry_date or timezone.now().date(),
            lines=lines,
            source_type="Invoice",
            source_id=invoice.pk,
            created_by=created_by,
        )
        logger.warning(
            "invoice %s: %s SAR excess not tied to any payment allocation moved by journal only",
            invoice.invoice_number, rest,
        )
    return total


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
def reallocate_payment(payment, allocations, *, created_by, log_action=None, note=""):
    """Ubah alokasi payment yang sudah efektif (confirmed/allocated).

    Append-only ledger: jurnal payment yang live di-reverse, PaymentAllocation
    lama diganti, lalu diposting ulang dengan dimensi baru supaya baris CR
    Piutang menempel ke baris invoice yang benar -- boleh baris dari invoice
    lain milik client yang sama.

    Koreksi bertanggal hari ini (pembalik dan posting ulang), bukan tanggal
    pembayaran: realokasi pembayaran di bulan yang sudah ditutup tetap bisa,
    dan angka bulan lalu tidak berubah diam-diam. Kas tidak bergerak karena
    nilainya sama; yang pindah hanya piutang antar baris. Baris buku bank
    pembayaran tetap satu (record_bank_transaction unik per sumber).

    `allocations`: iterable (target, amount_sar) -- lihat allocate_payment.
    Total alokasi baru tidak boleh melebihi amount_sar payment, dan alokasi
    ke satu baris tidak melebihi sisa tagihannya (check_allocation_caps).
    Mengembalikan payment yang sudah dimuat ulang.
    """
    from .errors import PaymentAlreadyProcessedError
    # Kunci baris pembayaran: Reallocate dan Move to deposit yang berjalan
    # bersamaan tidak boleh sama-sama membaca deposited_sar yang basi.
    payment = PaymentRecord.objects.select_for_update().get(pk=payment.pk)
    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        raise PaymentAlreadyProcessedError(
            f"Payment {payment.payment_number} harus efektif dulu "
            "(confirmed/allocated) untuk direalokasi."
        )

    allocations = list(allocations)
    total = sum(int(a) for _, a in allocations)
    if total + int(payment.deposited_sar) > int(payment.amount_sar):
        raise FinanceError(
            f"Alokasi {total:,} melebihi pembayaran {payment.amount_sar:,}"
            + (f" (sudah {payment.deposited_sar:,} dipindah ke deposit)" if payment.deposited_sar else "")
        )
    check_allocation_caps(payment, allocations)

    today = timezone.now().date()
    before = allocation_snapshot(payment)

    # Reverse live payment journal entry(ies).
    for entry in _live_entries("PaymentRecord", payment.pk, JournalEntry.TYPE_PAYMENT):
        reverse_entry(
            entry, reversal_date=today, created_by=created_by,
            note=f"Reallocation of {payment.payment_number}",
        )

    # Replace PaymentAllocation rows.
    from ..models.payment import PaymentAllocation
    payment.allocations.all().delete()
    for target, amt in allocations:
        PaymentAllocation.objects.create(payment=payment, amount_sar=int(amt), **_allocation_target(target, payment))

    # Repost with the new allocation dims. Fresh idempotency key because the
    # default key (payment:...:confirm) is still held by the now-reversed
    # original entry, and idempotency_key is unique.
    repost_key = f"payment:{payment.payment_number}:realloc:{timezone.now().timestamp()}"
    post_payment(payment, created_by=created_by, idempotency_key=repost_key, entry_date=today)

    PaymentLog.objects.create(
        payment=payment,
        action=log_action or PaymentLog.ACTION_ALLOCATED,
        before_state={"allocations": before},
        after_state={"allocations": allocation_snapshot(payment)},
        performed_by=created_by,
        note=note or f"Reallocated {payment.payment_number}",
    )
    return payment
