"""Derivasi keuangan — baca JournalLine, satu-satunya sumber angka.

Pengganti hw/ledger.py. Views memanggil fungsi di sini, tidak pernah
Sum() tabel jurnal sendiri. Belum di-wire (Fase 6).
"""
from django.db.models import Min, Q, Sum

from ..models.client import Client
from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from . import accounts as coa


def _net(qs):
    a = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["d"] or 0) - (a["c"] or 0)


def _scoped(qs, as_of=None):
    if as_of:
        qs = qs.filter(journal_entry__created_at__lte=as_of)
    return qs


# ── Invoice ────────────────────────────────────────────────────

_HOTEL = "hotel"
# Entry yang menyentuh transfer cabang → Pusat: kirim/terima, alokasi penerimaan, selisih.
REMITTANCE_TYPES = (JournalEntry.TYPE_REMITTANCE, JournalEntry.TYPE_ALLOCATE, JournalEntry.TYPE_REMITTANCE_DIFF)


def _in_accounts(*codes):
    """Baris pada akun-akun ini atau akun anaknya (kas per mata uang)."""
    return Q(account_id__in=codes) | Q(account__parent_id__in=codes)


def _root(account_id, parent_id):
    return parent_id or account_id


def _ar_qs(**f):
    return JournalLine.objects.filter(account_id=coa.AR, **f)


def _reversed_entry_ids():
    return JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)


# Billing = what the client is asked to pay: charges and credit notes, plus
# the reversals of either (an invoice re-post or void, a voided credit note).
# Everything else that touches Piutang settles it (payments, allocations,
# transfers, their reversals). Paid = settled, never "billed − open", so a
# credit note is not mistaken for money received.
BILLING_TYPES = (JournalEntry.TYPE_CHARGE, JournalEntry.TYPE_CREDIT_NOTE)
_BILLING_Q = (
    Q(journal_entry__entry_type__in=BILLING_TYPES)
    | Q(journal_entry__reverses__entry_type__in=BILLING_TYPES)
)


def _billing(**f):
    return _ar_qs(**f).filter(_BILLING_Q)


def _settling(**f):
    return _ar_qs(**f).exclude(_BILLING_Q)


def _live_charges(**f):
    """Baris DR Piutang dari charge entry yang BELUM di-reverse."""
    return _ar_qs(
        journal_entry__entry_type=JournalEntry.TYPE_CHARGE, **f,
    ).exclude(journal_entry_id__in=_reversed_entry_ids())


def invoice_charged_sar(invoice_id):
    """Total ditagih: charge entry hidup (bukan yang sudah di-reverse)."""
    return _live_charges(invoice_id=invoice_id).aggregate(d=Sum("debit"))["d"] or 0


def invoice_credited_sar(invoice_id):
    """Dikurangi nota kredit yang masih berlaku (ke Piutang maupun titipan)."""
    from ..models.credit_note import CreditNote
    return CreditNote.objects.filter(
        invoice_id=invoice_id, status=CreditNote.STATUS_ACTIVE,
    ).aggregate(t=Sum("lines__amount_sar"))["t"] or 0


def invoice_credit_deposited_sar(invoice_id):
    """Bagian nota kredit hidup yang masuk titipan client: uang yang sudah
    dibayar ke invoice ini lalu dipindah keluar karena tagihannya turun."""
    from ..models.credit_note import CreditNote
    return CreditNote.objects.filter(
        invoice_id=invoice_id, status=CreditNote.STATUS_ACTIVE,
    ).aggregate(t=Sum("to_deposit_sar"))["t"] or 0


def invoice_credited_map(invoice_ids):
    """{invoice_id: (credited_sar, deposited_sar)} untuk nota kredit hidup."""
    from ..models.credit_note import CreditNote
    live = CreditNote.objects.filter(invoice_id__in=invoice_ids, status=CreditNote.STATUS_ACTIVE)
    credited = {r["invoice_id"]: r["t"] or 0 for r in live.values("invoice_id").annotate(t=Sum("lines__amount_sar"))}
    deposited = {r["invoice_id"]: r["t"] or 0 for r in live.values("invoice_id").annotate(t=Sum("to_deposit_sar"))}
    return {i: (credited[i], deposited.get(i, 0)) for i in credited}


def invoice_billed_sar(invoice_id):
    """Tagihan bersih di Piutang: charge hidup − nota kredit hidup."""
    return _net(_billing(invoice_id=invoice_id))


def invoice_outstanding_sar(invoice_id):
    """Sisa piutang invoice = net semua baris Piutang (charge - payment +
    reversal). Positif = masih berutang."""
    return _net(_ar_qs(invoice_id=invoice_id))


def invoice_paid_sar(invoice_id):
    """Dibayar = kredit bersih Piutang di luar tagihan (payment − reversal).
    Kebal terhadap reversal dan nota kredit."""
    return -_net(_settling(invoice_id=invoice_id))


def invoice_unallocated_sar(invoice_id):
    """Jumlah pembayaran yang sudah diterima tapi belum dialokasikan ke
    reservasi/service mana pun = invoice_paid - sum(reservation_paid_map).

    Positif = ada sisa yang belum ditentukan alokasinya.
    Nol = semua pembayaran sudah teralokasi."""
    paid_total = invoice_paid_sar(invoice_id)
    rpm = reservation_paid_map(invoice_id)
    return max(0, paid_total - sum(rpm.values()))


