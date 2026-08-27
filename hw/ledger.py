"""Pure derivation functions over the Charge/Allocation/CashMovement ledger.

This module is the only place that knows how to compute money. Views call it,
never Sum() the ledger tables themselves.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q, Sum

from .models.ledger import CashAccount, Charge, Allocation, CashMovement
from .models.invoice import RemittanceLine


def _sum(qs, field='amount_sar'):
    return qs.aggregate(total=Sum(field))['total'] or 0


def tagihan(reservation):
    return _sum(Charge.objects.filter(reservation=reservation))


def terbayar(reservation):
    return _sum(Allocation.objects.filter(reservation=reservation))


def piutang(reservation):
    return tagihan(reservation) - terbayar(reservation)


def _sum_sar(qs):
    # amount_sar is a computed property (currency conversion is per-row), so it
    # can't be summed in SQL — must sum in Python.
    return sum(m.amount_sar for m in qs)


def saldo_dana(client):
    in_ = _sum_sar(CashMovement.objects.filter(client=client, from_account=CashAccount.CLIENT))
    out_ = _sum_sar(CashMovement.objects.filter(client=client, to_account=CashAccount.CLIENT))
    alloc = _sum(Allocation.objects.filter(client=client))
    return in_ - out_ - alloc


def total_charged_by_client(client):
    return _sum(Charge.objects.filter(client=client))


def total_paid_by_client(client):
    return _sum_sar(CashMovement.objects.filter(client=client, from_account=CashAccount.CLIENT))


def piutang_klien(client):
    allocated = _sum(Allocation.objects.filter(client=client))
    return total_charged_by_client(client) - allocated


def _wallet_net(company, account, invoice_ids=None):
    qs = CashMovement.objects.all()
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    in_ = _sum_sar(qs.filter(to_account=account))
    out_ = _sum_sar(qs.filter(from_account=account))
    return in_ - out_


def kas_surabaya(company=None, invoice_ids=None):
    return _wallet_net(company, CashAccount.SBY, invoice_ids)


def kas_jakarta(company=None, invoice_ids=None):
    return _wallet_net(company, CashAccount.JKT, invoice_ids)


def kas_pusat(company=None, invoice_ids=None):
    return _wallet_net(company, CashAccount.PUSAT, invoice_ids)


def selisih_kurs(company=None, invoice_ids=None):
    return _wallet_net(company, CashAccount.FX, invoice_ids)


# ── Cash routing ────────────────────────────────────────────────
# The single place that decides which kas wallet receives a client's
# payment. Every view that records a CLIENT CashMovement must go through
# this instead of re-deriving `PUSAT if method == 'direct' else SBY`.

def cash_destination(method='', received_in=''):
    """Which kas account receives a CLIENT payment.

    `received_in` names the kas explicitly when the form records it:
    'jkt' → Jakarta's own wallet, 'pusat'/'direct' → straight to HQ.
    Legacy rows/forms express "straight to HQ" as a Direct *method* —
    that must keep winning over received_in's column default ('sby'), or
    every pre-received_in Direct payment turns into Surabaya idle money.
    Everything else lands in Surabaya.
    """
    rin = (received_in or '').strip().lower()
    if rin in ('jkt', 'jakarta'):
        return CashAccount.JKT
    if rin in ('pusat', 'direct'):
        return CashAccount.PUSAT
    if (method or '').strip().lower() == 'direct':
        return CashAccount.PUSAT
    return CashAccount.SBY


def cash_journal_account(destination):
    """Ledger Account (client/sby/jkt/pusat) → journal Chart-of-Accounts."""
    from .models.journal import Account as JournalAccount
    return {
        CashAccount.SBY:   JournalAccount.CASH_SBY,
        CashAccount.JKT:   JournalAccount.CASH_JKT,
        CashAccount.PUSAT: JournalAccount.CASH_PUSAT,
    }.get(destination, JournalAccount.CASH_SBY)


def total_charge(company=None, invoice_ids=None):
    qs = Charge.objects.all()
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return _sum(qs)


def total_allocation(company=None, invoice_ids=None):
    qs = Allocation.objects.all()
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return _sum(qs)


def client_paid_to(account, company=None, invoice_ids=None):
    """Gross amount clients paid directly into `account` (CLIENT -> account),
    not netted against money that later left `account` -- for "how much came
    in via this route" style stats. Use kas_surabaya/kas_pusat instead when
    you want the net wallet balance."""
    qs = CashMovement.objects.filter(from_account=CashAccount.CLIENT, to_account=account)
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return _sum_sar(qs)


def total_client_cash_in(company=None, invoice_ids=None):
    """Gross amount clients paid in, regardless of destination account."""
    qs = CashMovement.objects.filter(from_account=CashAccount.CLIENT)
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return _sum_sar(qs)


def invoice_paid_sar(invoice_id):
    """Money paid toward this invoice's reservations/service items.

    Excludes penalty-linked movements: a CancellationPenalty's Charge/
    CashMovement is tagged with the invoice its CL happened to belong to
    (for traceability), but Invoice.total_sar only ever sums reservations --
    so counting a penalty payment here would make an invoice look more paid
    off than its own total_sar can account for.
    """
    qs = CashMovement.objects.filter(
        invoice_id=invoice_id, from_account=CashAccount.CLIENT, penalty_label__isnull=True,
    )
    return _sum_sar(qs)


def invoice_paid_sar_map(invoice_ids):
    """Bulk invoice_paid_sar(): {invoice_id: paid_sar} in one query.

    Callers that loop over many invoices use this instead of touching
    Invoice.total_paid_sar per row (one ledger query per invoice)."""
    if not invoice_ids:
        return {}
    paid = defaultdict(int)
    for m in CashMovement.objects.filter(
        invoice_id__in=invoice_ids, from_account=CashAccount.CLIENT, penalty_label__isnull=True,
    ):
        paid[m.invoice_id] += m.amount_sar
    return paid


def cl_paid_sar_map(letters):
    """Bulk ConfirmationLetter.paid_sar(): {cl_pk: paid_sar} in one query.

    Same attribution rule as the per-CL property: a Payment belongs to its
    `cl` when set, otherwise to the CL whose confirmation_number it links."""
    if not letters:
        return {}
    from .models.invoice import Payment
    from .utils import convert_to_sar

    pk_by_number = {cl.confirmation_number: cl.pk for cl in letters}
    paid = {cl.pk: 0 for cl in letters}
    rows = Payment.objects.filter(
        Q(cl_id__in=paid) |
        Q(linked_number__in=pk_by_number, cl__isnull=True),
    ).values_list('cl_id', 'linked_number', 'amount', 'currency', 'exchange_rate')
    for cl_id, linked_number, amount, currency, rate in rows:
        target = cl_id or pk_by_number.get(linked_number)
        if target in paid:
            paid[target] += int(round(convert_to_sar(amount, currency, float(rate))))
    return paid


def reservation_cash_breakdown(company=None):
    """Bulk per-reservation cash breakdown for the remittance dashboard:
    {reservation_id: {terbayar_sby, terbayar_jkt, terbayar_direct, sudah_dikirim, mengendap, mengendap_jkt}}.

    Computed in one pass over CashMovement -- callers that need this for many
    reservations at once (e.g. every reservation for a company) should use
    this instead of calling mengendap_per_res() in a loop (N+1 queries)."""
    qs = CashMovement.objects.filter(reservation_label__isnull=False)
    if company:
        qs = qs.filter(company=company)
    raw = defaultdict(lambda: {
        'terbayar_sby': 0, 'terbayar_jkt': 0, 'terbayar_direct': 0,
        'sent_from_sby': 0, 'sent_from_jkt': 0,
    })
    for m in qs:
        rid = m.reservation_label_id
        sar = m.amount_sar
        if m.from_account == CashAccount.CLIENT and m.to_account == CashAccount.SBY:
            raw[rid]['terbayar_sby'] += sar
        elif m.from_account == CashAccount.CLIENT and m.to_account == CashAccount.JKT:
            raw[rid]['terbayar_jkt'] += sar
        elif m.from_account == CashAccount.CLIENT and m.to_account == CashAccount.PUSAT:
            raw[rid]['terbayar_direct'] += sar
        elif m.from_account == CashAccount.SBY and m.to_account == CashAccount.PUSAT:
            raw[rid]['sent_from_sby'] += sar
        elif m.from_account == CashAccount.JKT and m.to_account == CashAccount.PUSAT:
            raw[rid]['sent_from_jkt'] += sar
    return {
        rid: {
            'terbayar_sby': d['terbayar_sby'],
            'terbayar_jkt': d['terbayar_jkt'],
            'terbayar_direct': d['terbayar_direct'],
            # Direct-to-HQ counts as already sent: it never has to be remitted.
            'sudah_dikirim': d['sent_from_sby'] + d['terbayar_direct'],
            'mengendap': d['terbayar_sby'] - d['sent_from_sby'],
            # Jakarta's own idle money -- tracked separately so Surabaya's
            # remittance obligation never includes cash that landed in Jakarta.
            'mengendap_jkt': d['terbayar_jkt'] - d['sent_from_jkt'],
        }
        for rid, d in raw.items()
    }


def mengendap_per_res(reservation):
    qs = CashMovement.objects.filter(reservation_label=reservation)
    in_ = _sum_sar(qs.filter(to_account=CashAccount.SBY))
    out_ = _sum_sar(qs.filter(from_account=CashAccount.SBY))
    return in_ - out_


def mengendap_per_service_item(service_item):
    qs = CashMovement.objects.filter(service_item_label=service_item)
    in_ = _sum_sar(qs.filter(to_account=CashAccount.SBY))
    out_ = _sum_sar(qs.filter(from_account=CashAccount.SBY))
    return in_ - out_


def mengendap_per_penalty(penalty):
    qs = CashMovement.objects.filter(penalty_label=penalty)
    in_ = _sum_sar(qs.filter(to_account=CashAccount.SBY))
    out_ = _sum_sar(qs.filter(from_account=CashAccount.SBY))
    return in_ - out_


def surplus_pusat(company=None):
    return kas_pusat(company) + selisih_kurs(company) - total_allocation(company)


def kewajiban_kirim_sby(company=None):
    return -surplus_pusat(company)


def _target_label(entry):
    if entry.reservation_id:
        return entry.reservation.reservation_number
    if entry.service_item_id:
        return entry.service_item.name
    if entry.penalty_id:
        return entry.penalty.penalty_number
    return '—'


def client_statement(client, date_from=None, date_to=None, as_of=None):
    """Full customer statement: every Charge (debit), every CLIENT-touching
    CashMovement (credit = money in, debit = refund out), and transfer pairs
    as zero-value memo lines -- sorted (date, created_at, id) with a running
    balance. Positive balance = client still owes; negative = client has
    unused funds.

    `as_of` filters on created_at (when the row was recorded), separate from
    `date` (when the event happened) -- so reprinting a past period with the
    same `as_of` always reproduces identical numbers, even if backdated
    corrections were entered later.
    """
    charges = Charge.objects.filter(client=client).select_related('reservation', 'service_item', 'penalty')
    movements = CashMovement.objects.filter(client=client).filter(
        Q(from_account=CashAccount.CLIENT) | Q(to_account=CashAccount.CLIENT)
    )
    allocations = Allocation.objects.filter(
        client=client, transfer_group__isnull=False,
    ).select_related('reservation', 'service_item', 'penalty')

    if date_from:
        charges = charges.filter(date__gte=date_from)
        movements = movements.filter(date__gte=date_from)
        allocations = allocations.filter(date__gte=date_from)
    if date_to:
        charges = charges.filter(date__lte=date_to)
        movements = movements.filter(date__lte=date_to)
        allocations = allocations.filter(date__lte=date_to)
    if as_of:
        charges = charges.filter(created_at__lte=as_of)
        movements = movements.filter(created_at__lte=as_of)
        allocations = allocations.filter(created_at__lte=as_of)

    rows = []
    for c in charges:
        rows.append({
            'date': c.date, 'created_at': c.created_at, 'sort_id': ('charge', c.id),
            'type': 'debit', 'description': c.description or c.get_reason_display(),
            'debit': c.amount_sar, 'credit': 0,
        })
    for m in movements:
        sar = m.amount_sar
        if m.from_account == CashAccount.CLIENT:
            rows.append({
                'date': m.date, 'created_at': m.created_at, 'sort_id': ('mov', m.id),
                'type': 'credit', 'description': m.note or f'Pembayaran ({m.get_to_account_display()})',
                'debit': 0, 'credit': sar,
            })
        else:
            rows.append({
                'date': m.date, 'created_at': m.created_at, 'sort_id': ('mov', m.id),
                'type': 'debit', 'description': m.note or 'Refund',
                'debit': sar, 'credit': 0,
            })

    groups = defaultdict(list)
    for a in allocations:
        groups[a.transfer_group].append(a)
    for group_id, allocs in groups.items():
        if len(allocs) != 2:
            continue
        neg = next((a for a in allocs if a.amount_sar < 0), None)
        pos = next((a for a in allocs if a.amount_sar > 0), None)
        if not (neg and pos):
            continue
        rows.append({
            'date': max(a.date for a in allocs), 'created_at': max(a.created_at for a in allocs),
            'sort_id': ('transfer', str(group_id)), 'type': 'memo',
            'description': f'Pindah {_target_label(neg)} → {_target_label(pos)}',
            'debit': 0, 'credit': 0,
        })

    rows.sort(key=lambda r: (r['date'], r['created_at'], str(r['sort_id'])))

    balance = 0
    for r in rows:
        balance += r['debit'] - r['credit']
        r['balance'] = balance
        del r['sort_id']

    return rows


def remittance_total_sar(remittance_id):
    """Total SAR actually recorded for a remittance batch, via its
    CashMovement rows -- these are kept in exact 1:1 sync with RemittanceLine
    by _sync_remittance_lines (full delete-then-recreate on every edit), so
    this always matches the legacy `sum(line.amount_sar for line in lines)`."""
    return _sum_sar(CashMovement.objects.filter(remittance_id=remittance_id))


def reservation_remittance_map(company=None, linked_numbers=None):
    """Riwayat remittance per reservasi dalam satu query.

    Returns: {reservation_number: [
        {'rmt_id', 'rmt_number', 'date', 'status', 'amount_sar'}, ...
    ]} diurutkan kronologis (tanggal RMT, lalu waktu dibuat) -- dipakai
    halaman tracking untuk menjawab "reservasi ini sudah ikut RMT apa saja".
    """
    qs = RemittanceLine.objects.select_related('remittance').order_by(
        'remittance__date', 'remittance__created_at',
    )
    if company:
        qs = qs.filter(remittance__company=company)
    if linked_numbers is not None:
        qs = qs.filter(linked_number__in=linked_numbers)

    result = defaultdict(list)
    for l in qs:
        result[l.linked_number].append({
            'rmt_id': l.remittance_id,
            'rmt_number': l.remittance.remittance_number,
            'date': l.remittance.date,
            'status': l.remittance.status,
            'amount_sar': int(l.amount_sar or 0),
        })
    return result


def client_statement_with_opening(client, date_from=None, date_to=None, as_of=None):
    """client_statement(), but with a real opening balance folded in.

    client_statement() only sums whatever rows it's given -- ask it for a
    period that starts mid-history and its running balance starts back at
    zero, silently dropping everything that happened before `date_from`.
    This computes that dropped balance as of the same `as_of` and carries it
    forward as an opening-balance line, so a period statement's closing
    balance always reconciles with a full, unfiltered one.
    """
    opening_balance = 0
    if date_from:
        prior = client_statement(client, date_to=date_from - timedelta(days=1), as_of=as_of)
        opening_balance = prior[-1]['balance'] if prior else 0

    rows = client_statement(client, date_from=date_from, date_to=date_to, as_of=as_of)
    for r in rows:
        r['balance'] += opening_balance

    closing_balance = rows[-1]['balance'] if rows else opening_balance
    return {
        'rows': rows,
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'total_debit': sum(r['debit'] for r in rows),
        'total_credit': sum(r['credit'] for r in rows),
    }


def clients_overview():
    """Agregat bulk per-client untuk halaman daftar statement.

    Rumus identik dengan helper per-client (total_charged_by_client,
    piutang_klien, saldo_dana) supaya angkanya konsisten dengan halaman
    statement existing. Konversi SAR tetap di Python karena
    CashMovement.amount_sar adalah properti per-baris.
    """
    from .utils import convert_to_sar

    def _cash_sar_map(direction):
        rows = CashMovement.objects.filter(
            **{direction: CashAccount.CLIENT},
        ).exclude(client=None).values_list('client_id', 'amount', 'currency', 'exchange_rate')
        result = defaultdict(int)
        for client_id, amount, currency, rate in rows:
            result[client_id] += int(round(convert_to_sar(amount, currency, float(rate))))
        return result

    charges = {
        r['client_id']: r['total']
        for r in Charge.objects.exclude(client=None)
        .values('client_id').annotate(total=Sum('amount_sar'))
    }
    allocs = {
        r['client_id']: r['total']
        for r in Allocation.objects.exclude(client=None)
        .values('client_id').annotate(total=Sum('amount_sar'))
    }
    cash_in = _cash_sar_map('from_account')
    cash_out = _cash_sar_map('to_account')

    client_ids = set(charges) | set(allocs) | set(cash_in) | set(cash_out)
    overview = []
    for cid in client_ids:
        tagihan = charges.get(cid, 0)
        allocated = allocs.get(cid, 0)
        paid = cash_in.get(cid, 0)
        overview.append({
            'client_id': cid,
            'tagihan': tagihan,
            'terbayar': paid,
            'allocated': allocated,
            'piutang': tagihan - allocated,
            'saldo_dana': paid - cash_out.get(cid, 0) - allocated,
        })
    overview.sort(key=lambda r: (-r['piutang'], r['client_id']))
    return overview
