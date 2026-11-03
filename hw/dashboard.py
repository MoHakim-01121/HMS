"""Dashboard data: the three dashboards on the Record View HMS canvas
(Manager "gaya D", Finance, Administrator; built 2026-10-17).

Each builder reads only the modules the user may view, over the branches the
user is looking at. Head office looking at head office (Pusat picked, or no
picker) sees every branch: the dashboard is the one page that sums branches
instead of showing Pusat's own records.

Money is read from the same sources as the reports it links to: AR from
queries.ar_aging (AR Aging), balances from the accounts overview (Bank and
Cash), money in/out and branch profit from fund_flow (Fund Flow).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone

from .branch_scope import active_hq, branch_codes, covers_all, scope
from .finance import fund_flow, queries
from .models import ConfirmationLetter, Invoice
from .models.activity import ActivityLog
from .models.branch import Branch
from .models.client import Client
from .models.client_money import ApprovalStatus, ClientRefund, ClientTransfer
from .models.confirmation import ReservationStatus
from .models.expense import Expense
from .models.payment import PaymentRecord
from .models.period import FinancialPeriod, Season
from .models.reconciliation import BankStatementLine
from .models.remittance import Remittance
from .permissions import ADMIN_SLUG, can, get_role

CANCELLED = ReservationStatus.CANCELLED
TENTATIVE = ReservationStatus.TENTATIVE
# Staff cash given more than this many days ago and not spent since is "held long".
STAFF_CASH_DAYS = 14
INACTIVE_USER_DAYS = 30
ROWS = 8


def view_codes(user):
    """Branch codes the dashboard reads, or None for every branch."""
    if covers_all(user) and active_hq(user):
        return None
    return branch_codes(user)


def ops_branches(codes):
    """Branches that sell and collect (not head office) among `codes`."""
    qs = Branch.objects.filter(is_active=True, is_hq=False)
    if codes is not None:
        qs = qs.filter(code__in=codes)
    return list(qs.order_by('name'))


def _days(d, today):
    if isinstance(d, datetime):
        d = timezone.localtime(d).date()
    return (today - d).days if d else 0


def _cl_value(cl):
    nights = cl.num_nights or 1
    return int(round(sum(r.price * r.quantity * nights for r in cl.rooms.all())))


def _cl_rooms(cl):
    return sum(r.quantity for r in cl.rooms.all())


# ── Bookings ────────────────────────────────────────────────────────────

def _live_cls(cls):
    return cls.exclude(reservation_status=CANCELLED)


def _paid_map(cls_list):
    return queries.cl_paid_sar_map(cls_list) if cls_list else {}


def _cl_row(cl, today, paid=None):
    inv = cl.invoice
    return {
        'id': cl.pk, 'number': cl.confirmation_number, 'client': cl.guest_name, 'client_id': cl.client_id,
        'hotel': cl.hotel_name, 'check_in': cl.check_in.isoformat(), 'in_days': (cl.check_in - today).days,
        'rooms': _cl_rooms(cl), 'status': cl.reservation_status, 'value': _cl_value(cl),
        'invoice': {'id': inv.pk, 'number': inv.invoice_number} if inv else None,
        'paid': paid,
    }


def checkins_week(cls, today):
    """CLs checking in over the next 7 days, and today's movements."""
    end = today + timedelta(days=6)
    live = _live_cls(cls)
    qs = list(live.filter(check_in__gte=today, check_in__lte=end).with_parties().with_invoice()
              .prefetch_related('rooms').order_by('check_in', 'confirmation_number'))
    paid = _paid_map(qs)
    return {
        'today': {
            'in': sum(1 for cl in qs if cl.check_in == today),
            'out': live.filter(check_out=today).count(),
            'house': live.filter(check_in__lt=today, check_out__gt=today).count(),
        },
        'rows': [_cl_row(cl, today, paid.get(cl.pk, 0)) for cl in qs],
        'until': end.isoformat(),
    }


def uninvoiced(cls, today, limit=ROWS):
    """CLs still to bill: not cancelled, not on an invoice, not checked out."""
    qs = _live_cls(cls).uninvoiced().filter(check_out__gte=today).with_parties().prefetch_related('rooms').order_by('check_in')
    rows = list(qs)
    return {'count': len(rows), 'value': sum(_cl_value(cl) for cl in rows),
            'rows': [_cl_row(cl, today) for cl in rows[:limit]]}


def waiting_dp(cls, today, limit=ROWS, days=14):
    """Invoiced CLs checking in within `days` with nothing paid yet."""
    qs = list(_live_cls(cls).invoiced().filter(check_in__gte=today, check_in__lte=today + timedelta(days=days))
              .with_parties().with_invoice().prefetch_related('rooms').order_by('check_in'))
    paid = _paid_map(qs)
    rows = [cl for cl in qs if not paid.get(cl.pk)]
    return {'count': len(rows), 'value': sum(_cl_value(cl) for cl in rows),
            'rows': [_cl_row(cl, today, 0) for cl in rows[:limit]]}


# ── Receivables ─────────────────────────────────────────────────────────

def receivables(clients, today):
    """Open invoices from AR Aging: totals, what is past due, per client."""
    aging = queries.ar_aging(as_of=today, clients=clients)
    invoices = [dict(i, client_id=c['client_id'], client=c['name']) for c in aging['clients'] for i in c['invoices']]
    past = [i for i in invoices if i['days_overdue'] > 0]
    return {
        'total': aging['total'], 'count': len(invoices),
        'past_due': sum(i['amount'] for i in past), 'past_count': len(past),
        'past_clients': len({i['client_id'] for i in past}),
        'clients': aging['clients'], 'past': sorted(past, key=lambda i: -i['days_overdue']),
    }


