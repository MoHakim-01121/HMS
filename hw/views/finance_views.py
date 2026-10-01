from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404

from inertia import render as inertia_render

from ..finance import queries as finance_queries
from ..models import Client
from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..permissions import can, require_perm, _deny
from .helpers import _parse_date, serialize_journal_entry, journal_line_dimension


_FINANCE_MODULES = ('payments', 'statements', 'remittance', 'expenses', 'journal', 'periods', 'penalty')


@login_required
def finance_hub(request):
    """Finance Hub — satu layar kontrol keuangan (Control Room).

    Setiap blok data dihitung hanya jika user punya izin view modul terkait,
    jadi dashboard tidak pernah membocorkan angka dari modul yang tak boleh
    dilihat user (payments/statements/remittance/expenses/journal terpisah).
    """
    from ..models import PaymentRecord, Remittance
    from ..models.expense import Expense, ExpenseLine, ExpensePayment

    today = date.today()

    def has(module):
        return can(request.user, module, 'view')

    if not any(has(m) for m in _FINANCE_MODULES):
        return _deny(request)

    data = {'can': {m: has(m) for m in _FINANCE_MODULES}}

    # ── Kas & Payment ─────────────────────────────────────────────
    if has('payments'):
        # The KPI counts every pending payment; pending_prs is only the
        # preview list. Deriving the count from the sliced list capped
        # "menunggu review" at 6 and summed only those 6 amounts.
        pending_qs = PaymentRecord.objects.filter(status=PaymentRecord.STATUS_PENDING)
        pending_prs = list(
            pending_qs.select_related('client').order_by('-created_at')[:6]
        )
        this_month = PaymentRecord.objects.filter(
            payment_date__year=today.year, payment_date__month=today.month,
            status__in=PaymentRecord.EFFECTIVE_STATUSES,
        )
        data['cash'] = {
            'sby': finance_queries.kas_surabaya(),
            'jkt': finance_queries.kas_jakarta(),
            'pusat': finance_queries.kas_pusat(),
            'transit': finance_queries.transit(),
        }
        data['payments'] = {
            'pending_review': pending_qs.count(),
            'pending_review_total': pending_qs.aggregate(t=Sum('amount_sar'))['t'] or 0,
            'this_month_count': this_month.count(),
            'this_month_sar': this_month.aggregate(t=Sum('amount_sar'))['t'] or 0,
            'recent': [{
                'id': p.pk,
                'number': p.payment_number,
                'client': p.client.name if p.client_id else p.reference or p.payment_number,
                'date': p.payment_date.isoformat(),
                'amount_sar': p.amount_sar,
                'status': p.status,
                'unallocated': finance_queries.payment_unallocated_sar(p.pk),
            } for p in pending_prs],
        }
    else:
        data['cash'], data['payments'] = None, None

    # ── Piutang & Statement ───────────────────────────────────────
    if has('statements'):
        overview = finance_queries.clients_overview()
        debtors = [r for r in overview if r['piutang'] > 0]
        data['receivables'] = {
            'total': sum(r['piutang'] for r in overview),
            'count': len(debtors),
            'top': debtors[:6],
        }
    else:
        data['receivables'] = None

    # ── Remittance ────────────────────────────────────────────────
    if has('remittance'):
        pending_remits = Remittance.objects.order_by('-date', '-created_at').pending()
        sent_map = finance_queries.remittance_sent_map([r.id for r in pending_remits])
        recent = list(Remittance.objects.order_by('-date', '-created_at')[:6])
        recent_map = finance_queries.remittance_sent_map([r.id for r in recent])
        data['remittance'] = {
            'pending_count': len(pending_remits),
            'pending_sar': sum(sent_map.get(r.id, 0) for r in pending_remits),
            'kewajiban_kirim': finance_queries.kewajiban_kirim_sby(),
            'recent': [{
                'id': r.id,
                'number': r.remittance_number,
                'date': r.date.isoformat(),
                'status': r.status,
                'settled_sar': r.settled_sar,
                'amount_sar': recent_map.get(r.id, 0),
            } for r in recent],
        }
    else:
        data['remittance'] = None

    # ── Expenses ──────────────────────────────────────────────────
    if has('expenses'):
        month_exp = Expense.objects.filter(
            expense_date__year=today.year, expense_date__month=today.month,
            status=Expense.STATUS_POSTED,
        )
        month_total = ExpenseLine.objects.filter(expense__in=month_exp).aggregate(t=Sum('amount_sar'))['t'] or 0
        month_paid = ExpensePayment.objects.filter(
            expense__in=month_exp, status=ExpensePayment.STATUS_PAID,
        ).aggregate(t=Sum('amount_sar'))['t'] or 0
        data['expenses'] = {
            'month_total': month_total,
            'month_outstanding': max(0, month_total - month_paid),
            'recent': [{
                'id': e.id,
                'number': e.expense_number,
                'vendor': (e.vendor.name if e.vendor_id else '') or e.description or f"EXP #{e.pk}",
                'date': e.expense_date.isoformat(),
                'amount_sar': e.total_amount_sar,
                'status': e.display_status,
            } for e in Expense.objects.select_related('branch', 'vendor').prefetch_related('lines')
                .order_by('-expense_date')[:6]],
        }
    else:
        data['expenses'] = None

    # ── Journal (ledger review) ───────────────────────────────────
    if has('journal'):
        data['journal'] = {
            'recent': [{
                'id': e.id,
                'number': e.entry_number,
                'date': e.entry_date.isoformat(),
                'entry_type': e.entry_type,
                'entry_type_display': dict(JournalEntry.TYPE_CHOICES).get(e.entry_type, e.entry_type),
                'description': e.description,
            } for e in JournalEntry.objects.order_by('-entry_date', '-id')[:6]],
        }
    else:
        data['journal'] = None

    return inertia_render(request, 'Finance/Dashboard', props=data)


