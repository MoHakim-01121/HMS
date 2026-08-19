"""Pure derivation functions over the Charge/Allocation/CashMovement ledger.

This module is the only place that knows how to compute money. Views call it,
never Sum() the ledger tables themselves.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q, Sum

from .models.ledger import Account, Charge, Allocation, CashMovement


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
    in_ = _sum_sar(CashMovement.objects.filter(client=client, from_account=Account.CLIENT))
    out_ = _sum_sar(CashMovement.objects.filter(client=client, to_account=Account.CLIENT))
    alloc = _sum(Allocation.objects.filter(client=client))
    return in_ - out_ - alloc


def total_charged_by_client(client):
    return _sum(Charge.objects.filter(client=client))


def total_paid_by_client(client):
    return _sum_sar(CashMovement.objects.filter(client=client, from_account=Account.CLIENT))


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
    return _wallet_net(company, Account.SBY, invoice_ids)


def kas_pusat(company=None, invoice_ids=None):
    return _wallet_net(company, Account.PUSAT, invoice_ids)


def selisih_kurs(company=None, invoice_ids=None):
    return _wallet_net(company, Account.FX, invoice_ids)


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
    qs = CashMovement.objects.filter(from_account=Account.CLIENT, to_account=account)
    if company:
        qs = qs.filter(company=company)
    if invoice_ids is not None:
        qs = qs.filter(invoice_id__in=invoice_ids)
    return _sum_sar(qs)


def total_client_cash_in(company=None, invoice_ids=None):
    """Gross amount clients paid in, regardless of destination account."""
    qs = CashMovement.objects.filter(from_account=Account.CLIENT)
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
        invoice_id=invoice_id, from_account=Account.CLIENT, penalty_label__isnull=True,
    )
    return _sum_sar(qs)


def reservation_cash_breakdown(company=None):
    """Bulk per-reservation cash breakdown for the remittance dashboard:
    {reservation_id: {terbayar_sby, terbayar_direct, sudah_dikirim, mengendap}}.

    Computed in one pass over CashMovement -- callers that need this for many
    reservations at once (e.g. every reservation for a company) should use
    this instead of calling mengendap_per_res() in a loop (N+1 queries)."""
    qs = CashMovement.objects.filter(reservation_label__isnull=False)
    if company:
        qs = qs.filter(company=company)
    raw = defaultdict(lambda: {'terbayar_sby': 0, 'terbayar_direct': 0, 'sent_from_sby': 0})
    for m in qs:
        rid = m.reservation_label_id
        sar = m.amount_sar
        if m.from_account == Account.CLIENT and m.to_account == Account.SBY:
            raw[rid]['terbayar_sby'] += sar
        elif m.from_account == Account.CLIENT and m.to_account == Account.PUSAT:
            raw[rid]['terbayar_direct'] += sar
        elif m.from_account == Account.SBY and m.to_account == Account.PUSAT:
            raw[rid]['sent_from_sby'] += sar
    return {
        rid: {
            'terbayar_sby': d['terbayar_sby'],
            'terbayar_direct': d['terbayar_direct'],
            'sudah_dikirim': d['sent_from_sby'] + d['terbayar_direct'],
            'mengendap': d['terbayar_sby'] - d['sent_from_sby'],
        }
        for rid, d in raw.items()
    }


def mengendap_per_res(reservation):
    qs = CashMovement.objects.filter(reservation_label=reservation)
    in_ = _sum_sar(qs.filter(to_account=Account.SBY))
    out_ = _sum_sar(qs.filter(from_account=Account.SBY))
    return in_ - out_


def mengendap_per_service_item(service_item):
    qs = CashMovement.objects.filter(service_item_label=service_item)
    in_ = _sum_sar(qs.filter(to_account=Account.SBY))
    out_ = _sum_sar(qs.filter(from_account=Account.SBY))
    return in_ - out_


def mengendap_per_penalty(penalty):
    qs = CashMovement.objects.filter(penalty_label=penalty)
    in_ = _sum_sar(qs.filter(to_account=Account.SBY))
    out_ = _sum_sar(qs.filter(from_account=Account.SBY))
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
        Q(from_account=Account.CLIENT) | Q(to_account=Account.CLIENT)
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
        if m.from_account == Account.CLIENT:
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
