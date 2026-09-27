"""Derivasi keuangan — baca JournalLine, satu-satunya sumber angka.

Pengganti hw/ledger.py. Views memanggil fungsi di sini, tidak pernah
Sum() tabel jurnal sendiri. Belum di-wire (Fase 6).
"""
from django.db.models import Min, Sum

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

    = amount_sar - sum(PaymentAllocation.amount_sar).

    Sebuah payment dianggap TERALOKASI penuh ke reservasi di dua cara:
    1. Punya baris PaymentAllocation -> sisa dihitung per baris.
    2. Tanpa baris PaymentAllocation tapi terikat LANGSUNG ke satu reservasi
       (payment.reservation_id terisi) -> dianggap penuh dialokasikan ke
       target tunggal itu (unallocated = 0).

    Hanya punya invoice_id (tanpa reservation/allocation) BUKAN tanda
    teralokasi: payment masih menunggu pemecahan alokasi per reservasi via
    reallocate, sehingga tetap dihitung sebagai unallocated.

    Berguna untuk menampilkan badge 'X SAR unallocated' di payment detail."""
    from ..models.payment import PaymentRecord
    try:
        pr = PaymentRecord.objects.get(pk=payment_id)
    except PaymentRecord.DoesNotExist:
        return 0
    alloc_sum = sum(int(a.amount_sar) for a in pr.allocations.all())
    if alloc_sum:
        return max(0, int(pr.amount_sar) - alloc_sum)
    if pr.reservation_id:
        return 0
    return int(pr.amount_sar)


def payment_unallocated_map(payment_ids):
    """{payment_id: unallocated_sar} — bentuk bulk dari payment_unallocated_sar.

    Dua query untuk N payment, bukan dua query PER payment. Aturannya persis
    sama dengan versi satuan: baris PaymentAllocation menang; tanpa baris tapi
    terikat langsung ke satu reservasi = teralokasi penuh; selain itu seluruh
    nilainya belum teralokasi.
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
    out = {}
    for pk, amount_sar, reservation_id in PaymentRecord.objects.filter(
        pk__in=ids,
    ).values_list("pk", "amount_sar", "reservation_id"):
        allocated = alloc.get(pk, 0)
        if allocated:
            out[pk] = max(0, int(amount_sar) - allocated)
        elif reservation_id:
            out[pk] = 0
        else:
            out[pk] = int(amount_sar)
    return out


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
    """Total ditagih (debit Piutang) untuk sekumpulan invoice."""
    return _invoice_scoped(invoice_ids).filter(
        account_id=coa.AR,
    ).aggregate(d=Sum("debit"))["d"] or 0


def paid_into(account_code, invoice_ids=None):
    """Total kas yang masuk ke akun ini dari pembayaran invoice-invoice ini."""
    return _invoice_scoped(invoice_ids).filter(
        account_id=account_code, debit__gt=0,
        journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
    ).aggregate(d=Sum("debit"))["d"] or 0


def mengendap(invoice_ids=None):
    """Kas Surabaya bersih untuk invoice-invoice ini (bisa negatif)."""
    return _net(_invoice_scoped(invoice_ids).filter(account_id=coa.CASH_SBY))


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
    pembayaran lewat `reservation.reservation_number == confirmation_number`.
    Paid = kredit bersih Piutang (payment - reversal) pada baris jurnal
    ber-dimensi reservasi itu — konsisten dengan `reservation_paid_map`."""
    if not letters:
        return {}
    numbers = {cl.confirmation_number for cl in letters}
    rows = (
        _ar_qs(reservation__reservation_number__in=numbers)
        .exclude(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .values("reservation__reservation_number")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    by_number = {
        r["reservation__reservation_number"]: (r["c"] or 0) - (r["d"] or 0)
        for r in rows
    }
    return {cl.pk: by_number.get(cl.confirmation_number, 0) for cl in letters}


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
    adalah yang pernah muncul ber-dimensi `reservation` pada baris jurnal
    ber-dimensi `client` yang bersangkutan."""
    return set(
        JournalLine.objects.exclude(reservation_id=None)
        .filter(client_id=client_id)
        .exclude(journal_entry_id__in=_reversed_entry_ids())
        .values_list("reservation_id", flat=True)
    )