def overdue_to_chase(rec, limit=ROWS):
    """One row per client with past-due invoices: the oldest of them, the
    client's past-due total, and when someone last drafted a billing message
    for one of them (the AI draft log)."""
    per = {}
    for i in rec['past']:
        c = per.setdefault(i['client_id'], {'client': i['client'], 'client_id': i['client_id'], 'open': 0,
                                            'invoice': i, 'numbers': []})
        c['open'] += i['amount']
        c['numbers'].append(i['invoice_number'])
        if i['days_overdue'] > c['invoice']['days_overdue']:
            c['invoice'] = i
    rows = sorted(per.values(), key=lambda c: -c['invoice']['days_overdue'])[:limit]
    numbers = [n for c in rows for n in c['numbers']]
    last = dict(ActivityLog.objects.filter(model_name__startswith='AI Draft', object_ref__in=numbers)
                .values('object_ref').annotate(t=Max('timestamp')).values_list('object_ref', 't'))
    wa = dict(Client.objects.filter(pk__in=[c['client_id'] for c in rows]).values_list('pk', 'wa'))
    out = []
    for c in rows:
        times = [last[n] for n in c['numbers'] if n in last]
        i = c['invoice']
        out.append({
            'client': c['client'], 'client_id': c['client_id'], 'wa': wa.get(c['client_id']) or '',
            'invoice': {'id': i['id'], 'number': i['invoice_number']}, 'due_date': i['due_date'],
            'late': i['days_overdue'], 'open': c['open'],
            'reminded': timezone.localtime(max(times)).date().isoformat() if times else None,
        })
    return {'clients': len(per), 'total': sum(c['open'] for c in per.values()), 'rows': out}


# ── Money ───────────────────────────────────────────────────────────────

def balances(codes):
    """Today's balance of every account (bank, cash, staff cash): SAR value
    in all, and per currency in the currency and in SAR."""
    from django.db.models import Case, F, IntegerField, When

    from .models.bank_transaction import BankTransaction
    rows = queries.money_accounts_overview(branches=codes)
    ids = [r['id'] for r in rows if r['kind'] != 'staff']
    native = {x['account_id']: x['n'] or 0 for x in BankTransaction.objects.filter(account_id__in=ids)
              .exclude(status=BankTransaction.STATUS_VOIDED).values('account_id')
              .annotate(n=Sum(Case(When(direction=BankTransaction.DIRECTION_IN, then=F('amount')),
                                   default=-F('amount'), output_field=IntegerField())))}
    per = defaultdict(lambda: {'native': 0, 'sar': 0})
    seen = set()
    for r in rows:
        c = per[r['currency']]
        if r['kind'] == 'staff':
            c['native'] += r['native_balance']
            c['sar'] += r['book_balance']
            continue
        c['native'] += native.get(r['id'], 0) if r['currency'] != 'SAR' else native.get(r['id'], r['book_balance'])
        # Accounts sharing one ledger share its SAR balance: count it once.
        if r['ledger_account'] not in seen:
            seen.add(r['ledger_account'])
            c['sar'] += r['book_balance']
    order = {'IDR': 0, 'USD': 1, 'SAR': 2}
    cur = [{'ccy': k, **v} for k, v in sorted(per.items(), key=lambda kv: order.get(kv[0], 9))]
    return {'sar': sum(c['sar'] for c in cur), 'currencies': cur,
            'staff': any(r['kind'] == 'staff' for r in rows)}


def _flow_idr(branches, start, end):
    """IDR in and out of `branches` over [start, end] from Fund Flow."""
    tot = defaultdict(int)
    for b in branches:
        flow = fund_flow.fund_flow(branch=b.code, date_from=start, date_to=end)
        for line in flow['lines']:
            tot[line['key']] += line['values'].get('IDR', 0)
    inflow = sum(max(tot[k], 0) for k in ('client_in', 'exchange_in', 'hq_receipts', 'other'))
    outflow = sum(max(-tot[k], 0) for k in ('exchange_out', 'sent_hq', 'operational', 'refund', 'other'))
    return {'in': inflow, 'client_in': max(tot['client_in'], 0), 'out': outflow, 'sent_hq': max(-tot['sent_hq'], 0)}


def not_sent(branches):
    """Client rupiah each branch holds and still owes HQ (Fund Flow's IDR pool)."""
    rows = []
    for b in branches:
        pool = fund_flow.idr_pool(b.code)
        rows.append({'branch': b.code, 'name': b.name, 'idr': pool['amount'], 'sar': pool['sar']})
    last = Remittance.objects.filter(from_account__branch_id__in=[b.code for b in branches]).aggregate(d=Max('date'))['d']
    return {'idr': sum(r['idr'] for r in rows), 'sar': sum(r['sar'] for r in rows), 'rows': rows,
            'last_sent': last.isoformat() if last else None}


# ── Finance queue ───────────────────────────────────────────────────────

def pending_payments(user, codes, today, limit=ROWS):
    qs = (scope(PaymentRecord.objects.filter(status=PaymentRecord.STATUS_PENDING), user, codes=codes)
          .select_related('client', 'invoice', 'receiving_account', 'receiving_account__branch')
          .order_by('created_at'))
    rows = list(qs)
    by_ccy = defaultdict(int)
    for p in rows:
        by_ccy[p.currency] += p.amount
    return {
        'count': len(rows), 'by_ccy': dict(by_ccy),
        'oldest': _days(rows[0].created_at, today) if rows else None,
        'rows': [{
            'id': p.pk, 'number': p.payment_number, 'date': p.payment_date.isoformat(),
            'waiting': _days(p.created_at, today), 'client': p.client.display_name,
            'invoice': {'id': p.invoice_id, 'number': p.invoice.invoice_number} if p.invoice_id else None,
            'amount': p.amount, 'ccy': p.currency, 'sar': p.amount_sar, 'account': str(p.receiving_account),
            'proof': p.proof.url if p.proof else None, 'mine': p.created_by_id == user.pk,
        } for p in rows[:limit]],
    }


def pending_refunds(user, codes):
    refunds = list(scope(ClientRefund.objects.filter(status=ApprovalStatus.PENDING), user, codes=codes)
                   .select_related('created_by', 'client').order_by('created_at'))
    transfers = scope(ClientTransfer.objects.filter(status=ApprovalStatus.PENDING), user, codes=codes).count()
    first = refunds[0] if refunds else None
    return {'count': len(refunds) + transfers, 'refunds': len(refunds), 'transfers': transfers,
            'first': {'id': first.pk, 'number': first.refund_number, 'client_id': first.client_id,
                      'by': first.created_by.get_full_name() or first.created_by.username} if first else None}