@require_perm('journal', 'view')
def journal_list(request):
    # Subquery totals instead of a JOIN annotate: Sum over `lines` on the
    # parent queryset duplicates the entry once per line row, breaking both
    # the per-entry totals and Paginator.count (which counted line rows).
    from django.db.models import OuterRef, Subquery
    lines_d = JournalLine.objects.filter(journal_entry_id=OuterRef('pk'))
    debit_sub = lines_d.annotate(total=Sum('debit')).values('total')[:1]
    credit_sub = lines_d.annotate(total=Sum('credit')).values('total')[:1]
    qs = JournalEntry.objects.annotate(
        debit=Subquery(debit_sub),
        credit=Subquery(credit_sub),
    )

    entry_type = request.GET.get('type', '')
    if entry_type:
        qs = qs.filter(entry_type=entry_type)
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    if date_from:
        qs = qs.filter(entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry_date__lte=date_to)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(entry_number__icontains=q) | Q(description__icontains=q))

    paginator = Paginator(qs.order_by('-entry_date', '-id'), 50)
    page = paginator.get_page(request.GET.get('page'))

    return inertia_render(request, 'Finance/Journal', props={
        'entries': [
            serialize_journal_entry(
                e, debit=e.debit or 0, credit=e.credit or 0, is_reversal=e.is_reversal,
            )
            for e in page.object_list
        ],
        'type_choices': JournalEntry.TYPE_CHOICES,
        'page_num': page.number,
        'num_pages': paginator.num_pages,
        'total': paginator.count,
        'filters': {'type': entry_type, 'date_from': date_from.isoformat() if date_from else '', 'date_to': date_to.isoformat() if date_to else '', 'q': q},
    })


@require_perm('journal', 'view')
def journal_detail(request, pk):
    entry = get_object_or_404(
        JournalEntry.objects.select_related('period', 'created_by'), pk=pk,
    )
    lines = entry.lines.select_related(
        'account', 'client', 'invoice', 'invoice_line__confirmation_letter', 'penalty',
    )
    totals = entry.lines.aggregate(debit=Sum('debit'), credit=Sum('credit'))
    return inertia_render(request, 'Finance/JournalDetail', props={
        'entry': serialize_journal_entry(
            entry,
            is_reversal=entry.is_reversal,
            reverses_id=entry.reverses_id,
            debit=totals['debit'] or 0,
            credit=totals['credit'] or 0,
        ),
        'created_by': entry.created_by.get_username() if entry.created_by else '',
        'reverses_number': entry.reverses.entry_number if entry.reverses else None,
        'lines': [{
            'id': ln.id,
            'account': ln.account_id,
            'account_display': ln.account.name,
            'amount_sar': ln.amount_sar,
            'note': ln.note,
            # Nominal asli baris kas/bank non-SAR.
            'native': f"{ln.amount_txn:,} {ln.currency}" if ln.amount_txn else None,
            'dim': journal_line_dimension(ln),
        } for ln in lines],
    })