def payment_unallocated_sar(payment_id):
    """Sisa alokasi satu payment yang belum ditentukan.

    = amount_sar - sum(PaymentAllocation.amount_sar) - deposited_sar.

    Setiap tujuan pembayaran adalah baris PaymentAllocation (payment yang
    dibuat untuk satu reservasi langsung punya satu alokasi penuh). Hanya
    punya invoice_id BUKAN tanda teralokasi: payment masih menunggu pemecahan
    per baris invoice, sehingga tetap dihitung sebagai unallocated.

    Berguna untuk menampilkan badge 'X SAR unallocated' di payment detail."""
    return payment_unallocated_map([payment_id]).get(payment_id, 0)


def payment_unallocated_map(payment_ids):
    """{payment_id: unallocated_sar} — bentuk bulk dari payment_unallocated_sar.

    Dua query untuk N payment, bukan dua query PER payment.
    """
    from ..models.payment import PaymentRecord, PaymentAllocation

    ids = list(payment_ids)
    if not ids:
        return {}

    alloc = {
        r["payment_id"]: int(r["t"] or 0)
        for r in PaymentAllocation.objects.filter(payment_id__in=ids)
        .values("payment_id").annotate(t=Sum("amount_sar"))
    }
    return {
        pk: max(0, int(amount_sar) - alloc.get(pk, 0) - int(deposited))
        for pk, amount_sar, deposited in PaymentRecord.objects.filter(pk__in=ids)
        .values_list("pk", "amount_sar", "deposited_sar")
    }