def _expense_rows(qs, today, limit):
    rows = list(qs.select_related('created_by', 'spent_by').prefetch_related('lines__receipts', 'lines__category')[:limit])
    out = []
    for e in rows:
        lines = list(e.lines.all())
        files = sum(len(l.receipts.all()) for l in lines) + (1 if e.proof else 0)
        missing = 0 if e.proof else sum(1 for l in lines if not l.receipts.all())
        cat = next((l.category.name for l in lines if getattr(l, 'category', None)), '')
        who = e.spent_by or e.created_by
        out.append({
            'id': e.pk, 'number': e.expense_number, 'title': e.description or (str(e.vendor) if e.vendor_id else e.expense_number),
            'by': who.get_full_name() or who.username, 'date': e.expense_date.isoformat(),
            'submitted': timezone.localtime(e.created_at).date().isoformat(), 'waiting': _days(e.created_at, today),
            'amount': e.total_amount, 'category': cat, 'files': files, 'missing': missing,
        })
    return out


def expenses_to_approve(user, codes, today, limit=ROWS):
    qs = scope(Expense.objects.filter(status=Expense.STATUS_SUBMITTED), user, codes=codes).order_by('created_at')
    total = qs.aggregate(t=Sum('lines__amount'))['t'] or 0
    first = qs.first()
    return {'count': qs.count(), 'total': int(total), 'oldest': _days(first.created_at, today) if first else None,
            'rows': _expense_rows(qs, today, limit)}


def expenses_to_pay(user, codes, today):
    qs = scope(Expense.objects.filter(status=Expense.STATUS_APPROVED), user, codes=codes)
    agg = qs.aggregate(t=Sum('lines__amount'), d=Min('decided_at'))
    return {'count': qs.count(), 'total': int(agg['t'] or 0), 'oldest': _days(agg['d'], today) if agg['d'] else None}


def remittances_in_transit(user, codes):
    rows = scope(Remittance.objects.all(), user, codes=codes).select_related('from_account').pending()
    rows = sorted(rows, key=lambda r: r.date)
    first = rows[0] if rows else None
    return {'count': len(rows), 'first': {'amount': first.amount_sent, 'ccy': first.from_account.currency,
                                          'date': first.date.isoformat()} if first else None}


def unapplied_cash(clients):
    """Client deposits that could settle the client's own open invoices."""
    ids = list(clients.values_list('pk', flat=True))
    credit = {k: v for k, v in queries.client_credit_balances(ids).items() if v > 0}
    if not credit:
        return {'total': 0, 'clients': 0, 'offset': 0}
    owing = {c['client_id'] for c in queries.ar_aging(clients=clients.filter(pk__in=credit))['clients']}
    return {'total': sum(credit.values()), 'clients': len(credit), 'offset': len(owing & set(credit))}


def unreconciled(user, codes):
    qs = scope(BankStatementLine.objects.filter(match__isnull=True), user, codes=codes)
    agg = qs.aggregate(n=Count('id'), d=Min('line_date'))
    top = (qs.values('statement__account_id').annotate(n=Count('id')).order_by('-n').first())
    name = ''
    if top:
        from .models.bank import MoneyAccount
        name = str(MoneyAccount.objects.get(pk=top['statement__account_id']))
    return {'count': agg['n'], 'since': agg['d'].isoformat() if agg['d'] else None, 'account': name}


def previous_period(today):
    """Last month's period while it is still open, and how long since it ended."""
    end = today.replace(day=1) - timedelta(days=1)
    p = FinancialPeriod.objects.filter(date_from__lte=end, date_to__gte=end).first()
    if not p or p.status not in (FinancialPeriod.STATUS_OPEN, FinancialPeriod.STATUS_SOFT_CLOSE):
        return None
    return {'id': p.pk, 'name': p.name, 'month': end.replace(day=1).isoformat(), 'days': (today - end).days,
            'soft': p.status == FinancialPeriod.STATUS_SOFT_CLOSE}


def staff_cash_held(codes, today):
    rows = [r for r in queries._staff_overview(branches=codes)
            if r['native_balance'] > 0 and r['given_on'] and not r['spent_since']
            and (today - date.fromisoformat(r['given_on'])).days > STAFF_CASH_DAYS]
    rows.sort(key=lambda r: r['given_on'])
    by_ccy = defaultdict(int)
    for r in rows:
        by_ccy[r['currency']] += r['native_balance']
    first = rows[0] if rows else None
    return {'count': len(rows), 'by_ccy': dict(by_ccy),
            'first': {'name': first['name'], 'days': (today - date.fromisoformat(first['given_on'])).days} if first else None}


# ── System ──────────────────────────────────────────────────────────────

def system_items(today):
    from axes.models import AccessAttempt
    from django.conf import settings
    now = timezone.now()
    cool = timedelta(hours=settings.AXES_COOLOFF_TIME)
    locked = []
    for a in (AccessAttempt.objects.filter(failures_since_start__gte=settings.AXES_FAILURE_LIMIT,
                                           attempt_time__gte=now - cool).order_by('-attempt_time')):
        if a.username and a.username not in {x['username'] for x in locked}:
            locked.append({'username': a.username, 'failures': a.failures_since_start,
                           'at': timezone.localtime(a.attempt_time).strftime('%H:%M'),
                           'until': timezone.localtime(a.attempt_time + cool).strftime('%H:%M')})
    User = get_user_model()
    cutoff = now - timedelta(days=INACTIVE_USER_DAYS)
    idle = []
    for u in (User.objects.filter(is_active=True).exclude(username__startswith='system.')
              .filter(Q(last_login__lt=cutoff) | Q(last_login__isnull=True, date_joined__lt=cutoff))
              .order_by('last_login')):
        seen = u.last_login or u.date_joined
        idle.append({'id': u.pk, 'name': u.get_full_name() or u.username, 'days': (now - seen).days,
                     'never': u.last_login is None})
    return {'locked': locked, 'idle': idle}


# ── Builders ────────────────────────────────────────────────────────────