@require_perm('journal', 'view')
def trial_balance(request):
    qs = JournalLine.objects.all()

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    if date_from:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)

    raw = qs.values('account').annotate(debit=Sum('debit'), credit=Sum('credit'))
    by_account = {r['account']: r for r in raw}

    groups = []
    total_debit = total_credit = 0
    for acc in LedgerAccount.objects.all():
        row = by_account.get(acc.code)
        if not row:
            continue
        debit = row['debit'] or 0
        credit = row['credit'] or 0
        net = debit - credit
        total_debit += debit
        total_credit += credit
        groups.append({
            'account': acc.code,
            'account_display': acc.name,
            'type': acc.type,
            'type_display': acc.get_type_display(),
            'debit': debit,
            'credit': credit,
            'net': net,
        })
    groups.sort(key=lambda g: (g['type'], -abs(g['net'])))

    return inertia_render(request, 'Finance/TrialBalance', props={
        'groups': groups,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balanced': total_debit == total_credit,
        'filters': {
            'date_from': date_from.isoformat() if date_from else '',
            'date_to': date_to.isoformat() if date_to else '',
        },
    })


@require_perm('statements', 'view')
def statements_list(request):
    return inertia_render(request, 'Finance/Statements', props={'clients': finance_queries.clients_overview()})


@require_perm('statements', 'view')
def bank_account_list(request):
    """Bank/cash balance overview (v2.0 §78). Read-only: accounts themselves
    are business-managed data (Django admin), balance is a pure projection
    from the journal (finance.queries.money_accounts_overview)."""
    from ..models.branch import Branch

    branch = request.GET.get('branch')
    rows = finance_queries.money_accounts_overview(branch=branch or None, include_inactive=True)
    return inertia_render(request, 'Finance/BankAccounts', props={
        'accounts': rows,
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True)],
        # Every branch, inactive included: an account can still belong to one.
        'branch_names': dict(Branch.objects.values_list('code', 'name')),
        'branch_filter': branch or '',
    })


BANK_CURRENCIES = ('IDR', 'SAR', 'USD')


# Ledger accounts a bank account may post to: the cash/bank class (1000-*),
# the same set the form's dropdown offers. Anything else (1100-AR, …) would
# book received money onto a non-cash account.
BANK_LEDGER_PREFIX = '1000-'


def _bank_account_in_use(acc):
    """A bank account that money or a reconciliation has touched keeps its
    branch, currency and ledger mapping — changing any of them would re-home
    or re-denominate what was already recorded against it."""
    from ..models import PaymentRecord
    return (
        acc.transactions.exclude(status='voided').exclude(source_type__startswith='OpeningBalance').exists()
        or acc.statements.exists()
        or PaymentRecord.objects.filter(receiving_account=acc).exists()
    )


def _bank_form_props(acc=None, data=None, errors=None):
    from ..models.branch import Branch
    ledger_choices = [
        {'value': a.code, 'label': f'{a.code} · {a.name}'}
        for a in LedgerAccount.objects.filter(type='asset', is_postable=True, is_active=True, code__startswith=BANK_LEDGER_PREFIX)
    ]
    if acc is not None and data is None:
        data = {
            'branch': acc.branch_id, 'bank_name': acc.bank_name,
            'account_identifier': acc.account_identifier, 'account_name': acc.account_name,
            'currency': acc.currency, 'ledger_account': acc.ledger_account_id,
            'show_on_invoice': acc.show_on_invoice, 'is_active': acc.is_active, 'note': acc.note,
            'opening_balance': acc.opening_balance or '',
            'opening_date': acc.opening_date.isoformat() if acc.opening_date else '',
        }
    return {
        'account': {**(data or {}), 'id': acc.pk if acc else None},
        'edit': acc is not None,
        'locked': bool(acc and _bank_account_in_use(acc)),
        'errors': errors or {},
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True)],
        'currency_choices': list(BANK_CURRENCIES),
        'ledger_choices': ledger_choices,
    }


def _default_ledger_for_branch(branch_code, currency):
    """The branch's cash ledger in this currency (1000-KAS-<BRANCH> for SAR,
    1000-KAS-<BRANCH>-<CUR> otherwise) when the form leaves the mapping blank."""
    from ..finance.accounts import cash_ledger_for
    if not LedgerAccount.objects.filter(code=f'1000-KAS-{branch_code.upper()}').exists():
        return None
    return cash_ledger_for(branch_code, currency)