def invoice_paid_map(invoice_ids):
    """{invoice_id: paid_sar} — bentuk bulk invoice_paid_sar, satu query."""
    return {
        r["invoice_id"]: (r["c"] or 0) - (r["d"] or 0)
        for r in _settling(invoice_id__in=invoice_ids)
        .values("invoice_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }


def invoice_paid_map_before(invoice_ids, before_date):
    """{invoice_id: paid_sar} dihitung hanya dari baris jurnal dengan
    `entry_date < before_date` — untuk "outstanding per akhir bulan" pada
    dashboard (pengganti sum legacy `Payment.amount_sar`)."""
    return {
        r["invoice_id"]: (r["c"] or 0) - (r["d"] or 0)
        for r in _settling(invoice_id__in=invoice_ids)
        .filter(journal_entry__entry_date__lt=before_date)
        .values("invoice_id").annotate(d=Sum("debit"), c=Sum("credit"))
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
        .prefetch_related('allocations__invoice_line__confirmation_letter')
        .order_by('payment_date', 'pk')
    )

    rows = []
    for pr in prs:
        refs = []
        svc_nos = []
        for a in pr.allocations.all():
            if a.reservation_id and a.reservation and a.reservation.reservation_number not in refs:
                refs.append(a.reservation.reservation_number)
            if a.service_item_id and a.service_item and a.service_item.service_number not in svc_nos:
                svc_nos.append(a.service_item.service_number)
        rows.append({
            'pk': pr.pk,
            'status': pr.status,
            'unallocated_sar': pr.amount_sar - sum(a.amount_sar for a in pr.allocations.all()),
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


def _invoice_scoped(invoice_ids):
    qs = JournalLine.objects.all()
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return qs


def total_charged(invoice_ids=None):
    """Total tagihan bersih (charge − nota kredit, tanpa yang sudah di-void)
    untuk sekumpulan invoice."""
    return _net(_invoice_scoped(invoice_ids).filter(account_id=coa.AR).filter(_BILLING_Q))


def paid_into(account_code, invoice_ids=None):
    """Total kas yang masuk ke akun ini dari pembayaran invoice-invoice ini."""
    return _invoice_scoped(invoice_ids).filter(
        _in_accounts(account_code), debit__gt=0,
        journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
    ).aggregate(d=Sum("debit"))["d"] or 0


def mengendap(invoice_ids=None):
    """Kas Surabaya bersih untuk invoice-invoice ini (bisa negatif)."""
    return _net(_invoice_scoped(invoice_ids).filter(_in_accounts(coa.CASH_SBY)))


# ── Client ─────────────────────────────────────────────────────

def reservation_paid_map(invoice_id):
    """{baris hotel (reservasi): paid_sar} — kredit bersih Piutang per
    reservasi (payment credit - reversal debit) utk invoice."""
    rows = (
        _settling(invoice_id=invoice_id, invoice_line__kind=_HOTEL)
        .values("invoice_line_id").annotate(d=Sum("debit"), c=Sum("credit"))
    )
    return {r["invoice_line_id"]: (r["c"] or 0) - (r["d"] or 0) for r in rows}


def line_settled_sar(line_id):
    """Uang yang sudah melunasi satu baris invoice (kredit bersih Piutang di
    luar charge dan nota kredit)."""
    a = _settling(invoice_line_id=line_id).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["c"] or 0) - (a["d"] or 0)


def line_last_settled_date(line_id):
    """Tanggal pembayaran terakhir pada satu baris invoice (None bila belum ada)."""
    from django.db.models import Max
    return _settling(invoice_line_id=line_id).filter(credit__gt=0).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    ).aggregate(d=Max("journal_entry__entry_date"))["d"]


def cl_paid_sar_map(letters):
    """Bulk ConfirmationLetter.paid_sar: {cl_pk: paid_sar} dari jurnal.

    Baris jurnal pembayaran membawa dimensi baris invoice hotel, dan baris itu
    menunjuk CL-nya. Paid = kredit bersih Piutang (payment - reversal) pada
    semua baris invoice milik CL itu — konsisten dengan `reservation_paid_map`."""
    if not letters:
        return {}
    rows = (
        _settling(invoice_line__confirmation_letter_id__in=[cl.pk for cl in letters])
        .values("invoice_line__confirmation_letter_id")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    by_cl = {
        r["invoice_line__confirmation_letter_id"]: (r["c"] or 0) - (r["d"] or 0)
        for r in rows
    }
    return {cl.pk: by_cl.get(cl.pk, 0) for cl in letters}


def client_receivable(client_id):
    """Piutang client (positif = client berutang ke kita)."""
    return _net(JournalLine.objects.filter(client_id=client_id, account_id=coa.AR))


def client_wallet_map(client_ids):
    """{client_id: saldo piutang} — sama dengan client_receivable() tapi untuk
    banyak client dalam satu aggregate query (dipakai client_list agar tidak
    N+1 query per baris)."""
    rows = (
        JournalLine.objects.filter(client_id__in=client_ids, account_id=coa.AR)
        .values("client_id")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    return {r["client_id"]: (r["d"] or 0) - (r["c"] or 0) for r in rows}


def client_billed_sar(client_id):
    """Total ditagih ke client = tagihan bersih (charge − nota kredit)."""
    return _net(_billing(client_id=client_id))


def client_paid_sar(client_id):
    """Total kas yang masuk dari client = debit kas dari entry payment yang
    masih hidup (from-credit payment tidak menyentuh kas, jadi tidak
    dobel-hitung)."""
    return _net(
        JournalLine.objects.filter(
            _in_accounts(*coa.CASH_ROOTS),
            client_id=client_id,
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


def total_client_credit_balance():
    """Σ client_credit_balance untuk semua client, satu aggregate query."""
    a = JournalLine.objects.filter(
        client_id__isnull=False, account_id=coa.CUST_CREDIT,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["c"] or 0) - (a["d"] or 0)


def client_reservation_ids(client_id):
    """Set reservasi milik client dari dimensi baris jurnal yang masih hidup.

    Pengganti pembacaan Charge (tabel legacy, tidak lagi ditulis oleh alur
    billing sejak jurnal jadi system of record): reservasi seorang client
    adalah baris hotel yang pernah muncul pada baris jurnal ber-dimensi
    `client` yang bersangkutan."""
    return set(
        JournalLine.objects.filter(client_id=client_id, invoice_line__kind=_HOTEL)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .values_list("invoice_line_id", flat=True)
    )


def client_statement(client_id, *, date_from=None, date_to=None, as_of=None):
    """Baris jurnal ber-dimensi client, urut kronologis, dengan running
    balance (debit - credit; positif = client berutang)."""
    qs = _scoped(
        JournalLine.objects.filter(
            client_id=client_id, account_id__in=[coa.AR, coa.CUST_CREDIT],
        ).select_related("journal_entry", "account", "invoice", "invoice_line__confirmation_letter__hotel"),
        as_of=as_of,
    ).order_by("journal_entry__entry_date", "journal_entry__created_at", "line_no")
    if date_from:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)

    rows, balance = [], 0
    reversed_ids = set(_reversed_entry_ids())
    for ln in qs:
        e = ln.journal_entry
        res = ln.invoice_line if ln.invoice_line_id and ln.invoice_line.kind == _HOTEL else None
        balance += ln.debit - ln.credit
        rows.append({
            "date": e.entry_date,
            "entry_number": e.entry_number,
            "entry_type": e.entry_type,
            "type": "debit" if ln.debit else "credit",
            "description": e.description,
            "account": ln.account_id,
            "account_name": ln.account.name,
            "invoice_number": ln.invoice.invoice_number if ln.invoice_id else None,
            "reservation_id": res.pk if res else None,
            "reservation_number": res.reservation_number if res else None,
            "hotel": res.hotel if res else None,
            "check_in": res.check_in if res else None,
            "debit": ln.debit,
            "credit": ln.credit,
            "balance": balance,
            # Pasangan batal: entry yang sudah di-reverse DAN entry reversal-nya.
            # Keduanya tetap tampil di ledger ini (riwayat tidak boleh dihapus),
            # tapi rollup harus bisa membuang pasangan itu karena net-nya nol.
            "is_voided": e.is_reversal or e.pk in reversed_ids,
        })
    return {
        "rows": rows,
        "closing_balance": balance,
        "total_debit": sum(r["debit"] for r in rows),
        "total_credit": sum(r["credit"] for r in rows),
    }


def client_statement_with_opening(client_id, *, date_from=None, date_to=None, as_of=None):
    """client_statement() + saldo awal yang benar untuk periode yang mulai di
    tengah riwayat (bukan reset ke nol). Konsisten dengan versi legacy."""
    from datetime import timedelta
    opening_balance = 0
    if date_from:
        prior = client_statement(
            client_id, date_to=date_from - timedelta(days=1), as_of=as_of,
        )
        opening_balance = prior["closing_balance"]

    st = client_statement(
        client_id, date_from=date_from, date_to=date_to, as_of=as_of,
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


def client_statement_by_reservation(
    client_id, *, date_from=None, date_to=None, as_of=None,
):
    """Statement open-item: baris jurnal client di-rollup jadi satu baris per
    reservasi (Tagihan / Terbayar / Sisa), bukan satu baris per transaksi.

    Baris tanpa dimensi reservasi dipisah dua arah, karena arahnya artinya
    berlawanan dan tidak boleh dijumlah diam-diam:
      - `unallocated_credits` — uang MASUK yang tidak melekat reservasi
        (payment yang belum dipecah alokasinya, refund keluar dari titipan).
        Ini saldo client's di tangan kita.
      - `unallocated_debits` — tagihan yang TIDAK punya reservasi (service item
        pada invoice servis, penalty pembatalan, adjustment). Ini piutang, bukan
        setoran, dan tidak pernah jadi titipan client.
    Pasangan reversal (entry yang dibatalkan + entry reversal-nya) dibuang dari
    semua bucket. Net-nya nol, jadi `unallocated` dan tiap `balance` reservasi
    tetap sama; yang bersih cuma `billed`/`paid` — tanpa itu "Total Invoiced"
    di PDF ikut menghitung charge/payment yang sudah dibatalkan, dan tiap
    pembatalan payment menambah 2x lipatnya ke salah satu sisi.
    `unallocated` tetap disediakan sebagai net-nya (debits - credits) supaya
    invarian dan pemanggil lama tidak berubah.

    Invarian: opening_balance + Σ(reservasi.balance) + unallocated ==
    closing_balance — sama persis dengan versi balance-forward. Di-assert.
    """
    from datetime import date

    st = client_statement_with_opening(
        client_id, date_from=date_from, date_to=date_to, as_of=as_of,
    )

    groups = {}
    unallocated_debits = 0
    unallocated_credits = 0
    for r in st["rows"]:
        if r["is_voided"]:
            # Pasangan batal: dibuang dari SEMUA bucket. Net-nya nol, jadi
            # `unallocated` dan tiap `reservasi.balance` tidak berubah —
            # yang berubah hanya `billed`/`paid`, supaya angka "Total Invoiced"
            # di PDF tidak ikut menghitung charge/payment yang sudah dibatalkan.
            continue
        rid = r["reservation_id"]
        if rid is None:
            unallocated_debits += r["debit"]
            unallocated_credits += r["credit"]
            continue
        g = groups.get(rid)
        if g is None:
            g = groups[rid] = {
                "reservation_id": rid,
                "reservation_number": r["reservation_number"],
                "hotel": r["hotel"],
                "check_in": r["check_in"],
                "billed": 0,
                "paid": 0,
            }
        g["billed"] += r["debit"]
        g["paid"] += r["credit"]

    unallocated = unallocated_debits - unallocated_credits

    reservations = []
    for g in groups.values():
        g["balance"] = g["billed"] - g["paid"]
        g["settled"] = g["balance"] <= 0
        reservations.append(g)

    # Outstanding dulu (check_in naik), lunas di bawah.
    reservations.sort(
        key=lambda g: (g["settled"], g["check_in"] or date.max, g["reservation_number"] or "")
    )

    assert (
        st["opening_balance"]
        + sum(g["balance"] for g in reservations)
        + unallocated
        == st["closing_balance"]
    ), "by-reservation rollup tidak rekonsiliasi dengan balance-forward"

    return {
        "opening_balance": st["opening_balance"],
        "closing_balance": st["closing_balance"],
        "total_debit": st["total_debit"],
        "total_credit": st["total_credit"],
        "unallocated": unallocated,
        "unallocated_debits": unallocated_debits,
        "unallocated_credits": unallocated_credits,
        "reservations": reservations,
        "aging": client_aging(client_id, as_of=as_of),
    }


def client_aging(client_id, *, as_of=None):
    """Aging summary per invoice — berapa lama piutang belum dibayar.

    Returns {buckets: {0_30, 31_60, 61_90, 90_plus}, total, invoices: [...]}."""
    from datetime import date as _date

    today = as_of.date() if as_of else _date.today()

    # Net AR lines per invoice (charge - payment/reversal)
    ar_lines = _scoped(_ar_qs(client_id=client_id), as_of=as_of)
    invoice_nets = (
        ar_lines
        .values("invoice_id")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )

    # Fetch invoices with due_date
    from ..models.invoice import Invoice
    inv_map = {
        inv["id"]: inv
        for inv in Invoice.objects.filter(
            id__in=[r["invoice_id"] for r in invoice_nets if r["invoice_id"]]
        ).values("id", "invoice_number", "due_date", "issued_date")
    }

    buckets = {"0_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0}
    total = 0
    invoices = []

    for row in invoice_nets:
        net = (row["d"] or 0) - (row["c"] or 0)
        if net <= 0:
            continue  # fully paid or credit
        inv = inv_map.get(row["invoice_id"])
        if not inv:
            continue

        due = inv.get("due_date") or inv.get("issued_date")
        if due:
            age_days = (today - due).days
        else:
            age_days = 0

        if age_days <= 30:
            buckets["0_30"] += net
        elif age_days <= 60:
            buckets["31_60"] += net
        elif age_days <= 90:
            buckets["61_90"] += net
        else:
            buckets["90_plus"] += net

        total += net
        invoices.append({
            "invoice_number": inv["invoice_number"],
            "amount": net,
            "due_date": inv["due_date"].isoformat() if inv.get("due_date") else None,
            "age_days": max(age_days, 0),
        })

    invoices.sort(key=lambda x: -x["age_days"])
    return {"buckets": buckets, "total": total, "invoices": invoices}


AGING_BUCKETS = ("current", "1_30", "31_60", "61_90", "90_plus")


def _aging_bucket(days_overdue):
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "90_plus"


def ar_aging(*, as_of=None):
    """Aging piutang semua client per tanggal `as_of` (date; default hari ini).

    Sisa per invoice = net baris Piutang dengan entry_date <= as_of (charge −
    pembayaran − nota kredit ± reversal), dikelompokkan menurut hari lewat
    jatuh tempo (due_date, atau issued_date bila kosong). Invoice yang sudah
    lunas/lebih bayar tidak ikut. Baris Piutang tanpa invoice dijumlahkan ke
    'current' klien tersebut.

    Returns {as_of, buckets: {...}, total, clients: [{client_id, name, buckets,
    total, oldest_days, invoices: [...]}]} — clients diurutkan dari total
    terbesar."""
    from datetime import date as _date
    from ..models.invoice import Invoice

    as_of = as_of or _date.today()
    nets = (
        _ar_qs(journal_entry__entry_date__lte=as_of, client_id__isnull=False)
        .values("client_id", "invoice_id")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    rows = [(r["client_id"], r["invoice_id"], (r["d"] or 0) - (r["c"] or 0)) for r in nets]
    inv_map = {
        i["id"]: i for i in Invoice.objects.filter(
            id__in={inv for _c, inv, _n in rows if inv},
        ).values("id", "invoice_number", "issued_date", "due_date")
    }
    names = dict(Client.objects.filter(id__in={c for c, _i, _n in rows}).values_list("id", "name"))

    clients = {}
    for client_id, invoice_id, net in rows:
        if net == 0 or (invoice_id and net < 0):
            continue
        entry = clients.setdefault(client_id, {
            "client_id": client_id, "name": names.get(client_id, "—"),
            "buckets": dict.fromkeys(AGING_BUCKETS, 0), "total": 0, "oldest_days": 0, "invoices": [],
        })
        inv = inv_map.get(invoice_id)
        due = inv and (inv["due_date"] or inv["issued_date"])
        days = (as_of - due).days if due else 0
        bucket = _aging_bucket(days)
        entry["buckets"][bucket] += net
        entry["total"] += net
        if inv:
            entry["oldest_days"] = max(entry["oldest_days"], days)
            entry["invoices"].append({
                "id": inv["id"], "invoice_number": inv["invoice_number"],
                "due_date": inv["due_date"].isoformat() if inv["due_date"] else None,
                "days_overdue": max(days, 0), "bucket": bucket, "amount": net,
            })

    out = [c for c in clients.values() if c["total"] > 0]
    for c in out:
        c["invoices"].sort(key=lambda i: -i["days_overdue"])
    out.sort(key=lambda c: (-c["total"], c["name"]))
    buckets = {b: sum(c["buckets"][b] for c in out) for b in AGING_BUCKETS}
    return {"as_of": as_of.isoformat(), "buckets": buckets, "total": sum(buckets.values()), "clients": out}


def open_items(client_id, *, date_to=None, as_of=None):
    """Open Item mode — daftar invoice yang belum lunas per client.

    Satu baris per invoice: nomor, tanggal terbit, jatuh tempo, jumlah tagihan,
    jumlah dibayar, dan sisa yang masih terbuka. Hanya invoice dengan
    remaining > 0 yang tampil. Konsisten dengan balance-forward (angka dari
    JournalLine), jadi kedua mode selalu reconciled."""
    from datetime import date as _date

    today = _date.today()

    ar_net = _scoped(_ar_qs(client_id=client_id), as_of=as_of).values(
        "invoice_id",
    ).annotate(d=Sum("debit"), c=Sum("credit"))

    charged = _scoped(_billing(client_id=client_id), as_of=as_of).values(
        "invoice_id",
    ).annotate(d=Sum("debit"), c=Sum("credit"))

    net_map = {
        r["invoice_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in ar_net if r["invoice_id"]
    }
    charged_map = {r["invoice_id"]: (r["d"] or 0) - (r["c"] or 0) for r in charged if r["invoice_id"]}

    inv_ids = set(net_map) | set(charged_map)
    from ..models.invoice import Invoice
    inv_map = {
        inv["id"]: inv
        for inv in Invoice.objects.filter(id__in=inv_ids).values(
            "id", "invoice_number", "invoice_type", "issued_date", "due_date",
        )
    }

    rows = []
    for inv_id in sorted(inv_ids):
        remaining = net_map.get(inv_id, 0)
        if remaining <= 0:
            continue
        inv = inv_map.get(inv_id)
        if not inv:
            continue
        billed = charged_map.get(inv_id, 0)
        paid = max(0, billed - remaining) if billed else 0
        due = inv.get("due_date")
        rows.append({
            "invoice_number": inv["invoice_number"],
            "invoice_type": inv["invoice_type"],
            "issued_date": inv["issued_date"].isoformat() if inv.get("issued_date") else None,
            "due_date": due.isoformat() if due else None,
            "billed": billed,
            "paid": paid,
            "remaining": remaining,
            "overdue": bool(due and (today - due).days > 0),
        })

    rows.sort(key=lambda x: (x["overdue"], x["due_date"] or "9999-12-31"))
    total_remaining = sum(r["remaining"] for r in rows)
    return {"rows": rows, "total_remaining": total_remaining}


# ── Kas ────────────────────────────────────────────────────────

def account_balance(account_code, *, as_of=None):
    return _net(_scoped(
        JournalLine.objects.filter(account_id=account_code), as_of=as_of,
    ))


def cash_balance(root_code, *, as_of=None):
    """Saldo kas cabang dalam SAR: akun induk + akun anak per mata uang."""
    return _net(_scoped(JournalLine.objects.filter(_in_accounts(root_code)), as_of=as_of))


def kas_surabaya():
    return cash_balance(coa.CASH_SBY)


def kas_jakarta():
    return cash_balance(coa.CASH_JKT)


def kas_pusat():
    return cash_balance(coa.CASH_PUSAT)


def transit():
    return account_balance(coa.TRANSIT)


def money_accounts_overview(branch=None, include_inactive=False):
    """Daftar rekening bank + kas dengan book_balance masing-masing.
    Data-layer untuk halaman saldo bank (v2.0 §78). `include_inactive`
    ikut menampilkan rekening bank nonaktif (halaman kelola rekening)."""
    from ..models.bank import BankAccount, CashAccount

    bank_qs = BankAccount.objects.all() if include_inactive else BankAccount.objects.filter(is_active=True)
    bank_qs = bank_qs.select_related('branch')
    cash_qs = CashAccount.objects.filter(is_active=True).select_related('branch')
    if branch:
        bank_qs = bank_qs.filter(branch_id=branch)
        cash_qs = cash_qs.filter(branch_id=branch)
    # book_balance is the ledger's balance (journal is SAR-only). Several money
    # accounts may post to one ledger (e.g. a bank account on the branch cash
    # ledger); flag those so the page doesn't pass a shared figure off as one
    # account's own.
    from collections import Counter
    from ..models.bank import MoneyAccount
    ledger_use = Counter(MoneyAccount.objects.values_list('ledger_account_id', flat=True))
    rows = []
    for kind, qs in (('bank', bank_qs), ('cash', cash_qs)):
        for acc in qs:
            rows.append({
                'id': acc.pk, 'kind': kind,
                'name': f'{acc.bank_name} ({acc.currency})' if kind == 'bank' else str(acc),
                'ledger_account': acc.ledger_account_id,
                'ledger_shared': ledger_use[acc.ledger_account_id] > 1,
                'branch': acc.branch_id, 'currency': acc.currency,
                'book_balance': acc.book_balance,
                'is_active': acc.is_active,
                'show_on_invoice': acc.show_on_invoice,
                'account_identifier': acc.account_identifier,
            })
    return rows


def account_transactions(kind, account_id, *, date_from=None, date_to=None):
    """Riwayat BankTransaction satu rekening (bank/kas), dengan saldo berjalan.

    Saldo berjalan di sini murni jumlah kumulatif BankTransaction rekening
    ini — BUKAN book_balance (proyeksi JournalLine); dua-duanya bisa berbeda
    untuk event lama yang belum lewat titik `record_bank_transaction`
    (mis. payment legacy `received_in`-only, lihat bank_transaction.py)."""
    from ..models.bank import BankAccount, CashAccount
    from ..models.bank_transaction import BankTransaction

    account_model = BankAccount if kind == 'bank' else CashAccount
    account = account_model.objects.filter(pk=account_id).first()
    if account is None:
        return None

    qs = (
        BankTransaction.objects.filter(account_id=account.pk)
        .exclude(status=BankTransaction.STATUS_VOIDED)
        .prefetch_related('statement_lines').order_by('transaction_date', 'id')
    )
    if date_from:
        qs = qs.filter(transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)

    running = 0
    rows = []
    for tx in qs:
        running += tx.amount_sar if tx.direction == BankTransaction.DIRECTION_IN else -tx.amount_sar
        rows.append({
            'id': tx.pk,
            'transaction_date': tx.transaction_date.isoformat(),
            'direction': tx.direction,
            'amount_sar': tx.amount_sar,
            'running_balance_sar': running,
            'source_type': tx.source_type,
            'source_id': tx.source_id,
            'reference': tx.reference,
            'status': tx.status,
            'matched': tx.statement_lines.exists(),
        })
    rows.reverse()
    return {'account': {'id': account.pk, 'kind': kind, 'name': str(account), 'currency': account.currency}, 'rows': rows}


def ap_balance():
    """Saldo Utang Usaha (positif = KONOZ berutang ke vendor)."""
    return -account_balance(coa.AP)


def branch_expense_sar(branch_code, *, date_from=None, date_to=None):
    """Total beban (net debit akun 5xxx) untuk satu cabang pada rentang tanggal."""
    qs = JournalLine.objects.filter(
        branch_id=branch_code, account__type='expense',
    )
    if date_from:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)
    return _net(qs)


def service_margins(*, branch=None, date_from=None, date_to=None):
    """Margin per baris Services (spec §5): pendapatan SAR yang ditagih (charge
    hidup − nota kredit, dari jurnal) dibanding biaya vendornya (ExpenseLine
    yang diposting dan menunjuk baris itu). Filter: cabang penjual dan tanggal
    terbit invoice."""
    from ..models.expense import Expense, ExpenseLine
    from ..models.invoice import Invoice, InvoiceLine

    lines = (
        InvoiceLine.objects.filter(kind=InvoiceLine.KIND_SERVICE, voided_at__isnull=True)
        .exclude(invoice__status=Invoice.STATUS_VOID)
        .select_related("invoice__client")
        .order_by("-invoice__issued_date", "invoice_id", "line_no")
    )
    if branch:
        lines = lines.filter(invoice__branch_id=branch)
    if date_from:
        lines = lines.filter(invoice__issued_date__gte=date_from)
    if date_to:
        lines = lines.filter(invoice__issued_date__lte=date_to)
    lines = list(lines)
    ids = [l.pk for l in lines]

    revenue = {
        r["invoice_line_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _billing(invoice_line_id__in=ids).values("invoice_line_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    cost = {
        r["service_line_id"]: r["t"] or 0
        for r in ExpenseLine.objects.filter(service_line_id__in=ids, expense__status=Expense.STATUS_POSTED)
        .values("service_line_id").annotate(t=Sum("amount_sar"))
    }

    rows = []
    for l in lines:
        rev, cst = int(revenue.get(l.pk, 0)), int(cost.get(l.pk, 0))
        rows.append({
            "line_id": l.pk,
            "invoice_id": l.invoice_id,
            "invoice_number": l.invoice.invoice_number,
            "branch": l.invoice.branch_id,
            "client": l.invoice.customer_name,
            "description": l.description,
            "quantity": l.quantity,
            "revenue_sar": rev,
            "cost_sar": cst,
            "margin_sar": rev - cst,
            "margin_pct": round((rev - cst) * 100 / rev, 1) if rev else None,
            "has_cost": l.pk in cost,
        })
    total_rev = sum(r["revenue_sar"] for r in rows)
    total_cost = sum(r["cost_sar"] for r in rows)
    return {
        "rows": rows,
        "revenue_sar": total_rev,
        "cost_sar": total_cost,
        "margin_sar": total_rev - total_cost,
        "without_cost": sum(1 for r in rows if not r["has_cost"]),
    }


def vendor_payables():
    """Utang per vendor (spec §5): Σ beban diposting − Σ pembayarannya."""
    from ..models.expense import Expense, ExpenseLine, ExpensePayment
    from ..models.vendor import Vendor

    billed = {
        r["expense__vendor_id"]: r["t"] or 0
        for r in ExpenseLine.objects.filter(expense__status=Expense.STATUS_POSTED)
        .values("expense__vendor_id").annotate(t=Sum("amount_sar"))
    }
    paid = {
        r["expense__vendor_id"]: r["t"] or 0
        for r in ExpensePayment.objects.filter(
            status=ExpensePayment.STATUS_PAID, expense__status=Expense.STATUS_POSTED,
        ).values("expense__vendor_id").annotate(t=Sum("amount_sar"))
    }
    names = dict(Vendor.objects.filter(pk__in=[k for k in billed if k]).values_list("pk", "name"))
    rows = [
        {
            "vendor_id": vid,
            "vendor": names.get(vid) or "(no vendor)",
            "billed_sar": int(t),
            "paid_sar": int(paid.get(vid, 0)),
            "outstanding_sar": int(t) - int(paid.get(vid, 0)),
        }
        for vid, t in billed.items()
    ]
    rows.sort(key=lambda r: (-r["outstanding_sar"], r["vendor"]))
    return rows


def mengendap_per_reservation(line_id):
    """Kas Surabaya yang menempel pada reservasi ini (belum diremit)."""
    return _net(JournalLine.objects.filter(_in_accounts(coa.CASH_SBY), invoice_line_id=line_id))


def total_allocated():
    """Total kas yang sudah 'dipakai' mengurangi piutang (credit bersih Piutang,
    selain charge) — analog total Allocation legacy. = ditagih - sisa AR net."""
    return -_net(_settling())


def surplus_pusat():
    return kas_pusat() + selisih_kurs() - total_allocated()


def kewajiban_kirim_sby():
    """Semua kas Surabaya idle wajib diremit ke pusat. Pertahankan makna
    legacy: -surplus_pusat (bukan sekadar kas_surabaya), supaya dashboard
    remittance tidak kehilangan pasangan KPI kewajiban_kirim + saldo_dana."""
    return -surplus_pusat()


# ── Remittance ─────────────────────────────────────────────────

def remittance_sent_sar(remittance_id):
    """Total SAR yang dikirim utk remittance ini = debit TRANSIT dari entry
    send yang masih hidup. Entry receive meng-credit TRANSIT (bukan debit),
    jadi Sum(debit) hanya mengunci sisi kirim -- setelah dua debit non-kirim
    disingkirkan (_sent_lines)."""
    return (
        _sent_lines(remittance_id=remittance_id)
        .aggregate(d=Sum("debit"))["d"] or 0
    )


def _sent_lines(**f):
    """Baris TRANSIT sisi kirim yang masih hidup. Dikecualikan:
    - entry reversal: membalik terima/settlement/selisih biaya menghasilkan
      debit TRANSIT, padahal itu bukan uang yang dikirim;
    - RemittanceDiff: laba kurs dibukukan Dr TRANSIT / Cr pendapatan."""
    return (
        JournalLine.objects.filter(account_id=coa.TRANSIT, **f)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .exclude(journal_entry__reverses__isnull=False)
        .exclude(journal_entry__entry_type=JournalEntry.TYPE_REMITTANCE_DIFF)
    )


def remittance_sent_map(remittance_ids):
    """{remittance_id: total SAR terkirim} — versi bulk remittance_sent_sar()
    untuk daftar (dashboard/rekap), satu aggregate query, bukan N+1."""
    if not remittance_ids:
        return {}
    rows = (
        _sent_lines(remittance_id__in=remittance_ids)
        .values("remittance_id").annotate(d=Sum("debit"))
    )
    return {r["remittance_id"]: r["d"] or 0 for r in rows}


def remittance_has_live_entries(remittance_id):
    """True kalau remittance ini punya baris jurnal REMITTANCE yang belum
    di-reverse — dipakai guard hapus (dokumen keuangan tak boleh hilang)."""
    return (
        JournalLine.objects.filter(
            remittance_id=remittance_id,
            journal_entry__entry_type__in=REMITTANCE_TYPES,
            journal_entry__reverses__isnull=True,
        ).exclude(journal_entry_id__in=_reversed_entry_ids()).exists()
    )


def selisih_kurs():
    """Saldo kliring selisih kurs (FX_CLEARING)."""
    return _net(JournalLine.objects.filter(account_id=coa.FX_CLEARING))


def piutang(line_id):
    """Sisa piutang satu baris invoice = net baris Piutang ber-dimensi baris
    itu (charge debit - payment credit) yang masih hidup."""
    return _net(_ar_qs(invoice_line_id=line_id).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    ))


def reservation_cash_breakdown():
    """Bulk per-reservation cash breakdown untuk dashboard remittance:
    {reservation_id: {terbayar_sby, terbayar_jkt, terbayar_direct,
    sudah_dikirim, mengendap, mengendap_jkt}} — derivasi dari JournalLine
    (payment legs ke kas + remittance send credit kas cabang per reservasi)."""
    from collections import defaultdict
    qs = JournalLine.objects.filter(invoice_line__kind=_HOTEL).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    )

    pay = (qs.filter(journal_entry__entry_type=JournalEntry.TYPE_PAYMENT, debit__gt=0)
           .values("invoice_line_id", "account_id", "account__parent_id").annotate(d=Sum("debit")))
    # Uang reservasi yang sudah sampai di Pusat: alokasi penerimaan transfer.
    send = (qs.filter(journal_entry__entry_type=JournalEntry.TYPE_ALLOCATE)
            .values("invoice_line_id", "account_id", "account__parent_id").annotate(c=Sum("credit")))

    out = defaultdict(lambda: {
        "terbayar_sby": 0, "terbayar_jkt": 0, "terbayar_direct": 0,
        "sent_from_sby": 0, "sent_from_jkt": 0,
    })
    for r in pay:
        rid, root = r["invoice_line_id"], _root(r["account_id"], r["account__parent_id"])
        if root == coa.CASH_SBY:
            out[rid]["terbayar_sby"] += r["d"]
        elif root == coa.CASH_JKT:
            out[rid]["terbayar_jkt"] += r["d"]
        elif root == coa.CASH_PUSAT:
            out[rid]["terbayar_direct"] += r["d"]
    for r in send:
        rid, root = r["invoice_line_id"], _root(r["account_id"], r["account__parent_id"])
        if root == coa.CASH_SBY:
            out[rid]["sent_from_sby"] += r["c"]
        elif root == coa.CASH_JKT:
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


def reservation_first_payment_date_map(reservation_numbers):
    """{reservation_number: tanggal pembayaran paling awal} dari baris jurnal
    kredit Piutang (bukan charge) — dipakai mengurutkan baris remittance sesuai
    kapan reservasi mulai dibayar."""
    if not reservation_numbers:
        return {}
    rows = (
        _settling(invoice_line__confirmation_letter__confirmation_number__in=list(reservation_numbers))
        .values("invoice_line__confirmation_letter__confirmation_number")
        .annotate(first=Min("journal_entry__entry_date"))
    )
    return {r["invoice_line__confirmation_letter__confirmation_number"]: r["first"] for r in rows}


def reservation_remittance_map(linked_numbers=None):
    """Riwayat remittance per reservasi (baca RemittanceLine, bukan jurnal):
    {reservation_number: [{rmt_id, rmt_number, date, status, amount_sar,
    received_date}]}. `received_date` terisi untuk alokasi penerimaan
    (RemittanceLine.settlement), None untuk baris yang dialokasikan saat kirim."""
    from collections import defaultdict
    from ..models.remittance import RemittanceLine
    qs = RemittanceLine.objects.select_related(
        "settlement__remittance", "invoice_line__confirmation_letter",
    ).order_by(
        "settlement__remittance__date", "settlement__remittance__created_at", "settlement__received_date", "pk",
    )
    if linked_numbers is not None:
        qs = qs.filter(invoice_line__confirmation_letter__confirmation_number__in=list(linked_numbers))
    result = defaultdict(list)
    for l in qs:
        result[l.linked_number].append({
            "rmt_id": l.remittance_id, "rmt_number": l.remittance.remittance_number,
            "date": l.remittance.date, "status": l.remittance.status,
            "amount_sar": int(l.amount_sar or 0),
            "received_date": l.settlement.received_date,
        })
    return result


def client_paid_map(client_ids):
    """{client_id: gross cash masuk dari client} — satu query agregat."""
    rows = (
        JournalLine.objects.filter(
            _in_accounts(*coa.CASH_ROOTS),
            client_id__in=client_ids,
            debit__gt=0, journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
        ).exclude(journal_entry_id__in=_reversed_entry_ids())
        .values("client_id").annotate(d=Sum("debit"))
    )
    return {r["client_id"]: r["d"] or 0 for r in rows}


def clients_overview():
    """Agregat bulk per-client untuk halaman daftar statement. Derivasinya
    konsisten dengan properti Client (billed/payable/credit) dari jurnal."""
    clients = {c.id: c for c in Client.objects.all()}
    cids = list(clients)

    billed = {
        r["client_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _billing(client_id__in=cids)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
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
        "name": clients[cid].name,
        "tagihan": billed.get(cid, 0),
        "terbayar": paid.get(cid, 0),
        "allocated": billed.get(cid, 0) - receivable.get(cid, 0),
        "piutang": receivable.get(cid, 0),
        "saldo_dana": credit.get(cid, 0),
    } for cid in cids]
    overview.sort(key=lambda r: (-r["piutang"], r["client_id"]))
    return overview


# ── Trial balance ──────────────────────────────────────────────

def trial_balance(*, date_from=None, date_to=None):
    qs = JournalLine.objects.all()
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
