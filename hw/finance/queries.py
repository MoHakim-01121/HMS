"""Derivasi keuangan — baca JournalLine, satu-satunya sumber angka.

Pengganti hw/ledger.py. Views memanggil fungsi di sini, tidak pernah
Sum() tabel jurnal sendiri. Belum di-wire (Fase 6).
"""
from django.db.models import Min, Sum

from ..models.client import Client
from ..models.choices import Company
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


def invoice_paid_map_before(invoice_ids, before_date):
    """{invoice_id: paid_sar} dihitung hanya dari baris jurnal dengan
    `entry_date < before_date` — untuk "outstanding per akhir bulan" pada
    dashboard (pengganti sum legacy `Payment.amount_sar`)."""
    charged = {
        r["invoice_id"]: r["d"] or 0
        for r in _live_charges(invoice_id__in=invoice_ids)
        .filter(journal_entry__entry_date__lt=before_date)
        .values("invoice_id").annotate(d=Sum("debit"))
    }
    net = {
        r["invoice_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _ar_qs(invoice_id__in=invoice_ids)
        .filter(journal_entry__entry_date__lt=before_date)
        .values("invoice_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    return {
        i: charged.get(i, 0) - net.get(i, 0)
        for i in set(charged) | set(net)
    }


def payment_history_rows(invoice):
    """Riwayat pembayaran satu invoice untuk display — dari PaymentRecord,
    satu-satunya sumber truth pembayaran (finance page, form invoice, backfill
    semuanya menulis PaymentRecord; legacy `Payment` tidak lagi dibaca).

    Hanya status ber-efek-jurnal (PaymentRecord.EFFECTIVE_STATUSES) yang
    dikembalikan; reversal/rejected/pending disembunyikan. Semua konsumen
    (invoice detail, form edit, PDF, konteks visa) memakai fungsi ini supaya
    satu invoice tak pernah menampilkan angka dari dua sumber berbeda.
    """
    from ..models.payment import PaymentRecord

    prs = list(
        PaymentRecord.objects
        .filter(invoice=invoice, status__in=PaymentRecord.EFFECTIVE_STATUSES)
        .select_related('reservation', 'service_item')
        .prefetch_related('allocations', 'allocations__reservation', 'allocations__service_item')
        .order_by('payment_date', 'pk')
    )

    rows = []
    for pr in prs:
        refs = []
        svc_nos = []
        if pr.reservation_id and pr.reservation:
            refs.append(pr.reservation.reservation_number)
            if str(pr.reservation.reservation_number).isdigit():
                svc_nos.append(int(pr.reservation.reservation_number))
        if pr.service_item_id and pr.service_item:
            svc_nos.append(pr.service_item.service_number)
        for a in pr.allocations.all():
            if a.reservation_id and a.reservation and a.reservation.reservation_number not in refs:
                refs.append(a.reservation.reservation_number)
            if a.service_item_id and a.service_item and a.service_item.service_number not in svc_nos:
                svc_nos.append(a.service_item.service_number)
        rows.append({
            'ref': ', '.join(refs) or pr.reference or pr.payment_number,
            'svc_nos': svc_nos,
            'payment_number': pr.payment_number,
            'payment_date': pr.payment_date,
            'method': pr.method,
            'amount': pr.amount,
            'currency': pr.currency,
            'exchange_rate': float(pr.exchange_rate) or 1,
            'amount_sar': pr.amount_sar,
            'note': pr.note or '',
            'proof': pr.proof,
        })
    return rows


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


def cl_paid_sar_map(letters):
    """Bulk ConfirmationLetter.paid_sar: {cl_pk: paid_sar} dari jurnal.

    Nomor CL = nomor reservasi pada invoice hotel, jadi CL dicocokkan ke baris
    pembayaran lewat `reservation.reservation_number == confirmation_number`
    (dalam company yang sama). Paid = kredit bersih Piutang (payment - reversal)
    pada baris jurnal ber-dimensi reservasi itu — konsisten dengan
    `reservation_paid_map`."""
    if not letters:
        return {}
    numbers = {cl.confirmation_number for cl in letters}
    companies = {cl.company for cl in letters}
    rows = (
        _ar_qs(
            reservation__reservation_number__in=numbers,
            journal_entry__company__in=companies,
        )
        .exclude(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .values("journal_entry__company", "reservation__reservation_number")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    by_key = {
        (r["journal_entry__company"], r["reservation__reservation_number"]): (r["c"] or 0) - (r["d"] or 0)
        for r in rows
    }
    return {cl.pk: by_key.get((cl.company, cl.confirmation_number), 0) for cl in letters}


def client_receivable(client_id):
    """Piutang client (positif = client berutang ke kita)."""
    return _net(JournalLine.objects.filter(client_id=client_id, account_id=coa.AR))


def client_billed_sar(client_id):
    """Total ditagih ke client = debit Piutang dari charge yang masih hidup."""
    return (
        _ar_qs(client_id=client_id)
        .filter(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .aggregate(d=Sum("debit"))["d"] or 0
    )


def client_paid_sar(client_id):
    """Total kas yang masuk dari client = debit kas dari entry payment yang
    masih hidup (from-credit payment tidak menyentuh kas, jadi tidak
    dobel-hitung)."""
    return _net(
        JournalLine.objects.filter(
            client_id=client_id,
            account_id__in=[coa.CASH_SBY, coa.CASH_JKT, coa.CASH_PUSAT],
            debit__gt=0,
            journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
        ).exclude(journal_entry_id__in=_reversed_entry_ids())
    )


def client_credit_balance(client_id):
    """Saldo titipan / dana client (positif = kita berutang ke client)."""
    a = JournalLine.objects.filter(
        client_id=client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["c"] or 0) - (a["d"] or 0)


def client_reservation_ids(client_id):
    """Set reservasi milik client dari dimensi baris jurnal yang masih hidup.

    Pengganti pembacaan Charge (tabel legacy, tidak lagi ditulis oleh alur
    billing sejak jurnal jadi system of record): reservasi seorang client
    adalah yang pernah muncul ber-dimensi `reservation` pada baris jurnal
    ber-dimensi `client` yang bersangkutan."""
    return set(
        JournalLine.objects.exclude(reservation_id=None)
        .filter(client_id=client_id)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .values_list("reservation_id", flat=True)
    )


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
            "date": e.entry_date,
            "entry_number": e.entry_number,
            "entry_type": e.entry_type,
            "type": "debit" if ln.debit else "credit",
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


def client_statement_with_opening(client_id, *, company=None, date_from=None, date_to=None, as_of=None):
    """client_statement() + saldo awal yang benar untuk periode yang mulai di
    tengah riwayat (bukan reset ke nol). Konsisten dengan versi legacy."""
    from datetime import timedelta
    opening_balance = 0
    if date_from:
        prior = client_statement(
            client_id, company=company, date_to=date_from - timedelta(days=1), as_of=as_of,
        )
        opening_balance = prior["closing_balance"]

    st = client_statement(
        client_id, company=company, date_from=date_from, date_to=date_to, as_of=as_of,
    )
    for r in st["rows"]:
        r["balance"] += opening_balance
    closing_balance = st["rows"][-1]["balance"] if st["rows"] else opening_balance
    return {
        "rows": st["rows"],
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "total_debit": st["total_debit"],
        "total_credit": st["total_credit"],
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


def total_allocated(company=None):
    """Total kas yang sudah 'dipakai' mengurangi piutang (credit bersih Piutang,
    selain charge) — analog total Allocation legacy. = ditagih - sisa AR net."""
    return total_charged(company, ) - _net(_scoped(_ar_qs(), company=company))


def surplus_pusat(company=None):
    return kas_pusat(company) + selisih_kurs(company) - total_allocated(company)


def kewajiban_kirim_sby(company=None):
    """Semua kas Surabaya idle wajib diremit ke pusat. Pertahankan makna
    legacy: -surplus_pusat (bukan sekadar kas_surabaya), supaya dashboard
    remittance tidak kehilangan pasangan KPI kewajiban_kirim + saldo_dana."""
    return -surplus_pusat(company)


# ── Remittance ─────────────────────────────────────────────────

def remittance_sent_sar(remittance_id):
    """Total SAR yang dikirim utk remittance ini = debit TRANSIT dari entry
    send yang masih hidup. Entry receive meng-credit TRANSIT (bukan debit),
    jadi Sum(debit) hanya mengunci sisi kirim."""
    return (
        JournalLine.objects.filter(
            remittance_id=remittance_id, account_id=coa.TRANSIT,
        ).exclude(journal_entry_id__in=_reversed_entry_ids())
        .aggregate(d=Sum("debit"))["d"] or 0
    )


def remittance_has_live_entries(remittance_id):
    """True kalau remittance ini punya baris jurnal REMITTANCE yang belum
    di-reverse — dipakai guard hapus (dokumen keuangan tak boleh hilang)."""
    return (
        JournalLine.objects.filter(
            remittance_id=remittance_id,
            journal_entry__entry_type=JournalEntry.TYPE_REMITTANCE,
            journal_entry__is_reversal=False,
        ).exclude(journal_entry_id__in=_reversed_entry_ids()).exists()
    )


def selisih_kurs(company=None):
    """Saldo kliring selisih kurs (FX_CLEARING) untuk company."""
    return _net(_scoped(
        JournalLine.objects.filter(account_id=coa.FX_CLEARING), company=company,
    ))


def piutang(reservation_id):
    """Sisa piutang satu reservasi = net baris Piutang ber-dimensi reservasi
    (charge debit - payment credit) yang masih hidup."""
    return _net(_ar_qs(reservation_id=reservation_id).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    ))


def reservation_cash_breakdown(company=None):
    """Bulk per-reservation cash breakdown untuk dashboard remittance:
    {reservation_id: {terbayar_sby, terbayar_jkt, terbayar_direct,
    sudah_dikirim, mengendap, mengendap_jkt}} — derivasi dari JournalLine
    (payment legs ke kas + remittance send credit kas cabang per reservasi)."""
    from collections import defaultdict
    qs = JournalLine.objects.exclude(reservation_id=None).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    )
    if company:
        qs = qs.filter(journal_entry__company=company)

    pay = (qs.filter(journal_entry__entry_type=JournalEntry.TYPE_PAYMENT, debit__gt=0)
           .values("reservation_id", "account_id").annotate(d=Sum("debit")))
    send = (qs.filter(journal_entry__entry_type=JournalEntry.TYPE_REMITTANCE)
            .values("reservation_id", "account_id").annotate(c=Sum("credit")))

    out = defaultdict(lambda: {
        "terbayar_sby": 0, "terbayar_jkt": 0, "terbayar_direct": 0,
        "sent_from_sby": 0, "sent_from_jkt": 0,
    })
    for r in pay:
        rid = r["reservation_id"]
        if r["account_id"] == coa.CASH_SBY:
            out[rid]["terbayar_sby"] += r["d"]
        elif r["account_id"] == coa.CASH_JKT:
            out[rid]["terbayar_jkt"] += r["d"]
        elif r["account_id"] == coa.CASH_PUSAT:
            out[rid]["terbayar_direct"] += r["d"]
    for r in send:
        rid = r["reservation_id"]
        if r["account_id"] == coa.CASH_SBY:
            out[rid]["sent_from_sby"] += r["c"]
        elif r["account_id"] == coa.CASH_JKT:
            out[rid]["sent_from_jkt"] += r["c"]

    return {
        rid: {
            "terbayar_sby": d["terbayar_sby"],
            "terbayar_jkt": d["terbayar_jkt"],
            "terbayar_direct": d["terbayar_direct"],
            "sudah_dikirim": d["sent_from_sby"] + d["terbayar_direct"],
            "mengendap": d["terbayar_sby"] - d["sent_from_sby"],
            "mengendap_jkt": d["terbayar_jkt"] - d["sent_from_jkt"],
        }
        for rid, d in out.items()
    }


def reservation_first_payment_date_map(reservation_numbers, company=None):
    """{reservation_number: tanggal pembayaran paling awal} dari baris jurnal
    kredit Piutang (bukan charge) — dipakai mengurutkan baris remittance sesuai
    kapan reservasi mulai dibayar."""
    if not reservation_numbers:
        return {}
    qs = _ar_qs(reservation__reservation_number__in=list(reservation_numbers))
    if company:
        qs = qs.filter(journal_entry__company=company)
    rows = (
        qs.exclude(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .values("reservation__reservation_number")
        .annotate(first=Min("journal_entry__entry_date"))
    )
    return {r["reservation__reservation_number"]: r["first"] for r in rows}


def reservation_remittance_map(company=None, linked_numbers=None):
    """Riwayat remittance per reservasi (baca RemittanceLine, bukan jurnal):
    {reservation_number: [{rmt_id, rmt_number, date, status, amount_sar}]}."""
    from collections import defaultdict
    from ..models.invoice import RemittanceLine
    qs = RemittanceLine.objects.select_related("remittance").order_by(
        "remittance__date", "remittance__created_at",
    )
    if company:
        qs = qs.filter(remittance__company=company)
    if linked_numbers is not None:
        qs = qs.filter(linked_number__in=linked_numbers)
    result = defaultdict(list)
    for l in qs:
        result[l.linked_number].append({
            "rmt_id": l.remittance_id, "rmt_number": l.remittance.remittance_number,
            "date": l.remittance.date, "status": l.remittance.status,
            "amount_sar": int(l.amount_sar or 0),
        })
    return result


def client_paid_map(client_ids):
    """{client_id: gross cash masuk dari client} — satu query agregat."""
    rows = (
        JournalLine.objects.filter(
            client_id__in=client_ids,
            account_id__in=[coa.CASH_SBY, coa.CASH_JKT, coa.CASH_PUSAT],
            debit__gt=0, journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
        ).exclude(journal_entry_id__in=_reversed_entry_ids())
        .values("client_id").annotate(d=Sum("debit"))
    )
    return {r["client_id"]: r["d"] or 0 for r in rows}


def clients_overview(company=Company.KONOZ):
    """Agregat bulk per-client untuk halaman daftar statement. Derivasinya
    konsisten dengan properti Client (billed/payable/credit) dari jurnal."""
    from collections import defaultdict
    clients = {}
    for c in Client.objects.filter(company=company):
        clients[c.id] = c
    cids = list(clients)

    billed = {
        r["client_id"]: r["d"] or 0
        for r in _ar_qs(client_id__in=cids)
        .filter(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .values("client_id").annotate(d=Sum("debit"))
    }
    paid = client_paid_map(cids)
    receivable = {
        r["client_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _ar_qs(client_id__in=cids)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    credit = {
        r["client_id"]: (r["c"] or 0) - (r["d"] or 0)
        for r in JournalLine.objects.filter(client_id__in=cids, account_id=coa.CUST_CREDIT)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }

    overview = [{
        "client_id": cid,
        "tagihan": billed.get(cid, 0),
        "terbayar": paid.get(cid, 0),
        "allocated": billed.get(cid, 0) - receivable.get(cid, 0),
        "piutang": receivable.get(cid, 0),
        "saldo_dana": credit.get(cid, 0),
    } for cid in cids]
    overview.sort(key=lambda r: (-r["piutang"], r["client_id"]))
    return overview


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
