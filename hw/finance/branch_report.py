"""Laporan cabang per periode, dalam rupiah (keputusan user 2026-10-19).

Laba cabang = laba kurs dari setoran ke Pusat saja (fund_flow.fx_profit).
Biaya operasional ditalangi cabang lalu diganti Pusat lewat klaim, jadi
ditampilkan sendiri beserta status penggantiannya, tidak mengurangi laba.
Posisi dibaca per tanggal akhir periode.

Periode: bulan, kuartal (kalender), tahun, musim umrah, atau rentang bebas;
pembandingnya periode sebelumnya yang sepanjang itu.
"""
import calendar
from datetime import date, timedelta

from django.db.models import Case, F, IntegerField, Sum, When
from django.utils import timezone

from ..models.bank import MoneyAccount
from ..models.bank_transaction import BankTransaction
from ..models.branch import Branch
from ..models.expense import Expense, ExpenseLine, ExpensePayment
from ..models.journal import JournalLine
from ..models.period import Season
from . import accounts as coa
from . import fund_flow
from .claim_service import head_office_credit, reimbursement_summary

KINDS = ('month', 'quarter', 'year', 'season', 'range')


def report_branches(user):
    """Branches `user` may see a report for: active, not Pusat (head office
    does not run on HMS), within the user's coverage (not the sidebar's
    active branch, so looking at Pusat still lists them)."""
    from ..branch_scope import coverage
    codes = coverage(user)
    branches = Branch.objects.filter(is_hq=False, is_active=True).order_by('code')
    return branches if codes is None else branches.filter(code__in=codes)


