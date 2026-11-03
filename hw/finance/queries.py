"""Derivasi keuangan — baca JournalLine, satu-satunya sumber angka.

Pengganti hw/ledger.py. Views memanggil fungsi di sini, tidak pernah
Sum() tabel jurnal sendiri.
"""
from django.db.models import Q, Sum
from django.utils import timezone

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
    from ..models.payment import PaymentAllocation, PaymentRecord

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


def payment_history_rows(invoice):
    """Riwayat pembayaran satu invoice untuk display — dari PaymentRecord,
    satu-satunya sumber truth pembayaran (finance page, form invoice, backfill
    semuanya menulis PaymentRecord; legacy `Payment` tidak lagi dibaca).

    Hanya status ber-efek-jurnal (PaymentRecord.EFFECTIVE_STATUSES) yang
    dikembalikan; reversal/rejected/pending disembunyikan. Semua konsumen
    (invoice detail, form edit, PDF) memakai fungsi ini supaya
    satu invoice tak pernah menampilkan angka dari dua sumber berbeda.
    """
    from ..models.payment import PaymentRecord

    prs = list(
        PaymentRecord.objects
        .filter(invoice=invoice, status__in=PaymentRecord.EFFECTIVE_STATUSES)
        .select_related('receiving_account__branch', 'confirmed_by')
        .prefetch_related('allocations__invoice_line__confirmation_letter')
        .order_by('payment_date', 'pk')
    )

    rows = []
    for pr in prs:
        refs = []
        for a in pr.allocations.all():
            if a.reservation_id and a.reservation and a.reservation.reservation_number not in refs:
                refs.append(a.reservation.reservation_number)
        received_in_display = ''
        try:
            received_in_display = pr.get_received_in_display()
        except Exception:
            if getattr(pr, 'receiving_account_id', None):
                try:
                    received_in_display = str(pr.receiving_account.branch)
                except Exception:
                    received_in_display = pr.receiving_branch_code or ''
        rows.append({
            'pk': pr.pk,
            'payment_id': pr.payment_number,
            'status': pr.status,
            'unallocated_sar': pr.amount_sar - sum(a.amount_sar for a in pr.allocations.all()),
            'allocations': [{
                'rsv': a.reservation.reservation_number if a.reservation_id and a.reservation else a.invoice_line.description,
                'amount_sar': a.amount_sar,
            } for a in sorted(pr.allocations.all(), key=lambda a: a.pk)],
            'ref': ', '.join(refs) or pr.reference or pr.payment_number,
            'payment_number': pr.payment_number,
            'payment_date': pr.payment_date,
            'method': pr.method,
            'received_in': getattr(pr, 'receiving_branch_code', None),
            'received_in_display': received_in_display,
            'receiving_office': received_in_display,
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


def reservation_paid_maps(invoice_ids):
    """Bulk reservation_paid_map: {invoice_id: {baris hotel: paid_sar}}."""
    out = {pk: {} for pk in invoice_ids}
    rows = (
        _settling(invoice_id__in=invoice_ids, invoice_line__kind=_HOTEL)
        .values("invoice_id", "invoice_line_id").annotate(d=Sum("debit"), c=Sum("credit"))
    )
    for r in rows:
        out[r["invoice_id"]][r["invoice_line_id"]] = (r["c"] or 0) - (r["d"] or 0)
    return out


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


def client_credit_balances(client_ids):
    """{client id: deposit held} for several clients, one query."""
    rows = (JournalLine.objects.filter(client_id__in=list(client_ids), account_id=coa.CUST_CREDIT)
            .values("client_id").annotate(d=Sum("debit"), c=Sum("credit")))
    return {r["client_id"]: (r["c"] or 0) - (r["d"] or 0) for r in rows}


def total_client_credit_balance():
    """Σ client_credit_balance untuk semua client, satu aggregate query."""
    a = JournalLine.objects.filter(
        client_id__isnull=False, account_id=coa.CUST_CREDIT,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (a["c"] or 0) - (a["d"] or 0)


def client_statement_qs(client_id, *, date_from=None, date_to=None, as_of=None):
    """Queryset baris Piutang + titipan milik satu client, kronologis.

    Dipisah dari client_statement() supaya view bisa menghitung jumlah baris
    (untuk Paginator) tanpa membangun dict untuk seluruh riwayat lebih dulu.
    """
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
    return qs


def client_statement(
    client_id, *, date_from=None, date_to=None, as_of=None, offset=0, limit=None,
):
    """Baris jurnal ber-dimensi client, urut kronologis, dengan running
    balance (debit - credit; positif = client berutang).

    `offset`/`limit` memotong baris yang dikembalikan untuk paginasi, tapi
    TIDAK memotong perhitungan: running balance, total_debit/total_credit dan
    closing_balance dihitung dari seluruh baris periode. Kalau tidak, saldo
    baris pertama halaman 2 akan salah (mulai dari nol, bukan saldo sebenarnya
    sebelum halaman itu). `count` selalu jumlah baris seluruh periode.
    """
    qs = client_statement_qs(client_id, date_from=date_from, date_to=date_to, as_of=as_of)

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
    totals = {
        "count": len(rows),
        "closing_balance": balance,
        "total_debit": sum(r["debit"] for r in rows),
        "total_credit": sum(r["credit"] for r in rows),
    }
    # Slice only after every total is computed — see the docstring.
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    return {"rows": rows, **totals}


def client_statement_with_opening(
    client_id, *, date_from=None, date_to=None, as_of=None, offset=0, limit=None,
):
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
        offset=offset, limit=limit,
    )
    for r in st["rows"]:
        r["balance"] += opening_balance
    # NOT st["rows"][-1]: with a paginated slice that is the last row on this
    # page, not the last row of the period. The period closing balance only
    # means anything once the opening balance is added back.
    closing_balance = st["closing_balance"] + opening_balance
    return {
        "rows": st["rows"],
        "count": st["count"],
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "total_debit": st["total_debit"],
        "total_credit": st["total_credit"],
    }


def client_ledger(client_id, *, date_from=None, date_to=None, hide_voided=True, q=""):
    """Buku besar client untuk halaman detail: baris periode + saldo awal/akhir,
    total, dan subtotal per bulan.

    `hide_voided` membuang pasangan batal (entry yang di-reverse DAN reversal-nya)
    dari tampilan. Saldo berjalan lalu dihitung ulang tanpa pasangan itu dari awal
    riwayat — bukan sekadar menyembunyikan barisnya — supaya saldo tiap baris yang
    tampil tetap bisa dijelaskan oleh baris di atasnya. Karena setiap pasangan
    netonya nol, saldo akhir sama persis dengan versi lengkapnya.

    `q` hanya menyaring baris yang dikembalikan; saldo, total dan subtotal bulan
    tetap milik seluruh periode.
    """
    st = client_statement(client_id, date_to=date_to)
    balance = opening = 0
    period, hidden = [], 0
    for r in st["rows"]:
        in_period = not date_from or r["date"] >= date_from
        if hide_voided and r["is_voided"]:
            hidden += in_period
            continue
        balance += r["debit"] - r["credit"]
        if in_period:
            period.append({**r, "balance": balance})
        else:
            opening = balance

    months = {}
    for r in period:
        m = months.setdefault(r["date"].strftime("%Y-%m"), {"debit": 0, "credit": 0, "closing": 0, "n": 0})
        m["n"] += 1
        m["debit"] += r["debit"]
        m["credit"] += r["credit"]
        m["closing"] = r["balance"]

    rows = period
    if q:
        needle = q.casefold()
        rows = [
            r for r in period
            if any(needle in (r.get(k) or "").casefold()
                   for k in ("invoice_number", "entry_number", "description", "reservation_number"))
        ]
    return {
        "rows": rows,
        "period_count": len(period),
        "hidden_voided": hidden,
        "opening_balance": opening,
        "closing_balance": balance,
        "total_debit": sum(r["debit"] for r in period),
        "total_credit": sum(r["credit"] for r in period),
        "months": months,
    }


def client_statement_by_reservation(
    client_id, *, date_from=None, date_to=None, as_of=None,
):
    """Statement open-item: baris jurnal client di-rollup jadi satu baris per
    reservasi (Debit / Credit / Balance), bukan satu baris per transaksi.

    Statement membaca dua akun, Piutang dan Titipan, dan keduanya dipisah
    supaya tiap angka di PDF berarti satu hal:
      - Baris Piutang ber-reservasi -> baris reservasi (`billed` / `paid`).
      - `adjustments` -- debit Piutang tanpa reservasi. Sejak invoice servis
        dihapus dan penalty melekat ke reservasinya, sisanya hanya adjustment
        manual.
      - `unapplied_payments` -- credit Piutang tanpa reservasi: pembayaran yang
        sudah masuk tapi belum dialokasikan.
      - `deposit_on_account` -- saldo Titipan (credit - debit). Refund, transfer
        antar client, dan pemakaian titipan hanya menggerakkan angka ini; tanpa
        pemisahan itu refund titipan terbaca sebagai tagihan tanpa reservasi.
    Debit Piutang pada jurnal transfer adalah kelebihan bayar yang dipindah ke
    titipan, bukan tagihan baru: ia mengurangi `paid` reservasinya (atau
    `unapplied_payments` bila tanpa reservasi), dan pasangannya muncul di
    `deposit_on_account`. Tanpa aturan ini kolom Debit ikut menghitung uang
    yang dipindah, tidak lagi sama dengan nilai tagihan.

    Pasangan reversal (entry yang dibatalkan + entry reversal-nya) dibuang dari
    semua bucket. Net-nya nol, jadi saldo tidak berubah; yang bersih cuma
    `billed`/`paid` -- tanpa itu Total debit di PDF ikut menghitung
    charge/payment yang sudah dibatalkan.
    `unallocated` = adjustments - unapplied_payments - deposit_on_account, semua
    yang di luar baris reservasi.

    Invarian: opening_balance + Σ(reservasi.balance) + unallocated ==
    closing_balance -- sama persis dengan versi balance-forward. Di-assert.
    """
    from datetime import date

    st = client_statement_with_opening(
        client_id, date_from=date_from, date_to=date_to, as_of=as_of,
    )

    groups = {}
    adjustments = 0
    unapplied_payments = 0
    deposit_on_account = 0
    for r in st["rows"]:
        if r["is_voided"]:
            continue
        if r["account"] == coa.CUST_CREDIT:
            deposit_on_account += r["credit"] - r["debit"]
            continue
        # Debit Piutang di jurnal transfer = kelebihan bayar keluar ke titipan.
        moved_out = r["debit"] if r["entry_type"] == JournalEntry.TYPE_TRANSFER else 0
        debit = r["debit"] - moved_out
        credit = r["credit"] - moved_out
        rid = r["reservation_id"]
        if rid is None:
            adjustments += debit
            unapplied_payments += credit
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
        g["billed"] += debit
        g["paid"] += credit

    unallocated = adjustments - unapplied_payments - deposit_on_account

    reservations = []
    for g in groups.values():
        g["balance"] = g["billed"] - g["paid"]
        g["settled"] = g["balance"] <= 0
        reservations.append(g)

    # Urut check_in naik, lunas atau tidak; tanpa check_in di paling bawah.
    reservations.sort(
        key=lambda g: (g["check_in"] or date.max, g["reservation_number"] or "")
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
        "adjustments": adjustments,
        "unapplied_payments": unapplied_payments,
        "deposit_on_account": deposit_on_account,
        "reservations": reservations,
        "aging": client_aging(client_id, as_of=as_of, date_to=date_to),
    }


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


def client_aging(client_id, *, as_of=None, date_to=None):
    """Aging summary per invoice — berapa lama piutang belum dibayar.

    `date_to` membatasi invoice mana yang dihitung: hanya journal pada atau sebelum
    tanggal itu yang masuk, jadi aging memakai periode yang sama dengan
    statement-nya. `as_of` membatasi histori jurnal — untuk data historis, bukan
    cutoff tanggal invoice.

    Bucket dihitung relatif terhadap `date_to` bila ada, karena itulah tanggal
    yang dipakai pengguna untuk memblok baris jurnal: statement yang difilter
    sampai 31 Jan tidak bolehsays "3 bulan terlambat" untuk invoice yang tempo
    temponya baru jatuh tempo bulan lalu.

    Returns {buckets: {current, 1_30, 31_60, 61_90, 90_plus}, total, invoices:
    [...]} — bucket yang sama dengan AGING_BUCKETS, jadi klien ini dan AR
    Aging page selalu bisa dibandingkan langsung.
    """

    today = date_to or (as_of.date() if as_of else timezone.localdate())

    # Net AR lines per invoice (charge - payment/reversal)
    ar_lines = _scoped(_ar_qs(client_id=client_id), as_of=as_of)
    if date_to:
        ar_lines = ar_lines.filter(journal_entry__entry_date__lte=date_to)
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

    buckets = {b: 0 for b in AGING_BUCKETS}
    total = 0
    invoices = []

    for row in invoice_nets:
        net = (row["d"] or 0) - (row["c"] or 0)
        if net <= 0:
            continue  # fully paid or credit
        if not row["invoice_id"]:
            # Piutang tanpa invoice (mis. charge manual) tidak punya due date,
            # jadi tidak bisa dihitungkan umurnya. ar_aging() memang menjumlahkan
            # sisa seperti ini ke 'current' — doing the same here is what makes
            # the two pages add up to the same total.
            buckets["current"] += net
            total += net
            continue
        inv = inv_map.get(row["invoice_id"])
        if not inv:
            continue

        due = inv.get("due_date") or inv.get("issued_date")
        # Not yet due is a bucket of its own, not "age 0": an invoice due in
        # three weeks is not in the same state as one due today.
        days_overdue = (today - due).days if due else 0

        buckets[_aging_bucket(days_overdue)] += net

        total += net
        invoices.append({
            "id": row["invoice_id"],
            "invoice_number": inv["invoice_number"],
            "amount": net,
            "due_date": inv["due_date"].isoformat() if inv.get("due_date") else None,
            "age_days": max(days_overdue, 0),
            "days_overdue": max(days_overdue, 0),
            "bucket": _aging_bucket(days_overdue),
        })

    invoices.sort(key=lambda x: -x["age_days"])
    return {"buckets": buckets, "total": total, "invoices": invoices}


def ar_aging(*, as_of=None, clients=None):
    """Aging piutang semua client per tanggal `as_of` (date; default hari ini).

    Sisa per invoice = net baris Piutang dengan entry_date <= as_of (charge −
    pembayaran − nota kredit ± reversal), dikelompokkan menurut hari lewat
    jatuh tempo (due_date, atau issued_date bila kosong). Invoice yang sudah
    lunas/lebih bayar tidak ikut. Baris Piutang tanpa invoice dijumlahkan ke
    'current' klien tersebut. `clients` membatasi ke queryset Client tertentu.

    Returns {as_of, buckets: {...}, total, clients: [{client_id, name, buckets,
    total, oldest_days, invoices: [...]}]} — clients diurutkan dari total
    terbesar."""

    from ..models.invoice import Invoice

    as_of = as_of or timezone.localdate()
    nets = _ar_qs(journal_entry__entry_date__lte=as_of, client_id__isnull=False)
    if clients is not None:
        nets = nets.filter(client_id__in=clients.values("id"))
    nets = (
        nets
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

    # Sama seperti client_aging(): "overdue" berarti lewat tanggal yang sedang
    # dipakai, bukan lewat hari ini — kalau statement-nya di-lock ke periode
    # lama, daftar open item-nya harus Seasam itu juga.
    today = date_to or (as_of.date() if as_of else timezone.localdate())

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
        aged_from = due or inv.get("issued_date")
        rows.append({
            "id": inv_id,
            "invoice_number": inv["invoice_number"],
            "invoice_type": inv["invoice_type"],
            "issued_date": inv["issued_date"].isoformat() if inv.get("issued_date") else None,
            "due_date": due.isoformat() if due else None,
            "billed": billed,
            "paid": paid,
            "remaining": remaining,
            "overdue": bool(due and (today - due).days > 0),
            # "38d late" beats a red date: how late is the question a bookkeeper
            # actually asks, and it sorts the list for them.
            "days_overdue": max((today - due).days, 0) if due else 0,
            # Same bucket the client's aging puts this invoice in (it ages from
            # the issue date when there is no due date), so a click on an aging
            # segment filters this list to exactly that segment's invoices.
            "bucket": _aging_bucket((today - aged_from).days) if aged_from else "current",
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


def kas_pusat():
    return cash_balance(coa.CASH_PUSAT)


def transit():
    return account_balance(coa.TRANSIT)


def money_accounts_overview(branch=None, include_inactive=False, branches=None):
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
    if branches is not None:
        bank_qs = bank_qs.filter(branch_id__in=branches)
        cash_qs = cash_qs.filter(branch_id__in=branches)
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
    rows += _staff_overview(branch=branch, branches=branches)
    return rows


def _staff_overview(*, branch=None, branches=None):
    """Uang muka staf as rows of the accounts overview: what each one holds in
    its currency, its SAR value at its ledger's average rate (all advances of
    a branch and currency share one ledger account), when money was last
    given, and whether an expense has been paid from it since."""
    from django.db.models import Max

    from ..models.bank import StaffAccount
    from ..models.bank_transaction import BankTransaction
    from ..models.expense import ExpensePayment
    from .staff_advance import balances, display_name
    qs = StaffAccount.objects.filter(is_active=True).select_related('holder', 'branch')
    if branch:
        qs = qs.filter(branch_id=branch)
    if branches is not None:
        qs = qs.filter(branch_id__in=branches)
    accounts = list(qs)
    held = balances(accounts)
    ids = [a.pk for a in accounts]
    live = BankTransaction.objects.filter(account_id__in=ids).exclude(status=BankTransaction.STATUS_VOIDED)
    given = dict(live.filter(direction=BankTransaction.DIRECTION_IN).values('account_id')
                 .annotate(d=Max('transaction_date')).values_list('account_id', 'd'))
    spent = dict(ExpensePayment.objects.filter(source_account_id__in=ids, status=ExpensePayment.STATUS_PAID)
                 .values('source_account_id').annotate(d=Max('payment_date')).values_list('source_account_id', 'd'))
    rates = {}
    rows = []
    for acc in accounts:
        if acc.ledger_account_id not in rates:
            sar = account_balance(acc.ledger_account_id)
            native = sum(held[a.pk] for a in accounts if a.ledger_account_id == acc.ledger_account_id)
            rates[acc.ledger_account_id] = (sar / native) if native else 0
        value = int(round(held[acc.pk] * rates[acc.ledger_account_id])) if acc.currency != 'SAR' else held[acc.pk]
        rows.append({
            'id': acc.pk, 'kind': 'staff', 'name': display_name(acc.holder),
            'ledger_account': acc.ledger_account_id, 'ledger_shared': False,
            'branch': acc.branch_id, 'currency': acc.currency,
            'book_balance': value, 'native_balance': held[acc.pk],
            'is_active': acc.is_active, 'show_on_invoice': False, 'account_identifier': '',
            'given_on': given[acc.pk].isoformat() if given.get(acc.pk) else None,
            'spent_since': bool(spent.get(acc.pk) and given.get(acc.pk) and spent[acc.pk] >= given[acc.pk]),
        })
    return rows


def account_transactions(kind, account_id, *, date_from=None, date_to=None):
    """Riwayat BankTransaction satu rekening (bank/kas), dengan saldo berjalan.

    Saldo berjalan di sini murni jumlah kumulatif BankTransaction rekening
    ini — BUKAN book_balance (proyeksi JournalLine); dua-duanya bisa berbeda
    untuk event lama yang belum lewat titik `record_bank_transaction`
    (mis. payment legacy `received_in`-only, lihat bank_transaction.py)."""
    from ..models.bank import BankAccount, CashAccount, StaffAccount
    from ..models.bank_transaction import BankTransaction

    account_model = {'bank': BankAccount, 'cash': CashAccount, 'staff': StaffAccount}[kind]
    account = account_model.objects.filter(pk=account_id).first()
    if account is None:
        return None

    qs = (
        BankTransaction.objects.filter(account_id=account.pk)
        .exclude(status=BankTransaction.STATUS_VOIDED)
        .order_by('transaction_date', 'id')
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
            'matched': tx.match_id is not None,
        })
    rows.reverse()
    return {'account': {'id': account.pk, 'kind': kind, 'name': str(account), 'currency': account.currency}, 'rows': rows}


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


OVERVIEW_SORTS = {
    # Biggest debtor first is what a collections list is read for; the rest
    # are alphabetical / biggest-first for reconciliation walks.
    "receivable": lambda r: (-r["piutang"], r["client_id"]),
    "billed": lambda r: (-r["tagihan"], r["client_id"]),
    "paid": lambda r: (-r["terbayar"], r["client_id"]),
    "credit": lambda r: (-r["saldo_dana"], r["client_id"]),
    "name": lambda r: (r["name"].lower(), r["client_id"]),
}


def clients_overview(*, q="", outstanding_only=False, sort="receivable", clients=None):
    """Agregat bulk per-client untuk halaman daftar statement. Derivasinya
    konsisten dengan properti Client (billed/payable/credit) dari jurnal.

    Hanya klien yang punya jejak di jurnal yang dikembalikan: daftar ini
    adalah ledger, bukan direktori, jadi klien tanpa tagihan/pembayaran/
    titipan tidak muncul sebagai baris nol.

    `q` menyaring nama di level Client (sebelum agregasi), jadi pencarian
    tidak menyapu seluruh jurnal. `outstanding_only` menyisakan yang masih
    punya piutang. `sort` kunci dari OVERVIEW_SORTS. `clients` membatasi ke
    queryset Client tertentu (mis. client cabang user).
    """
    qs = clients if clients is not None else Client.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    names = dict(qs.values_list("id", "name"))
    cids = list(names)

    billed = {
        r["client_id"]: (r["d"] or 0) - (r["c"] or 0)
        for r in _billing(client_id__in=cids)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    paid = client_paid_map(cids)
    ar_rows = {
        r["client_id"]: (r["d"] or 0, r["c"] or 0)
        for r in _ar_qs(client_id__in=cids)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }
    receivable = {cid: d - c for cid, (d, c) in ar_rows.items()}
    credit = {
        r["client_id"]: (r["c"] or 0) - (r["d"] or 0)
        for r in JournalLine.objects.filter(client_id__in=cids, account_id=coa.CUST_CREDIT)
        .values("client_id").annotate(d=Sum("debit"), c=Sum("credit"))
    }

    overview = []
    for cid in cids:
        row = {
            "client_id": cid,
            "name": names[cid],
            "tagihan": billed.get(cid, 0),
            "terbayar": paid.get(cid, 0),
            "piutang": receivable.get(cid, 0),
            "saldo_dana": credit.get(cid, 0),
            # The receivable account's own debit and credit (Client Ledger list).
            "ar_debit": ar_rows.get(cid, (0, 0))[0],
            "ar_credit": ar_rows.get(cid, (0, 0))[1],
        }
        if outstanding_only and row["piutang"] <= 0:
            continue
        # No ledger footprint at all → not a statement row.
        if not (row["tagihan"] or row["terbayar"] or row["piutang"] or row["saldo_dana"]):
            continue
        overview.append(row)

    overview.sort(key=OVERVIEW_SORTS.get(sort, OVERVIEW_SORTS["receivable"]))
    return overview


# ── Trial balance ──────────────────────────────────────────────

# Tahun buku = tahun kalender (Januari–Desember).
_PL_TYPES = ("income", "expense")


def trial_balance(*, date_from=None, date_to=None):
    """Saldo awal (per date_from), mutasi debit/kredit, dan saldo akhir (per
    date_to) tiap akun; saldo bertanda debit − kredit.

    Akun neraca membawa saldonya terus. Pendapatan dan beban mulai nol di
    awal tiap tahun buku: laba tahun-tahun sebelumnya dibaca di Laba Ditahan
    lewat tutup tahun virtual, tanpa jurnal penutup. Bila rentang melewati
    31 Desember, penutupan tahun itu ikut di kolom mutasi (`year_ends`),
    supaya saldo awal + debit − kredit = saldo akhir di setiap baris."""
    from datetime import date

    from django.db.models.functions import ExtractYear

    lines = JournalLine.objects.all()
    if date_to:
        lines = lines.filter(journal_entry__entry_date__lte=date_to)
    by_year = lines.annotate(y=ExtractYear("journal_entry__entry_date")).values("account", "y")
    before = by_year.filter(journal_entry__entry_date__lt=date_from) if date_from else by_year.none()
    inside = by_year.filter(journal_entry__entry_date__gte=date_from) if date_from else by_year
    before = list(before.annotate(d=Sum("debit"), c=Sum("credit")))
    inside = list(inside.annotate(d=Sum("debit"), c=Sum("credit")))

    accounts = {a.code: a for a in LedgerAccount.objects.all()}
    pl = {code for code, a in accounts.items() if a.type in _PL_TYPES}
    years = [r["y"] for r in inside + before]
    first_year = date_from.year if date_from else min(years, default=timezone.localdate().year)
    last_year = date_to.year if date_to else max(years + [timezone.localdate().year])

    rows = {}

    def row(code):
        return rows.setdefault(code, {"opening": 0, "debit": 0, "credit": 0})

    # Saldo awal: akun neraca seluruh riwayat; laba-rugi hanya tahun buku
    # date_from, tahun-tahun sebelumnya ke Laba Ditahan.
    pl_open = {}
    for r in before:
        net = (r["d"] or 0) - (r["c"] or 0)
        if r["account"] in pl and r["y"] < first_year:
            row(coa.RETAINED_EARNINGS)["opening"] += net
            continue
        row(r["account"])["opening"] += net
        if r["account"] in pl:
            pl_open[r["account"]] = pl_open.get(r["account"], 0) + net

    pl_year = {}
    for r in inside:
        rw = row(r["account"])
        rw["debit"] += r["d"] or 0
        rw["credit"] += r["c"] or 0
        if r["account"] in pl:
            key = (r["account"], r["y"])
            pl_year[key] = pl_year.get(key, 0) + (r["d"] or 0) - (r["c"] or 0)

    # Tutup tahun virtual untuk setiap 31 Desember di dalam rentang.
    year_ends = []
    for y in range(first_year, last_year):
        closed = 0
        for code in pl:
            bal = pl_year.get((code, y), 0) + (pl_open.get(code, 0) if y == first_year else 0)
            if bal:
                row(code)["credit" if bal > 0 else "debit"] += abs(bal)
                closed += bal
        if closed:
            row(coa.RETAINED_EARNINGS)["debit" if closed > 0 else "credit"] += abs(closed)
        year_ends.append(date(y, 12, 31).isoformat())

    out = []
    for code, rw in rows.items():
        if not (rw["opening"] or rw["debit"] or rw["credit"]):
            continue
        acc = accounts.get(code)
        out.append({
            "account": code, "account_name": acc.name if acc else code,
            "type": acc.type if acc else "", "normal_balance": acc.normal_balance if acc else "debit",
            **rw, "closing": rw["opening"] + rw["debit"] - rw["credit"],
        })
    total_d = sum(r["debit"] for r in out)
    total_c = sum(r["credit"] for r in out)
    return {
        "rows": out,
        "total_debit": total_d,
        "total_credit": total_c,
        "balanced": total_d == total_c and not sum(r["opening"] for r in out) and not sum(r["closing"] for r in out),
        "year_ends": year_ends,
    }