def _finance_cues(user, codes, clients, today, branches):
    cues = {}
    if can(user, 'payments', 'view'):
        cues['payments'] = pending_payments(user, codes, today)
        cues['refunds'] = pending_refunds(user, codes)
        cues['unapplied'] = unapplied_cash(clients)
    if can(user, 'expenses', 'view'):
        cues['to_pay'] = expenses_to_pay(user, codes, today)
    if can(user, 'remittance', 'view'):
        cues['transit'] = remittances_in_transit(user, codes)
        cues['not_sent'] = not_sent(branches)
    if can(user, 'bank', 'view'):
        cues['unreconciled'] = unreconciled(user, codes)
        cues['staff'] = staff_cash_held(codes, today)
    if can(user, 'periods', 'view'):
        cues['period'] = previous_period(today)
    return cues


# ── Home (Manager dashboard, HMS Dashboard canvas "ManagerHomlu") ───────
#
# Sales and room nights count by the date a CL was sold (created_at); only Top
# hotels reads the nights stayed. A running month compares with the same days
# of the month before ("1 to 19 Sep"); a past month with the whole month
# before; a season with the season before up to the same day.

SPARK_CUTS = 6
HERO_BARS = 10


def _local(dt):
    return timezone.localtime(dt).date()


def _span_label(start, end):
    if start.day == 1 and end == (start + relativedelta(months=1, days=-1)):
        return start.strftime('%B')
    return f"{start.day} to {end.day} {end.strftime('%b')}" if start.month == end.month else \
        f"{start.strftime('%-d %b')} to {end.strftime('%-d %b')}"


def home_period(today, month=None, season=False):
    """The window the dashboard reads and the one it compares with."""
    if season:
        s = Season.objects.filter(date_from__lte=today, date_to__gte=today).first()
        if s:
            end = min(today, s.date_to)
            prev = Season.objects.filter(date_to__lt=s.date_from).order_by('-date_from').first()
            p_end = min(prev.date_from + (end - s.date_from), prev.date_to) if prev else None
            return {'kind': 'season', 'label': s.name, 'start': s.date_from, 'end': end, 'last': s.date_to,
                    'prev_start': prev.date_from if prev else None, 'prev_end': p_end,
                    'prev_label': prev.name if prev else None, 'season': s, 'prev_season': prev}
    month = (month or today).replace(day=1)
    if month > today:
        month = today.replace(day=1)
    last = month + relativedelta(months=1, days=-1)
    prev = month - relativedelta(months=1)
    prev_last = month - timedelta(days=1)
    if month == today.replace(day=1):
        end = today
        p_end = min(prev + timedelta(days=today.day - 1), prev_last)
    else:
        end, p_end = last, prev_last
    return {'kind': 'month', 'label': month.strftime('%B'), 'start': month, 'end': end, 'last': last,
            'prev_start': prev, 'prev_end': p_end, 'prev_label': _span_label(prev, p_end),
            'running': end < last}


def _cuts(start, end, n):
    days = (end - start).days
    return [start + timedelta(days=round(days * (i + 1) / n)) for i in range(n)]


def _sold(cls, start, end):
    return list(_live_cls(cls).filter(created_at__date__gte=start, created_at__date__lte=end)
                .prefetch_related('rooms').only('id', 'created_at', 'check_in', 'check_out', 'client_id', 'hotel_id'))


def _nights_sold(cl):
    return _cl_rooms(cl) * (cl.num_nights or 0)


def _nights_in(cl, start, end):
    a, b = max(cl.check_in, start), min(cl.check_out, end + timedelta(days=1))
    return max((b - a).days, 0) * _cl_rooms(cl)


def _cum(rows, cuts, when, amount):
    return [sum(amount(r) for r in rows if when(r) <= c) for c in cuts]


def _pct_delta(cur, prev):
    if not prev:
        return None
    return round((cur - prev) * 100 / prev)


def _sales_side(cls, start, end):
    if not start:
        return None
    sold = _sold(cls, start, end)
    cuts = _cuts(start, end, SPARK_CUTS)
    cancelled = list(cls.filter(reservation_status=CANCELLED, updated_at__date__gte=start, updated_at__date__lte=end)
                     .prefetch_related('rooms').only('id', 'updated_at', 'check_in', 'check_out'))
    created = lambda cl: _local(cl.created_at)
    return {
        'value': sum(_cl_value(cl) for cl in sold), 'cl': len(sold),
        'rn': sum(_nights_sold(cl) for cl in sold),
        'cancelled': len(cancelled), 'lost': sum(_cl_value(cl) for cl in cancelled),
        'spark': {
            'value': _cum(sold, cuts, created, _cl_value),
            'cl': _cum(sold, cuts, created, lambda cl: 1),
            'rn': _cum(sold, cuts, created, _nights_sold),
            'cancelled': _cum(cancelled, cuts, lambda cl: _local(cl.updated_at), lambda cl: 1),
        },
        'bars': _cum(sold, _cuts(start, end, HERO_BARS), created, _cl_value),
    }


def _profit(branches, start, end):
    if not start or not branches:
        return None
    fx = exp = 0
    priced = False
    for b in branches:
        f = fund_flow.fx_profit(branch=b.code, date_from=start, date_to=end)
        if fund_flow.net_profit(f) is not None:
            priced = True
        fx += f['total_profit_idr'] or 0
        exp += fund_flow.branch_expenses_idr(b.code, date_from=start, date_to=end) or 0
    # Expenses are shown beside the profit, never deducted: Pusat pays them back.
    return {'fx': fx, 'expenses': exp, 'profit': fx if priced else None}


def _season_months(today, per):
    """Twelve months of the season (or the twelve to this month), CL sold in
    each, and the same month of the span before."""
    s = per.get('season') or Season.objects.filter(date_from__lte=today, date_to__gte=today).first()
    start = s.date_from.replace(day=1) if s else today.replace(day=1) - relativedelta(months=11)
    prev_s = Season.objects.filter(date_to__lt=s.date_from).order_by('-date_from').first() if s else None
    prev_start = prev_s.date_from.replace(day=1) if prev_s else start - relativedelta(years=1)
    return s, start, prev_start, prev_s