def client_statement(client_id, *, date_from=None, date_to=None, as_of=None):
    """Baris jurnal ber-dimensi client, urut kronologis, dengan running
    balance (debit - credit; positif = client berutang)."""
    qs = _scoped(
        JournalLine.objects.filter(
            client_id=client_id, account_id__in=[coa.AR, coa.CUST_CREDIT],
        ).select_related("journal_entry", "account", "invoice", "reservation"),
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
            "reservation_id": ln.reservation_id,
            "reservation_number": ln.reservation.reservation_number if ln.reservation_id else None,
            "hotel": ln.reservation.hotel if ln.reservation_id else None,
            "check_in": ln.reservation.check_in if ln.reservation_id else None,
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

    charged = _scoped(_live_charges(client_id=client_id), as_of=as_of).values(
        "invoice_id",
    ).annotate(d=Sum("debit"))

    net_map = {
        r["invoice_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in ar_net if r["invoice_id"]
    }
    charged_map = {r["invoice_id"]: r["d"] or 0 for r in charged if r["invoice_id"]}

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


def kas_surabaya():
    return account_balance(coa.CASH_SBY)


def kas_jakarta():
    return account_balance(coa.CASH_JKT)


def kas_pusat():
    return account_balance(coa.CASH_PUSAT)


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
    ledger_use = Counter(
        list(BankAccount.objects.values_list('ledger_account_id', flat=True))
        + list(CashAccount.objects.values_list('ledger_account_id', flat=True))
    )
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
                'show_on_invoice': getattr(acc, 'show_on_invoice', False),
                'account_identifier': getattr(acc, 'account_identifier', ''),
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

    field = 'bank_account' if kind == 'bank' else 'cash_account'
    qs = BankTransaction.objects.filter(**{field: account_id}).prefetch_related('statement_lines').order_by('transaction_date', 'id')
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


def mengendap_per_reservation(reservation_id):
    """Kas Surabaya yang menempel pada reservasi ini (belum diremit)."""
    return _net(JournalLine.objects.filter(reservation_id=reservation_id, account_id=coa.CASH_SBY))


def total_allocated():
    """Total kas yang sudah 'dipakai' mengurangi piutang (credit bersih Piutang,
    selain charge) — analog total Allocation legacy. = ditagih - sisa AR net."""
    return total_charged() - _net(_ar_qs())


def surplus_pusat():
    return kas_pusat() + selisih_kurs() - total_allocated()


def _client_idr_payments_qs():
    from ..models.payment import PaymentRecord
    return PaymentRecord.objects.filter(
        currency='IDR',
        received_in__in=('sby', 'jkt'),
        status__in=PaymentRecord.EFFECTIVE_STATUSES,
    )


def rupiah_diterima_dari_klien():
    """Total rupiah (IDR asli) pembayaran klien yang masuk ke kas lokal
    (Surabaya/Jakarta). Angka analitik dari PaymentRecord.amount."""
    return int(_client_idr_payments_qs().aggregate(s=Sum('amount'))['s'] or 0)


def _kurs_rata_rata_klien():
    """Kurs IDR/SAR rata-rata tertimbang dari pembayaran klien (ΣIDR / ΣSAR).
    Dipakai untuk menaksir nilai rupiah remittance lama yang tidak menyimpan
    amount_idr/exchange_rate."""
    from decimal import Decimal
    agg = _client_idr_payments_qs().aggregate(idr=Sum('amount'), sar=Sum('amount_sar'))
    if not agg['idr'] or not agg['sar']:
        return None
    return Decimal(agg['idr']) / Decimal(agg['sar'])


def rupiah_mengendap_sby():
    """Rupiah dari klien yang masih mengendap di Surabaya — belum dikirim ke
    pusat. = Σ(pembayaran klien IDR) − Σ(rupiah yang sudah keluar via remittance).

    Rupiah keluar per remittance memakai amount_idr bila ada, lalu
    total_sar × exchange_rate, dan terakhir total_sar × kurs rata-rata klien
    untuk RMT lama yang tak menyimpan data transfer bank."""
    from decimal import Decimal
    from ..models.remittance import Remittance

    diterima = rupiah_diterima_dari_klien()
    avg_rate = _kurs_rata_rata_klien()

    dikirim = Decimal(0)
    for rem in Remittance.objects.all():
        if rem.amount_idr:
            dikirim += Decimal(rem.amount_idr)
            continue
        sent_sar = remittance_sent_sar(rem.id)
        if not sent_sar:
            continue
        rate = rem.exchange_rate or avg_rate
        if rate:
            dikirim += Decimal(sent_sar) * rate

    return int(Decimal(diterima) - dikirim)


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
        .exclude(journal_entry__is_reversal=True)
        .exclude(journal_entry__reference_type="RemittanceDiff")
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
            journal_entry__entry_type=JournalEntry.TYPE_REMITTANCE,
            journal_entry__is_reversal=False,
        ).exclude(journal_entry_id__in=_reversed_entry_ids()).exists()
    )