def _save_bank_account(request, acc):
    """Validate the POST and write it onto `acc` (new or existing). Returns an
    errors dict; empty means saved."""
    from ..models.bank import BankAccount
    from ..models.branch import Branch
    P = request.POST
    data = {
        'branch': (P.get('branch') or '').strip(),
        'bank_name': (P.get('bank_name') or '').strip(),
        'account_identifier': (P.get('account_identifier') or '').strip(),
        'account_name': (P.get('account_name') or '').strip(),
        'currency': (P.get('currency') or '').strip().upper(),
        'ledger_account': (P.get('ledger_account') or '').strip(),
        'show_on_invoice': P.get('show_on_invoice') == 'on',
        'is_active': P.get('is_active') == 'on',
        'note': (P.get('note') or '').strip(),
        'opening_balance': (P.get('opening_balance') or '').strip().replace(',', ''),
        'opening_date': (P.get('opening_date') or '').strip(),
    }
    locked = acc.pk is not None and _bank_account_in_use(acc)
    if locked:
        data['branch'] = acc.branch_id
        data['currency'] = acc.currency
        data['ledger_account'] = acc.ledger_account_id

    errors = {}
    if not Branch.objects.filter(code=data['branch'], is_active=True).exists():
        errors['branch'] = 'Pick a branch.'
    if not data['bank_name']:
        errors['bank_name'] = 'Bank name is required.'
    if not data['account_identifier']:
        errors['account_identifier'] = 'Account number is required.'
    if data['currency'] not in BANK_CURRENCIES:
        errors['currency'] = 'Pick a currency.'
    elif data['branch'] == 'pusat' and data['currency'] != 'SAR':
        errors['currency'] = 'HQ only receives SAR — rupiah and dollar accounts belong to a branch.'
    if not data['ledger_account'] and not errors.get('branch') and not errors.get('currency'):
        data['ledger_account'] = _default_ledger_for_branch(data['branch'], data['currency']) or ''
    # Without a valid branch the automatic ledger can't be resolved — the
    # branch error already says what to fix, so don't pile a second one on.
    if not errors.get('branch') and not LedgerAccount.objects.filter(
        code=data['ledger_account'], code__startswith=BANK_LEDGER_PREFIX,
        type='asset', is_postable=True, is_active=True,
    ).exists():
        errors['ledger_account'] = 'Pick a ledger account.'
    elif not errors.get('currency'):
        from ..finance.bank_ledger import ledger_currency_conflict
        other = ledger_currency_conflict(data['ledger_account'], data['currency'], exclude_pk=acc.pk)
        if other:
            errors['ledger_account'] = (
                f'{data["ledger_account"]} already holds {other} accounts — one ledger account, one currency.'
            )
    dup = BankAccount.objects.filter(
        bank_name__iexact=data['bank_name'], account_identifier=data['account_identifier'], currency=data['currency'],
    ).exclude(pk=acc.pk)
    if data['bank_name'] and data['account_identifier'] and dup.exists():
        errors['account_identifier'] = 'This account is already registered.'
    try:
        opening_balance = int(data['opening_balance'] or 0)
    except ValueError:
        opening_balance = None
        errors['opening_balance'] = 'Enter a whole number.'
    opening_date = _parse_date(data['opening_date']) if data['opening_date'] else None
    if opening_balance and opening_date is None:
        errors['opening_date'] = 'Pick the date of this balance.'
    if errors:
        return errors, data

    acc.branch_id = data['branch']
    acc.bank_name = data['bank_name']
    acc.account_identifier = data['account_identifier']
    acc.account_name = data['account_name']
    acc.currency = data['currency']
    acc.ledger_account_id = data['ledger_account']
    acc.show_on_invoice = data['show_on_invoice'] and data['is_active']
    acc.is_active = data['is_active']
    acc.note = data['note']
    # name is the account's own label; str(acc) prefixes the bank and
    # suffixes the currency, so storing those here doubled them everywhere.
    acc.name = data['account_identifier']
    acc.opening_balance = opening_balance
    acc.opening_date = opening_date
    from ..finance.bank_ledger import sync_opening_balance
    from ..finance.errors import FinanceError
    try:
        with transaction.atomic():
            acc.save()
            sync_opening_balance(acc)
    except FinanceError as e:
        return {'opening_balance': str(e)}, data
    return {}, data