def sold_per_month(cls, today, per):
    s, start, prev_start, prev_s = _season_months(today, per)
    rows = (_live_cls(cls).filter(created_at__date__gte=prev_start, created_at__date__lt=start + relativedelta(months=12))
            .values_list('created_at', flat=True))
    cur, ly = [0] * 12, [0] * 12
    for dt in rows:
        d = _local(dt).replace(day=1)
        i = (d.year - start.year) * 12 + d.month - start.month
        if 0 <= i < 12:
            cur[i] += 1
        j = (d.year - prev_start.year) * 12 + d.month - prev_start.month
        if 0 <= j < 12:
            ly[j] += 1
    months = [start + relativedelta(months=i) for i in range(12)]
    now_i = next((i for i, m in enumerate(months) if m == today.replace(day=1)), 11)
    sel = None if per['kind'] == 'season' else next((i for i, m in enumerate(months) if m == per['start']), None)
    # Months before the first CL in HMS are not "nothing sold": nothing was
    # recorded yet. The chart marks them rather than drawing empty bars.
    first = _live_cls(cls).aggregate(m=Min('created_at'))['m']
    first_i = 0
    if first:
        f = _local(first).replace(day=1)
        first_i = max(0, min(12, (f.year - start.year) * 12 + f.month - start.month))
    return {
        'before_hms': first_i,
        'season': s.name if s else None, 'prev_season': prev_s.name if prev_s else None,
        'has_ly': any(ly),
        'months': [{'key': m.isoformat(), 'cur': cur[i] if i <= now_i else None, 'ly': ly[i]} for i, m in enumerate(months)],
        'now': now_i, 'selected': sel,
    }


def collected(invoices, per, today):
    """Hotel invoices issued in the window: billed, paid, and the rest split
    into not due yet and past due."""
    invs = list(invoices.filter(invoice_type='hotel', issued_date__gte=per['start'], issued_date__lte=per['end']).with_lines())
    paid_map = queries.invoice_paid_map([inv.pk for inv in invs])
    billed = paid = past = 0
    for inv in invs:
        b = inv.total_sar
        p = min(paid_map.get(inv.pk, 0), b)
        billed += b
        paid += p
        if inv.due_date and inv.due_date < today:
            past += b - p
    return {'billed': billed, 'paid': paid, 'past_due': past, 'not_due': billed - paid - past,
            'pct': round(paid * 100 / billed) if billed else None, 'count': len(invs)}


def _checkin_status(row):
    if row['status'] == TENTATIVE:
        return 'tentative'
    if not row['invoice']:
        return 'uninvoiced'
    if not row['paid']:
        return 'no_dp'
    return 'paid' if row['paid'] >= row['value'] else 'partial'


def due_this_week(user, codes, today):
    """Hotel invoices falling due in the next 7 days with money still owed:
    what the bell's "due in N days" warns about."""
    qs = scope(Invoice.objects.all(), user, codes=codes).filter(
        invoice_type='hotel', due_date__gte=today, due_date__lte=today + timedelta(days=7))
    rows = [inv for inv in qs.with_lines().order_by('due_date') if inv.remaining_sar > 0]
    return {'count': len(rows), 'value': round(sum(inv.remaining_sar for inv in rows)),
            'first': {'date': rows[0].due_date.isoformat(), 'client': rows[0].customer_name} if rows else None}


def _todo(user, codes, cls, clients, today, rec, mine=False):
    """What waits today, most urgent first. `mine`: a staff member's list,
    which also carries today's check-ins and the invoices due this week, so it
    tells the same story as the bell (2026-10-22)."""
    items = []
    if mine and can(user, 'cl', 'view'):
        arriving = list(_live_cls(cls).filter(check_in=today).with_parties().order_by('confirmation_number'))
        if arriving:
            items.append({'key': 'checkin_today', 'count': len(arriving), 'amount': None, 'ccy': None,
                          'first': arriving[0].guest_name, 'url': '/calendar/'})
    if mine and can(user, 'invoice', 'view'):
        due = due_this_week(user, codes, today)
        if due['count']:
            items.append({'key': 'due_week', 'count': due['count'], 'amount': due['value'], 'ccy': 'SAR',
                          'nearest': due['first'], 'url': '/invoice/'})
    if rec is not None and rec['past_count']:
        oldest = rec['past'][0]['days_overdue'] if rec['past'] else 0
        items.append({'key': 'past_due', 'count': rec['past_count'], 'amount': rec['past_due'], 'ccy': 'SAR',
                      'clients': rec['past_clients'], 'oldest': oldest, 'url': '/finance/ar-aging/'})
    if can(user, 'cl', 'view') and can(user, 'invoice', 'view'):
        dp = waiting_dp(cls, today, limit=1)
        if dp['count']:
            r = dp['rows'][0]
            items.append({'key': 'no_dp', 'count': dp['count'], 'amount': dp['value'], 'ccy': 'SAR',
                          'nearest': {'date': r['check_in'], 'client': r['client']}, 'url': '/cl/'})
    if can(user, 'cl', 'view'):
        tq = list(_live_cls(cls).filter(reservation_status=TENTATIVE, check_in__gte=today,
                                        check_in__lte=today + timedelta(days=14)).with_parties()
                  .prefetch_related('rooms').order_by('check_in'))
        if tq:
            items.append({'key': 'tentative', 'count': len(tq), 'amount': sum(_cl_value(cl) for cl in tq), 'ccy': 'SAR',
                          'nearest': {'date': tq[0].check_in.isoformat(), 'client': tq[0].guest_name}, 'url': '/cl/'})
    if can(user, 'cl', 'view') and can(user, 'invoice', 'view'):
        un = uninvoiced(cls, today, limit=1)
        if un['count']:
            r = un['rows'][0]
            items.append({'key': 'uninvoiced', 'count': un['count'], 'amount': un['value'], 'ccy': 'SAR',
                          'nearest': {'date': r['check_in'], 'client': r['client']}, 'url': '/invoice/'})
    if can(user, 'expenses', 'approve'):
        ex = expenses_to_approve(user, codes, today, limit=ROWS)
        if ex['count']:
            names = sorted({r['by'] for r in ex['rows']})
            items.append({'key': 'expenses', 'count': ex['count'], 'amount': ex['total'], 'ccy': 'IDR',
                          'by': names[:3], 'url': '/finance/expenses/'})
    if can(user, 'payments', 'approve'):
        rf = pending_refunds(user, codes)
        if rf['count']:
            # Refunds and deposit transfers are approved on the client's ledger.
            url = f"/finance/clients/{rf['first']['client_id']}/statement/" if rf['first'] else '/finance/statements/'
            items.append({'key': 'refunds', 'count': rf['count'], 'amount': None, 'ccy': None,
                          'first': rf['first'], 'url': url})
    return items


