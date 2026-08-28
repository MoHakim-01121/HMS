"""Derivasi keuangan — baca JournalLine, satu-satunya sumber angka.

Pengganti hw/ledger.py. Views memanggil fungsi di sini, tidak pernah
Sum() tabel jurnal sendiri. Belum di-wire (Fase 6).
"""
from django.db.models import Sum

from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from . import accounts as coa


def _net(qs):
    a = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["d"] or 0) - (a["c"] or 0)


def _scoped(qs, company=None, as_of=None):
    if company:
        qs = qs.filter(journal_entry__company=company)
    if as_of:
        qs = qs.filter(journal_entry__created_at__lte=as_of)
    return qs


# ── Invoice ────────────────────────────────────────────────────

def _ar_qs(**f):
    return JournalLine.objects.filter(account_id=coa.AR, **f)


def _reversed_entry_ids():
    return JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)


def _live_charges(**f):
    """Baris DR Piutang dari charge entry yang BELUM di-reverse."""
    return _ar_qs(
        journal_entry__entry_type=JournalEntry.TYPE_CHARGE, **f,
    ).exclude(journal_entry_id__in=_reversed_entry_ids())


def invoice_charged_sar(invoice_id):
    """Total ditagih: charge entry hidup (bukan yang sudah di-reverse)."""
    return _live_charges(invoice_id=invoice_id).aggregate(d=Sum("debit"))["d"] or 0


def invoice_outstanding_sar(invoice_id):
    """Sisa piutang invoice = net semua baris Piutang (charge - payment +
    reversal). Positif = masih berutang."""
    return _net(_ar_qs(invoice_id=invoice_id))


def invoice_paid_sar(invoice_id):
    """Dibayar = ditagih - sisa. Kebal terhadap reversal (net-based)."""
    return invoice_charged_sar(invoice_id) - invoice_outstanding_sar(invoice_id)


def invoice_paid_map(invoice_ids):
    """{invoice_id: paid_sar} — charged - outstanding, dua query."""
    charged = {
        r["invoice_id"]: r["d"] or 0
        for r in _live_charges(invoice_id__in=invoice_ids)
        .values("invoice_id").annotate(d=Sum("debit"))
    }
    net = {
        r["invoice_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _ar_qs(invoice_id__in=invoice_ids)
        .values("invoice_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    return {
        i: charged.get(i, 0) - net.get(i, 0)
        for i in set(charged) | set(net)
    }


def _invoice_scoped(company, invoice_ids):
    qs = JournalLine.objects.all()
    if company:
        qs = qs.filter(journal_entry__company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return qs


def total_charged(company=None, invoice_ids=None):
    """Total ditagih (debit Piutang) untuk sekumpulan invoice."""
    return _invoice_scoped(company, invoice_ids).filter(
        account_id=coa.AR,
    ).aggregate(d=Sum("debit"))["d"] or 0


def paid_into(account_code, company=None, invoice_ids=None):
    """Total kas yang masuk ke akun ini dari pembayaran invoice-invoice ini."""
    return _invoice_scoped(company, invoice_ids).filter(
        account_id=account_code, debit__gt=0,
        journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
    ).aggregate(d=Sum("debit"))["d"] or 0


def mengendap(company=None, invoice_ids=None):
    """Kas Surabaya bersih untuk invoice-invoice ini (bisa negatif)."""
    return _net(_invoice_scoped(company, invoice_ids).filter(account_id=coa.CASH_SBY))


# ── Client ─────────────────────────────────────────────────────

def reservation_paid_map(invoice_id):
    """{reservation_id: paid_sar} — kredit bersih Piutang per reservasi
    (payment credit - reversal debit) utk invoice."""
    rows = (
        _ar_qs(invoice_id=invoice_id, reservation_id__isnull=False)
        .exclude(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .values("reservation_id").annotate(d=Sum("debit"), c=Sum("credit"))
    )
    return {r["reservation_id"]: (r["c"] or 0) - (r["d"] or 0) for r in rows}


def client_receivable(client_id):
    """Piutang client (positif = client berutang ke kita)."""
    return _net(JournalLine.objects.filter(client_id=client_id, account_id=coa.AR))


def client_credit_balance(client_id):
    """Saldo titipan / dana client (positif = kita berutang ke client)."""
    a = JournalLine.objects.filter(
        client_id=client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["c"] or 0) - (a["d"] or 0)


def client_statement(client_id, *, company=None, date_from=None, date_to=None, as_of=None):
    """Baris jurnal ber-dimensi client, urut kronologis, dengan running
    balance (debit - credit; positif = client berutang)."""
    qs = _scoped(
        JournalLine.objects.filter(
            client_id=client_id, account_id__in=[coa.AR, coa.CUST_CREDIT],
        ).select_related("journal_entry", "account"),
        company=company, as_of=as_of,
    ).order_by("journal_entry__entry_date", "journal_entry__created_at", "line_no")
    if date_from:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)

    rows, balance = [], 0
    for ln in qs:
        e = ln.journal_entry
        balance += ln.debit - ln.credit
        rows.append({
            "date": e.entry_date.isoformat(),
            "entry_number": e.entry_number,
            "entry_type": e.entry_type,
            "description": e.description,
            "account": ln.account_id,
            "account_name": ln.account.name,
            "debit": ln.debit,
            "credit": ln.credit,
            "balance": balance,
        })
    return {
        "rows": rows,
        "closing_balance": balance,
        "total_debit": sum(r["debit"] for r in rows),
        "total_credit": sum(r["credit"] for r in rows),
    }


# ── Kas ────────────────────────────────────────────────────────

def account_balance(account_code, *, company=None, as_of=None):
    return _net(_scoped(
        JournalLine.objects.filter(account_id=account_code), company=company, as_of=as_of,
    ))


def kas_surabaya(company=None):
    return account_balance(coa.CASH_SBY, company=company)


def kas_jakarta(company=None):
    return account_balance(coa.CASH_JKT, company=company)


def kas_pusat(company=None):
    return account_balance(coa.CASH_PUSAT, company=company)


def transit(company=None):
    return account_balance(coa.TRANSIT, company=company)


def mengendap_per_reservation(reservation_id, company=None):
    """Kas Surabaya yang menempel pada reservasi ini (belum diremit)."""
    return _net(_scoped(
        JournalLine.objects.filter(reservation_id=reservation_id, account_id=coa.CASH_SBY),
        company=company,
    ))


def kewajiban_kirim_sby(company=None):
    """Semua kas Surabaya idle wajib diremit ke pusat."""
    return kas_surabaya(company)


# ── Trial balance ──────────────────────────────────────────────

def trial_balance(*, company=None, date_from=None, date_to=None):
    qs = JournalLine.objects.all()
    if company:
        qs = qs.filter(journal_entry__company=company)
    if date_from:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)

    totals = {
        r["account"]: (r["d"] or 0, r["c"] or 0)
        for r in qs.values("account").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    groups, total_d, total_c = [], 0, 0
    for acc in LedgerAccount.objects.all():
        d, c = totals.get(acc.code, (0, 0))
        if not d and not c:
            continue
        total_d += d
        total_c += c
        groups.append({
            "account": acc.code, "account_name": acc.name,
            "type": acc.type, "debit": d, "credit": c, "net": d - c,
        })
    return {
        "groups": groups,
        "total_debit": total_d,
        "total_credit": total_c,
        "balanced": total_d == total_c,
    }