def _month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def _parse_date(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _year_ok(y):
    # The previous period of year y starts in y - 1, which date() must hold.
    return 1901 <= y <= 9999


def _span(date_from, date_to, label):
    return {'date_from': date_from, 'date_to': date_to, 'label': label}


def period_bounds(kind, value, *, today=None):
    """{'kind', 'value', 'date_from', 'date_to', 'label', 'prev'}. Nilai yang
    kosong atau tidak terbaca jatuh ke bulan berjalan."""
    today = today or timezone.localdate()
    value = (value or '').strip()
    if kind == 'quarter':
        try:
            y, q = value.split('-Q')
            y, q = int(y), int(q)
            assert 1 <= q <= 4 and _year_ok(y)
        except (ValueError, AssertionError):
            y, q = today.year, (today.month - 1) // 3 + 1
        py, pq = (y - 1, 4) if q == 1 else (y, q - 1)
        cur = _span(date(y, 3 * q - 2, 1), _month_end(y, 3 * q), f'Q{q} {y}')
        prev = _span(date(py, 3 * pq - 2, 1), _month_end(py, 3 * pq), f'Q{pq} {py}')
        return {'kind': kind, 'value': f'{y}-Q{q}', **cur, 'prev': prev}
    if kind == 'year':
        y = int(value) if value.isdigit() and len(value) == 4 and _year_ok(int(value)) else today.year
        return {'kind': kind, 'value': str(y), **_span(date(y, 1, 1), date(y, 12, 31), str(y)),
                'prev': _span(date(y - 1, 1, 1), date(y - 1, 12, 31), str(y - 1))}
    if kind == 'season':
        season = Season.objects.filter(pk=value).first() if value.isdigit() else None
        season = season or Season.objects.filter(date_from__lte=today).order_by('-date_from').first()
        if season is not None:
            before = Season.objects.filter(date_from__lt=season.date_from).order_by('-date_from').first()
            return {'kind': kind, 'value': str(season.pk),
                    **_span(season.date_from, season.date_to, season.name),
                    'prev': _span(before.date_from, before.date_to, before.name) if before else None}
        # No season yet: stay on the Season kind (the page says so) over this month.
        first = today.replace(day=1)
        return {'kind': kind, 'value': '', **_span(first, _month_end(first.year, first.month), f'{first:%B %Y}'),
                'prev': None}
    if kind == 'range':
        a, _, b = value.partition('..')
        a, b = _parse_date(a), _parse_date(b)
        if not (a and b and a <= b and _year_ok(a.year) and _year_ok(b.year)):
            # Nothing picked yet: start the range on this month.
            a, b = today.replace(day=1), _month_end(today.year, today.month)
        days = (b - a).days + 1
        pa, pb = a - timedelta(days=days), a - timedelta(days=1)
        return {'kind': kind, 'value': f'{a}..{b}', **_span(a, b, f'{a:%d %b %Y} – {b:%d %b %Y}'),
                'prev': _span(pa, pb, f'{pa:%d %b %Y} – {pb:%d %b %Y}')}
    try:
        y, m = (int(x) for x in value.split('-'))
        first = date(y, m, 1)
        assert _year_ok(y)
    except (ValueError, TypeError, AssertionError):
        first = today.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    return {'kind': 'month', 'value': f'{first:%Y-%m}',
            **_span(first, _month_end(first.year, first.month), f'{first:%B %Y}'),
            'prev': _span(prev, _month_end(prev.year, prev.month), f'{prev:%B %Y}')}


def profit_delta(cur, prev):
    """'+12%' against the previous period's profit; None without a positive
    base (a loss or zero before would flip or blow up the percentage)."""
    if cur is None or prev is None or prev <= 0:
        return None
    d = round((cur - prev) * 100 / prev)
    return f"{'+' if d >= 0 else ''}{d}%"


def _fx_idr(fx):
    """Laba kurs periode: None hanya bila setiap setoran belum bisa dihitung
    (sama dengan fund_flow.net_profit); tanpa setoran = 0."""
    if fx['transfers'] and fx['unpriced'] == len(fx['transfers']):
        return None
    return fx['total_profit_idr']


def _profit(fx):
    """Laba kurs, diskon yang ditanggung cabang (nota kredit), laba bersih."""
    return {
        'fx_idr': _fx_idr(fx), 'transfers': fx['transfers'], 'unpriced': fx['unpriced'],
        'discounts': fx['discounts'], 'discount_idr': fx['discount_idr'],
        'discount_unpriced': sum(1 for d in fx['discounts'] if d['idr'] is None),
        'net_idr': fund_flow.net_profit(fx),
    }


def _expenses(branch_code, date_from, date_to):
    paid = ExpensePayment.objects.filter(
        status=ExpensePayment.STATUS_PAID, expense__status=Expense.STATUS_PAID, expense__branch_id=branch_code,
        payment_date__gte=date_from, payment_date__lte=date_to,
    )
    by_cat = (
        ExpenseLine.objects.filter(expense__in=paid.values('expense'))
        .values('category__name').annotate(amount=Sum('amount')).order_by('-amount')
    )
    # Status as it stood on the period's last day, like the position block.
    status = reimbursement_summary(Branch(pk=branch_code), as_of=date_to, date_from=date_from, date_to=date_to)
    return {
        'total': sum(r['amount'] for r in by_cat),
        'by_category': [{'name': r['category__name'], 'amount': r['amount']} for r in by_cat],
        'paid_back': status['paid'], 'claimed': status['claimed'], 'unclaimed': status['unclaimed'],
    }


def _net_lines(account, branch_code, as_of, sign):
    agg = JournalLine.objects.filter(
        account_id=account, client__owner_branch_id=branch_code, journal_entry__entry_date__lte=as_of,
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return sign * ((agg['d'] or 0) - (agg['c'] or 0))


def _position(branch_code, as_of):
    accounts = list(MoneyAccount.objects.filter(branch_id=branch_code).order_by('kind', 'currency', 'pk'))
    native = dict(
        BankTransaction.objects.filter(account__in=accounts, transaction_date__lte=as_of)
        .exclude(status=BankTransaction.STATUS_VOIDED).values('account_id')
        .annotate(n=Sum(Case(When(direction=BankTransaction.DIRECTION_IN, then=F('amount')),
                             default=-F('amount'), output_field=IntegerField())))
        .values_list('account_id', 'n')
    )
    rows = [{'name': str(a), 'kind': a.kind, 'currency': a.currency, 'native': native.get(a.pk, 0) or 0}
            for a in accounts if a.is_active or native.get(a.pk)]
    owed = reimbursement_summary(Branch(pk=branch_code), as_of=as_of)
    return {
        'as_of': as_of.isoformat(),
        'accounts': rows,
        'receivable_sar': _net_lines(coa.AR, branch_code, as_of, 1),
        'deposits_sar': _net_lines(coa.CUST_CREDIT, branch_code, as_of, -1),
        'owed_by_hq_idr': owed['claimed'] + owed['unclaimed'] - head_office_credit(branch_code, as_of=as_of),
        'cash_idr': sum(r['native'] for r in rows if r['currency'] == 'IDR' and r['kind'] != MoneyAccount.KIND_STAFF),
    }


def branch_report(branch_code, date_from, date_to):
    fx = fund_flow.fx_profit(branch=branch_code, date_from=date_from, date_to=date_to)
    return {
        'profit': _profit(fx),
        'expenses': _expenses(branch_code, date_from, date_to),
        'position': _position(branch_code, date_to),
    }


def headline(branch_code, date_from, date_to):
    """Angka pembanding periode sebelumnya: laba bersih dan biaya."""
    fx = fund_flow.fx_profit(branch=branch_code, date_from=date_from, date_to=date_to)
    return {'fx_idr': _fx_idr(fx), 'net_idr': fund_flow.net_profit(fx),
            'expenses': _expenses(branch_code, date_from, date_to)['total']}