def _top(cls, today, per):
    """Clients by booked value and hotels by room nights over the season (or
    twelve months), each with its change against the span before."""
    s, start, prev_start, prev_s = _season_months(today, per)
    end = today
    span = end - start
    p_end = prev_start + span

    def by_client(a, b):
        out = defaultdict(lambda: {'n': 0, 'val': 0})
        for cl in _sold(cls, a, b):
            out[cl.client_id]['n'] += 1
            out[cl.client_id]['val'] += _cl_value(cl)
        return out

    def by_hotel(a, b):
        out = defaultdict(int)
        for cl in _live_cls(cls).filter(check_in__lte=b, check_out__gt=a).prefetch_related('rooms').only('id', 'hotel_id', 'check_in', 'check_out'):
            out[cl.hotel_id] += _nights_in(cl, a, b)
        return out

    cur_c, prev_c = by_client(start, end), by_client(prev_start, p_end)
    names = {c.pk: c.display_name for c in Client.objects.filter(pk__in=list(cur_c))}
    clients = sorted(({'id': k, 'name': names.get(k, ''), 'cl': v['n'], 'val': v['val'],
                       'chg': None if k not in prev_c else _pct_delta(v['val'], prev_c[k]['val']),
                       'new': k not in prev_c} for k, v in cur_c.items()), key=lambda r: -r['val'])[:5]
    from .models.hotel import Hotel
    cur_h, prev_h = by_hotel(start, end), by_hotel(prev_start, p_end)
    hinfo = {h.pk: h for h in Hotel.objects.filter(pk__in=list(cur_h))}
    hotels = sorted(({'id': k, 'name': hinfo[k].name, 'city': hinfo[k].get_city_display(), 'rn': v,
                      'chg': None if k not in prev_h else _pct_delta(v, prev_h[k]),
                      'new': k not in prev_h} for k, v in cur_h.items() if v and k in hinfo), key=lambda r: -r['rn'])[:5]
    return {'season': s.name if s else None, 'clients': clients, 'hotels': hotels, 'has_prev': bool(prev_s)}


def _money_now(user, codes, branches, today):
    out = {}
    accounts = [r for r in queries.money_accounts_overview(branches=codes)]
    bal = balances(codes)
    out['cash'] = {'sar': bal['sar'], 'accounts': sum(1 for r in accounts if r['kind'] != 'staff')}
    staff = [r for r in queries._staff_overview(branches=codes) if r['native_balance'] > 0]
    oldest = min((r['given_on'] for r in staff if r['given_on']), default=None)
    out['staff'] = {'sar': sum(r['book_balance'] for r in staff), 'people': len(staff),
                    'oldest': (today - date.fromisoformat(oldest)).days if oldest else None}
    pq = scope(PaymentRecord.objects.filter(status=PaymentRecord.STATUS_PENDING), user, codes=codes)
    agg = pq.aggregate(n=Count('id'), t=Sum('amount_sar'), d=Min('created_at'))
    out['pending'] = {'count': agg['n'], 'sar': agg['t'] or 0, 'oldest': _days(agg['d'], today) if agg['d'] else None}
    if branches and can(user, 'remittance', 'view'):
        ns = not_sent(branches)
        out['not_sent'] = {'idr': ns['idr'], 'last_sent': ns['last_sent']}
    return out


def _by_branch(user, cls, clients, rec, branches, per):
    # Profit is a finance figure: without Statements access the column stays empty.
    finance_view = can(user, 'statements', 'view')
    profits = {b.code: _profit([b], per['start'], per['end']) for b in branches} if finance_view else {}
    sent = {r['branch']: r['idr'] for r in not_sent(branches)['rows']} if can(user, 'remittance', 'view') else {}
    owner = dict(clients.values_list('pk', 'owner_branch_id'))
    rows = []
    for b in branches:
        sold = _sold(cls.filter(client__owner_branch=b.code), per['start'], per['end'])
        past = sum(i['amount'] for i in rec['past'] if owner.get(i['client_id']) == b.code) if rec else None
        rows.append({'code': b.code, 'name': b.name, 'is_hq': b.is_hq, 'cl': len(sold),
                     'value': sum(_cl_value(cl) for cl in sold), 'past_due': past,
                     'not_sent': sent.get(b.code), 'profit': (profits.get(b.code) or {}).get('profit')})
    return rows


# ── Finance, Administrator, Staff and Viewer dashboards (HMS Dashboard canvas
#    artboards Finance, Admin and Staff, built 2026-10-20). Same period bar and
#    patterns as the Manager one; each block still needs its module.

def _received(user, codes, start, end):
    """Confirmed client payments in [start, end], SAR, with the running total
    at the spark's cuts."""
    if not start:
        return None
    rows = list(scope(PaymentRecord.objects.filter(status=PaymentRecord.STATUS_CONFIRMED,
                                                   payment_date__gte=start, payment_date__lte=end), user, codes=codes)
                .values_list('payment_date', 'amount_sar'))
    cuts = _cuts(start, end, SPARK_CUTS)
    return {'sar': sum(a for _, a in rows), 'count': len(rows),
            'spark': [sum(a for d, a in rows if d <= c) for c in cuts]}


def _accounts(codes):
    """Bank and cash accounts with today's balance in their own currency."""
    from django.db.models import Case, F, IntegerField, When

    from .models.bank_transaction import BankTransaction
    rows = [r for r in queries.money_accounts_overview(branches=codes) if r['kind'] != 'staff' and r.get('is_active', True)]
    native = {x['account_id']: x['n'] or 0 for x in BankTransaction.objects.filter(account_id__in=[r['id'] for r in rows])
              .exclude(status=BankTransaction.STATUS_VOIDED).values('account_id')
              .annotate(n=Sum(Case(When(direction=BankTransaction.DIRECTION_IN, then=F('amount')),
                                   default=-F('amount'), output_field=IntegerField())))}
    return [{'id': r['id'], 'kind': r['kind'], 'name': r.get('name') or '', 'ccy': r['currency'],
             'native': native.get(r['id'], 0) if r['currency'] != 'SAR' else native.get(r['id'], r['book_balance'])}
            for r in rows]