@require_perm('statements', 'edit')
def bank_account_new(request):
    from django.contrib import messages
    from django.shortcuts import redirect
    from ..models.bank import BankAccount
    if request.method == 'POST':
        acc = BankAccount()
        errors, data = _save_bank_account(request, acc)
        if errors:
            return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(None, data, errors))
        messages.success(request, f'Bank account {acc} added.')
        return redirect('bank_account_list')
    return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(
        None, {'branch': request.GET.get('branch', ''), 'currency': 'IDR', 'is_active': True},
    ))


@require_perm('statements', 'edit')
def bank_account_edit(request, pk):
    from django.contrib import messages
    from django.shortcuts import redirect
    from ..models.bank import BankAccount
    acc = get_object_or_404(BankAccount, pk=pk)
    if request.method == 'POST':
        errors, data = _save_bank_account(request, acc)
        if errors:
            return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(acc, data, errors))
        messages.success(request, f'Bank account {acc} updated.')
        return redirect('bank_account_list')
    return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(acc))


@require_perm('statements', 'view')
def bank_account_transactions(request, kind, pk):
    """Drill-down riwayat BankTransaction satu rekening (v2.0 §64 follow-up).
    Saldo berjalan di sini murni kumulatif BankTransaction — beda dari
    book_balance (proyeksi JournalLine) yang dipakai di bank_account_list."""
    if kind not in ('bank', 'cash'):
        raise Http404

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    data = finance_queries.account_transactions(kind, pk, date_from=date_from, date_to=date_to)
    if data is None:
        raise Http404

    return inertia_render(request, 'Finance/BankAccountTransactions', props={
        'account': data['account'],
        'rows': data['rows'],
        'filters': {
            'date_from': date_from.isoformat() if date_from else '',
            'date_to': date_to.isoformat() if date_to else '',
        },
    })


@require_perm('statements', 'view')
def client_finance_statement(request, pk):
    """Client finance statement from JournalEntries (unified query path).

    Supports two modes, mirroring QuickBooks/Xero/Zoho:
      - `balance` (default): Balance Forward — opening + running balance rows.
      - `open`: Open Item — daftar invoice yang belum lunas per client.
    """
    client = get_object_or_404(Client, pk=pk)

    mode = request.GET.get('mode', 'balance')
    if mode not in ('balance', 'open'):
        mode = 'balance'

    date_from = request.GET.get('from')
    date_to = request.GET.get('to')

    if date_from:
        date_from = _parse_date(date_from)
    if date_to:
        date_to = _parse_date(date_to)

    aging = finance_queries.client_aging(client.pk)

    if mode == 'open':
        open_items = finance_queries.open_items(
            client.pk, date_to=date_to,
        )
        statement_payload = {
            "mode": "open",
            "transactions": [],
            "open_items": open_items["rows"],
            "total_open": open_items["total_remaining"],
            "opening_balance": 0,
            "closing_balance": open_items["total_remaining"],
            "total_debit": 0,
            "total_credit": 0,
        }
    else:
        statement = finance_queries.client_statement_with_opening(
            client.pk, date_from=date_from, date_to=date_to,
        )
        transactions = [{
            "date": r["date"].isoformat() if r["date"] else None,
            "entry_number": r["entry_number"],
            "entry_type": r["entry_type"],
            "entry_type_display": dict(JournalEntry.TYPE_CHOICES).get(r["entry_type"], r["entry_type"]),
            "description": r["description"],
            "account": r["account"],
            "account_display": r["account_name"],
            "invoice_number": r["invoice_number"],
            "amount_sar": r["debit"] - r["credit"],
            "balance": r["balance"],
        } for r in statement["rows"]]
        statement_payload = {
            "mode": "balance",
            "transactions": transactions,
            "open_items": [],
            "total_open": 0,
            "opening_balance": statement["opening_balance"],
            "closing_balance": statement["closing_balance"],
            "total_debit": statement["total_debit"],
            "total_credit": statement["total_credit"],
        }

    return inertia_render(request, 'Finance/ClientStatement', props={
        'client': {
            'id': client.pk,
            'name': client.name,
            # Moved here from Client detail: Client is information only.
            'total_billed': client.total_billed,
            'saldo_dana': finance_queries.client_credit_balance(client.pk),
            'avg_days_to_pay': client.avg_days_to_pay,
        },
        'statement': statement_payload,
        'aging': aging,
        'mode': mode,
        'date_from': date_from.isoformat() if date_from else None,
        'date_to': date_to.isoformat() if date_to else None,
    })



