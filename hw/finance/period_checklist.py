"""Month-end close checklist for a FinancialPeriod.

Each item is ok / warn / fail. A failure blocks locking the period (lock is
irreversible, so it must never seal a known error); a warning is something a
person should look at and may knowingly accept. Read-only.
"""
from django.db.models import Sum

OK, WARN, FAIL = 'ok', 'warn', 'fail'


def _item(key, label, status, detail='', link=None, rows=(), n=None):
    """`detail` is an English UI string, translated in the page; {n} = `n`."""
    rows = list(rows)
    return {'key': key, 'label': label, 'status': status, 'detail': detail,
            'params': {'n': len(rows) if n is None else n}, 'link': link, 'rows': rows[:8]}


def _payments(period):
    from ..models.payment import PaymentRecord
    from . import queries
    in_period = PaymentRecord.objects.filter(payment_date__gte=period.date_from, payment_date__lte=period.date_to)
    pending = list(in_period.filter(status=PaymentRecord.STATUS_PENDING).values_list('payment_number', flat=True))
    items = [_item(
        'pending_payments', 'Payments awaiting review', FAIL if pending else OK,
        '{n} payment(s) still pending — confirm or reject them.' if pending else 'None pending.',
        '/finance/payments/?status=pending', pending,
    )]
    effective = list(in_period.filter(status__in=PaymentRecord.EFFECTIVE_STATUSES).values_list('pk', 'payment_number'))
    unalloc = queries.payment_unallocated_map([pk for pk, _n in effective])
    open_rows = [f'{num}: {unalloc[pk]:,} SAR' for pk, num in effective if unalloc.get(pk)]
    items.append(_item(
        'unallocated_payments', 'Payments applied to reservations', WARN if open_rows else OK,
        '{n} payment(s) not fully applied to a reservation.' if open_rows else 'All applied.',
        '/finance/payments/', open_rows,
    ))
    return items


def _remittances(period):
    from ..models.remittance import Remittance
    from ..models.settlement import RemittanceSettlement
    from .settlement_service import diff_is_closed
    open_rems = list(
        Remittance.objects.filter(date__lte=period.date_to, status=Remittance.STATUS_PENDING)
        .prefetch_related('settlements').order_by('date')
    )
    transit = [r for r in open_rems if not r.settlements.all()]
    unclosed = [r for r in open_rems if r.settlements.all() and not diff_is_closed(r)]
    items = [
        _item('in_transit', 'Transfers to HQ received', WARN if transit else OK,
              '{n} transfer(s) sent but not yet received by HQ.' if transit else 'Nothing in transit.',
              '/remittance/?tab=tracking', [f'{r.remittance_number} ({r.date:%d/%m})' for r in transit]),
        _item('diff_open', 'Transfer differences closed', WARN if unclosed else OK,
              '{n} transfer(s) received but the difference (fees/FX) is not closed.' if unclosed else 'All closed.',
              '/remittance/?tab=tracking', [r.remittance_number for r in unclosed]),
    ]
    receipts = (
        RemittanceSettlement.objects.filter(received_date__lte=period.date_to)
        .annotate(allocated=Sum('allocations__amount_sar')).select_related('remittance')
    )
    unalloc = [s for s in receipts if (s.allocated or 0) < s.received_amount_sar
               and s.remittance.status == Remittance.STATUS_PENDING]
    items.append(_item(
        'receipts_unallocated', 'HQ receipts allocated to reservations', WARN if unalloc else OK,
        '{n} receipt(s) at HQ not fully allocated.' if unalloc else 'All allocated.',
        '/remittance/?tab=tracking',
        [f'{s.remittance.remittance_number}: {s.received_amount_sar - (s.allocated or 0):,} SAR' for s in unalloc],
    ))
    return items


def _bank_statements(period):
    from ..models.bank import BankAccount
    from ..models.bank_transaction import BankTransaction
    from ..models.reconciliation import BankStatement
    from .reconciliation_service import statement_summary
    active_ids = set(
        BankTransaction.objects.filter(
            transaction_date__gte=period.date_from, transaction_date__lte=period.date_to, account__kind='bank',
        ).exclude(status=BankTransaction.STATUS_VOIDED).values_list('account_id', flat=True)
    )
    problems = []
    for acc in BankAccount.objects.filter(pk__in=active_ids).order_by('branch_id', 'bank_name'):
        st = BankStatement.objects.filter(
            account=acc, period_start__lte=period.date_to, period_end__gte=period.date_to,
        ).order_by('-period_end').first()
        if st is None:
            problems.append(f'{acc}: no statement up to {period.date_to:%d/%m/%Y}')
            continue
        s = statement_summary(st)
        if not s['is_fully_matched']:
            problems.append(f'{acc}: {s["lines_total"] - s["lines_matched"]} statement line(s) unmatched')
        if s['difference']:
            problems.append(f'{acc}: bank vs books differ by {s["difference"]:,} {s["currency"]}')
    return [_item(
        'bank_statements', 'Bank accounts reconciled', WARN if problems else OK,
        'Reconcile each account that moved money this period.' if problems
        else ('All accounts reconciled.' if active_ids else 'No bank movement this period.'),
        '/finance/reconciliation/', problems,
    )]


def _integrity():
    from ..management.commands.check_finance import Command
    found = [(label, rows) for label, rows in Command().run_checks() if rows]
    rows = [f'{label}: {r}' for label, items in found for r in items]
    return [_item(
        'integrity', 'Journal integrity', FAIL if found else OK,
        '{n} finding(s) — the journal must be consistent before locking.' if found
        else 'Hash chain, balances and source documents agree.',
        None, rows,
    )]


def checklist(period):
    items = [*_payments(period), *_remittances(period), *_bank_statements(period), *_integrity()]
    return {
        'items': items,
        'fails': sum(1 for i in items if i['status'] == FAIL),
        'warns': sum(1 for i in items if i['status'] == WARN),
        'can_lock': not any(i['status'] == FAIL for i in items),
    }