def _flow_months(branches, today, n=6):
    """Money in and out of the branches' accounts per month, IDR, the last
    `n` months to this one (Fund Flow)."""
    out = []
    first = today.replace(day=1) - relativedelta(months=n - 1)
    for i in range(n):
        m = first + relativedelta(months=i)
        f = _flow_idr(branches, m, min(today, m + relativedelta(months=1, days=-1)))
        out.append({'key': m.isoformat(), 'in': f['in'], 'out': f['out']})
    return out


def _pending_agg(user, codes, today):
    qs = scope(PaymentRecord.objects.filter(status=PaymentRecord.STATUS_PENDING), user, codes=codes)
    agg = qs.aggregate(n=Count('id'), t=Sum('amount_sar'), d=Min('created_at'))
    return {'count': agg['n'], 'sar': agg['t'] or 0, 'oldest': _days(agg['d'], today) if agg['d'] else None}


def _finance_todo(user, codes, cues, today):
    """Finance's queue, most urgent first; each row opens the list to work it."""
    items = []
    if 'payments' in cues and can(user, 'payments', 'approve'):
        p = _pending_agg(user, codes, today)
        if p['count']:
            items.append({'key': 'payments', 'count': p['count'], 'amount': p['sar'], 'ccy': 'SAR',
                          'oldest': p['oldest'], 'url': '/finance/payments/?status=pending'})
        rf = cues['refunds']
        if rf['count']:
            url = f"/finance/clients/{rf['first']['client_id']}/statement/" if rf['first'] else '/finance/statements/'
            items.append({'key': 'refunds', 'count': rf['count'], 'amount': None, 'ccy': None, 'first': rf['first'], 'url': url})
    if cues.get('to_pay', {}).get('count'):
        x = cues['to_pay']
        items.append({'key': 'to_pay', 'count': x['count'], 'amount': x['total'], 'ccy': 'IDR', 'oldest': x['oldest'],
                      'url': '/finance/expenses/?status=approved'})
    if cues.get('not_sent', {}).get('idr', 0) > 0:
        items.append({'key': 'not_sent', 'count': 1, 'amount': cues['not_sent']['idr'], 'ccy': 'IDR',
                      'last_sent': cues['not_sent']['last_sent'], 'url': '/remittance/'})
    if cues.get('transit', {}).get('count'):
        x = cues['transit']
        items.append({'key': 'transit', 'count': x['count'], 'amount': x['first']['amount'] if x['count'] == 1 else None,
                      'ccy': x['first']['ccy'] if x['count'] == 1 else None, 'since': x['first']['date'], 'url': '/remittance/'})
    if cues.get('unreconciled', {}).get('count'):
        x = cues['unreconciled']
        items.append({'key': 'unreconciled', 'count': x['count'], 'amount': None, 'ccy': None,
                      'account': x['account'], 'since': x['since'], 'url': '/finance/reconciliation/'})
    if cues.get('staff', {}).get('count'):
        x = cues['staff']
        items.append({'key': 'staff_held', 'count': x['count'], 'amount': None, 'ccy': None,
                      'first': x['first'], 'url': '/finance/bank-accounts/'})
    if cues.get('period'):
        p = cues['period']
        items.append({'key': 'period', 'count': 1, 'amount': None, 'ccy': None, 'month': p['month'],
                      'days': p['days'], 'url': '/finance/periods/'})
    return items


def _finance(user, today, per, codes, branches, clients):
    out = {}
    cues = _finance_cues(user, codes, clients, today, branches)
    rec = receivables(clients, today) if can(user, 'invoice', 'view') else None
    if can(user, 'payments', 'view'):
        out['received'] = {'cur': _received(user, codes, per['start'], per['end']),
                           'prev': _received(user, codes, per['prev_start'], per['prev_end'])}
        out['pay'] = pending_payments(user, codes, today, limit=5)
        out['deposits'] = cues['unapplied']
    if can(user, 'bank', 'view'):
        bal = balances(codes)
        staff = [r for r in queries._staff_overview(branches=codes) if r['native_balance'] > 0]
        oldest = min((r['given_on'] for r in staff if r['given_on']), default=None)
        out['cash'] = {'sar': bal['sar'], 'currencies': bal['currencies'], 'accounts': _accounts(codes),
                       'staff': {'sar': sum(r['book_balance'] for r in staff), 'people': len(staff),
                                 'oldest': (today - date.fromisoformat(oldest)).days if oldest else None},
                       'unreconciled': cues.get('unreconciled')}
    if can(user, 'statements', 'view') and branches:
        flow_end = per['end']
        out['flow'] = {'months': _flow_months(branches, today),
                       'cur': _flow_idr(branches, per['start'], flow_end),
                       'prev': _flow_idr(branches, per['prev_start'], per['prev_end']) if per['prev_start'] else None}
        # Branch profit is the FX gain on rupiah sent to HQ; expenses are
        # paid back by Pusat and not taken off it.
        cur, prev = _profit(branches, per['start'], per['end']), _profit(branches, per['prev_start'], per['prev_end'])
        out['profit'] = {'cur': cur['fx'] if cur else None, 'prev': prev['fx'] if prev else None,
                         'expenses': cur['expenses'] if cur else 0}
    if rec is not None:
        out['receivable'] = {'total': rec['total'], 'past_due': rec['past_due'], 'past_clients': rec['past_clients'],
                             'count': rec['count']}
        out['chase'] = overdue_to_chase(rec, limit=5)
        out['collected'] = collected(scope(Invoice.objects.exclude(status=Invoice.STATUS_VOID), user, codes=codes), per, today)
    if can(user, 'remittance', 'view') and branches:
        out['owed'] = {'not_sent': cues['not_sent']['idr'], 'last_sent': cues['not_sent']['last_sent'],
                       'transit': cues['transit']}
    if 'to_pay' in cues:
        out['to_pay'] = cues['to_pay']
    out['todo'] = _finance_todo(user, codes, cues, today)
    return out