def _fund_flow_params(request):
    from ..models.branch import Branch
    today = date.today()
    date_from = _parse_date(request.GET.get('from')) or today.replace(day=1)
    date_to = _parse_date(request.GET.get('to')) or today
    branch = request.GET.get('branch') or 'sby'
    if not Branch.objects.filter(code=branch).exists():
        branch = 'sby'
    return branch, date_from, date_to


@require_perm('statements', 'view')
def fund_flow_report(request):
    """Arus Dana: per-currency money in/out of a branch + realized FX profit."""
    from ..finance import fund_flow
    from ..models.branch import Branch
    branch, date_from, date_to = _fund_flow_params(request)
    flow = fund_flow.fund_flow(branch=branch, date_from=date_from, date_to=date_to)
    fx = fund_flow.fx_profit(branch=branch, date_from=date_from, date_to=date_to)
    return inertia_render(request, 'Finance/FundFlow', props={
        'branch': branch,
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.order_by('code')],
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'flow': flow,
        'fx': fx,
    })


@require_perm('statements', 'export')
def fund_flow_csv(request):
    from ..finance import fund_flow
    from .helpers import csv_export_response
    branch, date_from, date_to = _fund_flow_params(request)
    flow = fund_flow.fund_flow(branch=branch, date_from=date_from, date_to=date_to)
    fx = fund_flow.fx_profit(branch=branch, date_from=date_from, date_to=date_to)
    rows = [['Fund flow', branch, date_from.isoformat(), date_to.isoformat()], ['Line', *flow['currencies']]]
    rows += [[l['label'], *[l['values'][c] for c in flow['currencies']]] for l in flow['lines']]
    rows += [[], ['Transfer', 'Date', 'SAR', 'IDR sent', 'Average rate', 'Send rate', 'FX profit (IDR)']]
    rows += [[t['remittance_number'], t['date'], t['sar'], t['idr_sent'], t['avg_rate'], t['send_rate'], t['profit_idr']]
             for t in fx['transfers']]
    rows += [['Total FX profit', '', '', '', '', '', fx['total_profit_idr']]]
    rows += [[], ['Date', 'Line', 'Account', 'Currency', 'Amount', 'Reference']]
    rows += [[t['date'], t['line'], t['account'], t['currency'], t['amount'], t['reference']] for t in flow['transactions']]
    return csv_export_response(f'fund-flow-{branch}-{date_from}-{date_to}.csv', rows[0], rows[1:])


def _aging_as_of(request):
    return _parse_date(request.GET.get('as_of')) or date.today()


@require_perm('statements', 'view')
def ar_aging_report(request):
    """Aging piutang semua client, per tanggal."""
    return inertia_render(request, 'Finance/ArAging', props={
        'aging': finance_queries.ar_aging(as_of=_aging_as_of(request)),
    })


@require_perm('statements', 'view')
def service_margin_report(request):
    """Margin baris Services terhadap biaya vendornya, dan utang per vendor."""
    from ..models.branch import Branch
    branch = request.GET.get('branch') or ''
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    return inertia_render(request, 'Finance/ServiceMargin', props={
        'margins': finance_queries.service_margins(branch=branch or None, date_from=date_from, date_to=date_to),
        'payables': finance_queries.vendor_payables(),
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True).order_by('name')],
        'filters': {
            'branch': branch,
            'date_from': date_from.isoformat() if date_from else '',
            'date_to': date_to.isoformat() if date_to else '',
        },
    })


@require_perm('statements', 'export')
def ar_aging_csv(request):
    from .helpers import csv_export_response
    aging = finance_queries.ar_aging(as_of=_aging_as_of(request))
    buckets = finance_queries.AGING_BUCKETS
    header = ['Client', 'Invoice', 'Due date', 'Days overdue', 'Not yet due', '1-30', '31-60', '61-90', '>90', 'Total (SAR)']
    rows = []
    for c in aging['clients']:
        rows.append([c['name'], '', '', '', *[c['buckets'][b] for b in buckets], c['total']])
        for i in c['invoices']:
            rows.append(['', i['invoice_number'], i['due_date'] or '', i['days_overdue'],
                         *[i['amount'] if i['bucket'] == b else '' for b in buckets], i['amount']])
    rows.append(['Total', '', '', '', *[aging['buckets'][b] for b in buckets], aging['total']])
    return csv_export_response(f'ar-aging-{aging["as_of"]}.csv', header, rows)
