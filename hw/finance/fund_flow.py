"""Branch fund flow and realized FX profit (Arus Dana).

Business model: a branch collects client money (IDR, sometimes USD) and must
remit the full SAR value of each booking to HQ; the branch's own income is the
exchange spread. Two questions, answered in real currencies:

  fund_flow()  how much came in from clients, was exchanged, sent to HQ, spent
               on operations and refunded — per currency, from the cash book
               (BankTransaction.amount), plus the opening/closing balance.
  fx_profit()  what each transfer to HQ earned: SAR sent × weighted-average
               cost of the client money held (IAS 21) − rupiah actually sent.

The SAR journal stays the system of record for what is owed; this module only
reads source documents and the cash book.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ..models.bank_transaction import BankTransaction

# Cash-book source → fund-flow line.
CATEGORY_BY_SOURCE = {
    'PaymentRecord': 'client_in',
    'CurrencyExchangeIn': 'exchange_in',
    'CurrencyExchangeOut': 'exchange_out',
    'Remittance': 'sent_hq',
    'RemittanceSettlement': 'hq_receipts',
    'ExpensePayment': 'operational',
    'Refund': 'refund',
    'OpeningBalance': 'opening_rows',
}
LINES = [
    ('opening', 'Opening balance'),
    ('client_in', 'Received from clients'),
    ('exchange_in', 'Exchanged in'),
    ('exchange_out', 'Exchanged out'),
    ('hq_receipts', 'Received from branches'),
    ('sent_hq', 'Sent to HQ'),
    ('operational', 'Operational'),
    ('refund', 'Refunds to clients'),
    ('other', 'Other'),
    ('closing', 'Closing balance'),
]
UNRECORDED = 'Account not recorded'


def _account(tx):
    return tx.account


def _signed(tx):
    return tx.amount if tx.direction == BankTransaction.DIRECTION_IN else -tx.amount


def _live_rows(branch=None, date_to=None):
    qs = (
        BankTransaction.objects.exclude(status=BankTransaction.STATUS_VOIDED)
        .filter(amount__isnull=False)
        .select_related('account')
        .order_by('transaction_date', 'pk')
    )
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)
    rows = list(qs)
    if branch:
        rows = [tx for tx in rows if _account(tx).branch_id == branch]
    return rows


def _unrecorded_transfers(branch, date_to):
    """Transfers with no source account. Since schema v2 every remittance names
    the account the money left, so there are none; kept so the report keeps
    its UNRECORDED line (always zero now)."""
    return []


def _source_link(source_type, source_id):
    return {
        'PaymentRecord': f'/finance/payments/{source_id}/',
        'Remittance': f'/remittance/{source_id}/',
        'CurrencyExchangeIn': '/finance/exchanges/',
        'CurrencyExchangeOut': '/finance/exchanges/',
        'Refund': f'/finance/journal/{source_id}/',
    }.get(source_type)


def fund_flow(*, branch=None, date_from=None, date_to=None):
    """Per-currency fund flow for `branch` (None = all) over [date_from, date_to]."""
    totals = defaultdict(lambda: defaultdict(int))        # line -> currency -> amount
    accounts = {}                                          # key -> {...}
    transactions = []

    def account_entry(key, label, branch_id, currency):
        if key not in accounts:
            accounts[key] = {'label': label, 'branch': branch_id, 'currency': currency,
                             'opening': 0, 'inflow': 0, 'outflow': 0}
        return accounts[key]

    def add(line, currency, amount, acc_entry, in_period, row):
        if not in_period:
            totals['opening'][currency] += amount
            acc_entry['opening'] += amount
            return
        totals[line][currency] += amount
        if amount >= 0:
            acc_entry['inflow'] += amount
        else:
            acc_entry['outflow'] += -amount
        transactions.append({**row, 'line': line, 'currency': currency, 'amount': amount})

    for tx in _live_rows(branch, date_to):
        acc = _account(tx)
        line = CATEGORY_BY_SOURCE.get(tx.source_type, 'other')
        if line == 'opening_rows':
            line = 'opening'   # an opening balance inside the period still opens it
        in_period = not date_from or tx.transaction_date >= date_from
        key = acc.token
        entry = account_entry(key, str(acc), acc.branch_id, tx.currency)
        add(line, tx.currency, _signed(tx), entry, in_period, {
            'date': tx.transaction_date.isoformat(), 'account': str(acc),
            'source_type': tx.source_type, 'reference': tx.reference,
            'link': _source_link(tx.source_type, tx.source_id),
        })

    for rem in _unrecorded_transfers(branch, date_to):
        in_period = not date_from or rem.date >= date_from
        entry = account_entry('unrecorded:IDR', UNRECORDED, 'sby', 'IDR')
        add('sent_hq', 'IDR', -int(rem.amount_idr), entry, in_period, {
            'date': rem.date.isoformat(), 'account': UNRECORDED, 'source_type': 'Remittance',
            'reference': rem.remittance_number, 'link': f'/remittance/{rem.pk}/',
        })

    currencies = sorted({c for line in totals.values() for c in line} | {a['currency'] for a in accounts.values()},
                        key=lambda c: (c != 'IDR', c != 'USD', c))
    for c in currencies:
        totals['closing'][c] = sum(totals[k][c] for k, _ in LINES if k != 'closing')
    account_rows = []
    for a in sorted(accounts.values(), key=lambda a: (a['currency'], a['label'])):
        a['closing'] = a['opening'] + a['inflow'] - a['outflow']
        account_rows.append(a)
    return {
        'currencies': currencies,
        'lines': [{'key': k, 'label': label, 'values': {c: totals[k][c] for c in currencies}} for k, label in LINES],
        'accounts': account_rows,
        'transactions': transactions,
    }


# ── Realized FX profit ─────────────────────────────────────────────────

@dataclass
class _Pool:
    """Client money held in one currency and the SAR it still owes HQ."""
    amount: Decimal = Decimal(0)
    sar: Decimal = Decimal(0)

    @property
    def rate(self):
        return self.amount / self.sar if self.sar > 0 else None


def _branch_events(branch, date_to):
    """Chronological client-money events of one branch that move the pools."""
    from ..models.currency_exchange import CurrencyExchange
    from ..models.payment import PaymentRecord
    from ..models.remittance import Remittance

    events = []
    for p in (PaymentRecord.objects.filter(status__in=PaymentRecord.EFFECTIVE_STATUSES).exclude(receiving_account__currency='SAR')
              .select_related('receiving_account')):
        if p.receiving_branch_code == branch and (not date_to or p.payment_date <= date_to):
            events.append((p.payment_date, 0, p.pk, 'payment', p))
    for ex in CurrencyExchange.objects.filter(status=CurrencyExchange.STATUS_ACTIVE).select_related('from_account', 'to_account'):
        # A same-currency transfer leaves the currency pools as they were.
        if ex.from_currency == ex.to_currency:
            continue
        if ex.from_account.branch_id == branch and (not date_to or ex.exchange_date <= date_to):
            events.append((ex.exchange_date, 1, ex.pk, 'exchange', ex))
    for tx in BankTransaction.objects.filter(source_type='Refund').exclude(status=BankTransaction.STATUS_VOIDED).select_related('account'):
        if _account(tx).branch_id == branch and tx.currency != 'SAR' and (not date_to or tx.transaction_date <= date_to):
            events.append((tx.transaction_date, 2, tx.pk, 'refund', tx))
    for rem in Remittance.objects.select_related('from_account'):
        sender = rem.from_account.branch_id if rem.from_account_id else 'sby'
        if sender == branch and (not date_to or rem.date <= date_to):
            events.append((rem.date, 3, rem.pk, 'remittance', rem))
    events.sort(key=lambda e: e[:3])
    return events


def _take(pool, sar):
    """Remove `sar` of obligation at the pool's average cost; returns
    (sar actually covered, amount of currency it cost)."""
    covered = min(Decimal(sar), pool.sar) if pool.sar > 0 else Decimal(0)
    cost = pool.amount * covered / pool.sar if pool.sar > 0 else Decimal(0)
    pool.sar -= covered
    pool.amount -= cost
    return covered, cost


def _replay(branch, *, date_from=None, date_to=None, stop_before=None):
    """Putar ulang uang client cabang menurut urutan waktu. Mengembalikan
    (pools, transfers). `stop_before`: id setoran — berhenti tepat sebelum
    setoran itu (posisi uang client yang dipakai setoran tersebut)."""
    from . import queries
    pools = defaultdict(_Pool)
    transfers = []
    events = _branch_events(branch, date_to)
    # SAR actually sent per transfer, in one query.
    sent_map = queries.remittance_sent_map([o.pk for *_x, k, o in events if k == 'remittance'])
    for _d, _o, _pk, kind, obj in events:
        if kind == 'payment':
            pool = pools[obj.currency]
            pool.amount += Decimal(obj.amount)
            pool.sar += Decimal(obj.amount_sar)
        elif kind == 'exchange':
            src, dst = pools[obj.from_currency], pools[obj.to_currency]
            share = min(Decimal(obj.amount_out) / src.amount, Decimal(1)) if src.amount > 0 else Decimal(0)
            sar_moved = src.sar * share
            src.amount -= Decimal(obj.amount_out) * share
            src.sar -= sar_moved
            dst.amount += Decimal(obj.amount_in) * share   # only the client-money part joins the pool
            dst.sar += sar_moved
        elif kind == 'refund':
            pool = pools[obj.currency]
            pool.amount = max(pool.amount - Decimal(obj.amount), Decimal(0))
            pool.sar = max(pool.sar - Decimal(obj.amount_sar), Decimal(0))
        elif kind == 'remittance':
            if stop_before is not None and obj.pk == stop_before:
                break
            sar = obj.expected_sar or int(sent_map.get(obj.pk, 0))
            if not sar:
                continue
            pool = pools['IDR']
            rate = pool.rate
            if obj.is_legacy and obj.original_amount:
                # Setoran lama: rupiah client di baliknya diisi user.
                covered = min(Decimal(sar), pool.sar)
                pool.sar -= covered
                pool.amount = max(pool.amount - Decimal(obj.original_amount), Decimal(0))
                cost, covered = Decimal(obj.original_amount), Decimal(sar)
                rate = cost / Decimal(sar)
            else:
                covered, cost = _take(pool, sar)
            if date_from and obj.date < date_from:
                continue
            idr_sent = obj.amount_idr
            profit = None
            if obj.is_legacy and not obj.original_amount:
                pass  # tidak dihitung sampai nominal original diisi
            elif idr_sent is not None and covered > 0:
                sent_for_covered = Decimal(idr_sent) * covered / Decimal(sar)
                profit = int((cost - sent_for_covered).quantize(Decimal('1')))
            transfers.append({
                'id': obj.pk, 'remittance_number': obj.remittance_number, 'date': obj.date.isoformat(),
                'sar': int(sar), 'idr_sent': idr_sent,
                'avg_rate': float(rate.quantize(Decimal('0.01'))) if rate else None,
                'send_rate': float(obj.exchange_rate) if obj.exchange_rate else None,
                'cost_idr': int(cost.quantize(Decimal('1'))),
                'profit_idr': profit,
                'fully_covered': covered == Decimal(sar),
                'is_legacy': obj.is_legacy,
                'original_amount': obj.original_amount,
            })
    return pools, transfers


def idr_pool(branch='sby', *, before=None):
    """Uang client rupiah cabang yang belum disetor, dan kurs asalnya:
    {'amount', 'sar', 'rate'}. `before`: id setoran — posisi tepat sebelum
    setoran itu (untuk form edit); tanpa itu, posisi sekarang."""
    pools, _ = _replay(branch, stop_before=before)
    pool = pools['IDR']
    return {
        'amount': int(pool.amount.quantize(Decimal('1'))),
        'sar': int(pool.sar.quantize(Decimal('1'))),
        'rate': float(pool.rate.quantize(Decimal('0.0001'))) if pool.rate else None,
    }


def branch_expenses_idr(branch, *, date_from=None, date_to=None):
    """Rupiah the branch paid for its expenses in the period (by payment date)."""
    from django.db.models import Sum
    from ..models.expense import Expense, ExpensePayment
    qs = ExpensePayment.objects.filter(
        status=ExpensePayment.STATUS_PAID, expense__status=Expense.STATUS_PAID,
        expense__branch_id=branch, source_account__currency='IDR',
    )
    if date_from:
        qs = qs.filter(payment_date__gte=date_from)
    if date_to:
        qs = qs.filter(payment_date__lte=date_to)
    return int(qs.aggregate(t=Sum('amount'))['t'] or 0)


def net_profit(fx):
    """The branch's profit in rupiah: realized FX profit on transfers to HQ.

    Expenses do not reduce it: the branch fronts them and head office pays
    them back per claim (user, 2026-10-19; replaces "laba cabang = sisa uang
    bersih" of 2026-09-29). None while no transfer in the period has a
    priced FX profit."""
    if fx['transfers'] and fx['unpriced'] == len(fx['transfers']):
        return None
    return fx['total_profit_idr']


def fx_profit(*, branch='sby', date_from=None, date_to=None):
    """Realized FX profit per transfer to HQ (IDR) for `branch`.

    Pools per currency hold client money at cost with the SAR it owes. A client
    payment adds to its currency's pool; an exchange moves the matching share
    of obligation from one pool to another at the exchanged amount; a refund
    removes money and obligation; a transfer to HQ consumes SAR from the IDR
    pool at its average rate — profit = that cost − rupiah actually sent.
    Setoran lama dihitung dari nominal original yang diisi user, atau tidak
    dihitung (profit None) selama kosong."""
    pools, transfers = _replay(branch, date_from=date_from, date_to=date_to)
    held = {c: {'amount': int(p.amount.quantize(Decimal('1'))), 'sar': int(p.sar.quantize(Decimal('1')))}
            for c, p in pools.items() if p.amount or p.sar}
    return {
        'transfers': transfers,
        'total_profit_idr': sum(t['profit_idr'] or 0 for t in transfers),
        # Transfers whose profit cannot be computed yet (old deposit with no
        # original amount): the total leaves them out, so say how many.
        'unpriced': sum(1 for t in transfers if t['profit_idr'] is None),
        'client_money_held': held,
    }