def _admin_todo(user, codes, today, system):
    """What only the administrator sees on top of the Manager's to do."""
    items = []
    if can(user, 'payments', 'approve'):
        p = _pending_agg(user, codes, today)
        if p['count']:
            items.append({'key': 'payments', 'count': p['count'], 'amount': p['sar'], 'ccy': 'SAR',
                          'oldest': p['oldest'], 'url': '/finance/payments/?status=pending'})
    if system['locked']:
        items.append({'key': 'locked', 'count': len(system['locked']), 'amount': None, 'ccy': None,
                      'first': system['locked'][0], 'url': '/users/'})
    if system['idle']:
        items.append({'key': 'idle', 'count': len(system['idle']), 'amount': None, 'ccy': None, 'url': '/users/'})
    if can(user, 'periods', 'view'):
        p = previous_period(today)
        if p:
            items.append({'key': 'period', 'count': 1, 'amount': None, 'ccy': None, 'month': p['month'],
                          'days': p['days'], 'url': '/finance/periods/'})
    return items


def _my_payments(user, codes, limit=5):
    rows = (scope(PaymentRecord.objects.filter(created_by=user), user, codes=codes)
            .select_related('client', 'receiving_account').order_by('-created_at')[:limit])
    return [{'id': p.pk, 'number': p.payment_number, 'client': p.client.display_name if p.client_id else p.reference,
             'date': p.payment_date.isoformat(), 'uploaded': _local(p.created_at).isoformat(),
             'account': str(p.receiving_account) if p.receiving_account_id else '',
             'amount': p.amount, 'ccy': p.currency, 'status': p.status} for p in rows]


def _my_advance(user, today):
    """The staff member's own cash advance (uang muka), per currency."""
    from .finance.staff_advance import balances as advance_balances
    from .models.bank import StaffAccount
    accounts = list(StaffAccount.objects.filter(holder=user, is_active=True).select_related('branch'))
    if not accounts:
        return None
    held = advance_balances(accounts)
    rows = {r['id']: r for r in queries._staff_overview(branches=[a.branch_id for a in accounts])}
    return [{'id': a.pk, 'ccy': a.currency, 'branch': a.branch.name if a.branch_id else '', 'held': held[a.pk],
             'given_on': (rows.get(a.pk) or {}).get('given_on')} for a in accounts]


def _people(user, today):
    """Users and access for the administrator: locked sign-ins, idle accounts."""
    return system_items(today) if can(user, 'users', 'view') else None


VARIANTS = ('manager', 'finance', 'admin', 'staff', 'viewer')


def home_variant(user):
    """Which dashboard the user gets, by role. A custom role gets the Manager
    one, cut down to what it may view."""
    role = get_role(user)
    if role == ADMIN_SLUG:
        return 'admin'
    return role if role in VARIANTS else 'manager'


def home(user, today, month=None, season=False):
    """Everything the user's dashboard draws, for the modules the user may
    view. Blocks the user may not see are left out (the page drops them)."""
    codes = view_codes(user)
    branches = ops_branches(codes)
    cls = scope(ConfirmationLetter.objects.all(), user, codes=codes)
    clients = scope(Client.objects.all(), user, codes=codes)
    per = home_period(today, month, season)
    finance_view = can(user, 'statements', 'view')
    variant = home_variant(user)
    out = {
        'variant': variant,
        'period': {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in per.items()
                   if k not in ('season', 'prev_season')},
        'all_branches': codes is None,
        'seasons': [{'name': s.name, 'start': s.date_from.isoformat(), 'end': s.date_to.isoformat()}
                    for s in Season.objects.filter(date_from__lte=today).order_by('-date_from')[:2]],
    }
    if variant == 'finance':
        out.update(_finance(user, today, per, codes, branches, clients))
        return out
    if variant in ('staff', 'viewer'):
        # Staff see every CL of their branch, not only the ones they sold
        # (2026-10-21).
        mine = cls
        if can(user, 'cl', 'view'):
            out['sales'] = {'cur': _sales_side(mine, per['start'], per['end']),
                            'prev': _sales_side(mine, per['prev_start'], per['prev_end'])}
            out['sold_months'] = sold_per_month(mine, today, per)
            out['checkins'] = checkins_week(mine, today)
            for r in out['checkins']['rows']:
                r['state'] = _checkin_status(r)
            out['top'] = _top(mine, today, per)
            if can(user, 'invoice', 'view'):
                out['uninvoiced'] = uninvoiced(mine, today, limit=1)
        if variant == 'staff':
            # Viewer reads only: no to do. Staff's to do is about their own CLs.
            out['todo'] = _todo(user, codes, mine, clients, today, None, mine=True)
            if can(user, 'payments', 'view'):
                out['my_payments'] = _my_payments(user, codes)
            out['advance'] = _my_advance(user, today)
        return out
    rec = None
    if can(user, 'invoice', 'view'):
        rec = receivables(clients, today)
    if can(user, 'cl', 'view'):
        cur = _sales_side(cls, per['start'], per['end'])
        prev = _sales_side(cls, per['prev_start'], per['prev_end'])
        out['sales'] = {'cur': cur, 'prev': prev}
        out['sold_months'] = sold_per_month(cls, today, per)
        out['checkins'] = checkins_week(cls, today)
        for r in out['checkins']['rows']:
            r['state'] = _checkin_status(r)
        out['top'] = _top(cls, today, per)
    if finance_view and branches:
        out['profit'] = {'cur': _profit(branches, per['start'], per['end']),
                         'prev': _profit(branches, per['prev_start'], per['prev_end'])}
    if can(user, 'invoice', 'view'):
        out['collected'] = collected(scope(Invoice.objects.exclude(status=Invoice.STATUS_VOID), user, codes=codes), per, today)
    out['todo'] = _todo(user, codes, cls, clients, today, rec)
    if finance_view:
        out['money'] = _money_now(user, codes, branches, today)
    if codes is None and can(user, 'cl', 'view'):
        out['branches'] = _by_branch(user, cls, clients, rec, ops_branches(None), per)
    if variant == 'admin':
        out['receivable'] = {'past_due': rec['past_due'], 'past_clients': rec['past_clients'],
                             'oldest': rec['past'][0]['days_overdue'] if rec['past'] else 0} if rec else None
        people = _people(user, today)
        if people is not None:
            out['people'] = people
            out['todo'] += _admin_todo(user, codes, today, people)
    return out