def selisih_kurs():
    """Saldo kliring selisih kurs (FX_CLEARING)."""
    return _net(JournalLine.objects.filter(account_id=coa.FX_CLEARING))


def piutang(reservation_id):
    """Sisa piutang satu reservasi = net baris Piutang ber-dimensi reservasi
    (charge debit - payment credit) yang masih hidup."""
    return _net(_ar_qs(reservation_id=reservation_id).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    ))


def reservation_cash_breakdown():
    """Bulk per-reservation cash breakdown untuk dashboard remittance:
    {reservation_id: {terbayar_sby, terbayar_jkt, terbayar_direct,
    sudah_dikirim, mengendap, mengendap_jkt}} — derivasi dari JournalLine
    (payment legs ke kas + remittance send credit kas cabang per reservasi)."""
    from collections import defaultdict
    qs = JournalLine.objects.exclude(reservation_id=None).exclude(
        journal_entry_id__in=_reversed_entry_ids(),
    )

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


def reservation_first_payment_date_map(reservation_numbers):
    """{reservation_number: tanggal pembayaran paling awal} dari baris jurnal
    kredit Piutang (bukan charge) — dipakai mengurutkan baris remittance sesuai
    kapan reservasi mulai dibayar."""
    if not reservation_numbers:
        return {}
    rows = (
        _ar_qs(reservation__reservation_number__in=list(reservation_numbers))
        .exclude(journal_entry__entry_type=JournalEntry.TYPE_CHARGE)
        .values("reservation__reservation_number")
        .annotate(first=Min("journal_entry__entry_date"))
    )
    return {r["reservation__reservation_number"]: r["first"] for r in rows}


def reservation_remittance_map(linked_numbers=None):
    """Riwayat remittance per reservasi (baca RemittanceLine, bukan jurnal):
    {reservation_number: [{rmt_id, rmt_number, date, status, amount_sar,
    received_date}]}. `received_date` terisi untuk alokasi penerimaan
    (RemittanceLine.settlement), None untuk baris yang dialokasikan saat kirim."""
    from collections import defaultdict
    from ..models.remittance import RemittanceLine
    qs = RemittanceLine.objects.select_related("remittance", "settlement").order_by(
        "remittance__date", "remittance__created_at", "settlement__received_date", "pk",
    )
    if linked_numbers is not None:
        qs = qs.filter(linked_number__in=linked_numbers)
    result = defaultdict(list)
    for l in qs:
        result[l.linked_number].append({
            "rmt_id": l.remittance_id, "rmt_number": l.remittance.remittance_number,
            "date": l.remittance.date, "status": l.remittance.status,
            "amount_sar": int(l.amount_sar or 0),
            "received_date": l.settlement.received_date if l.settlement_id else None,
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


def clients_overview():
    """Agregat bulk per-client untuk halaman daftar statement. Derivasinya
    konsisten dengan properti Client (billed/payable/credit) dari jurnal."""
    clients = {c.id: c for c in Client.objects.all()}
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
