from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from inertia import render as inertia_render

from ..branch_scope import branch_codes, covers_all, get_in_scope_or_404, in_view, scope
from ..finance import queries as finance_queries
from ..finance.seasons import season_choices
from ..i18n import tr
from ..models import Client
from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..permissions import _deny, can, require_perm
from .helpers import _parse_date, journal_line_dimension, pagination_props, serialize_journal_entry


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
        'seasons': season_choices(),
        'filters': {
            'date_from': date_from.isoformat() if date_from else '',
            'date_to': date_to.isoformat() if date_to else '',
        },
    })


@require_perm('statements', 'view')
def statements_list(request):
    """Client Ledger list (Record View HMS canvas): receivables, what is
    overdue, customer deposits and what can be offset, then one row per client
    with its receivable debit, credit, balance and deposit."""
    from datetime import date as _date

    from .helpers import list_per_page
    q = request.GET.get('q', '').strip()
    show = request.GET.get('show', '')
    sort = request.GET.get('sort', 'receivable')
    clients = scope(Client.objects.all(), request.user)
    rows = finance_queries.clients_overview(q=q, sort='receivable', clients=clients)
    aging = {c['client_id']: c for c in finance_queries.ar_aging(clients=clients)['clients']}
    for r in rows:
        a = aging.get(r['client_id'])
        r['overdue'] = (a['total'] - a['buckets'].get('current', 0)) if a else 0
        r['oldest_days'] = a['oldest_days'] if a else 0
        r['offset'] = min(r['piutang'], r['saldo_dana']) if r['piutang'] > 0 and r['saldo_dana'] > 0 else 0
    pick = {
        'owe': lambda r: r['piutang'] > 0, 'due': lambda r: r['overdue'] > 0,
        'dep': lambda r: r['saldo_dana'] > 0, 'off': lambda r: r['offset'] > 0,
    }
    counts = {k: sum(1 for r in rows if f(r)) for k, f in pick.items()}
    counts['all'] = len(rows)
    owing = [r for r in rows if r['piutang'] > 0]
    due = [r for r in rows if r['overdue'] > 0]
    kpis = {
        'ar': sum(r['piutang'] for r in owing), 'ar_clients': len(owing),
        'overdue': sum(r['overdue'] for r in due), 'overdue_clients': len(due),
        'oldest_days': max((r['oldest_days'] for r in due), default=0),
        'deposits': sum(r['saldo_dana'] for r in rows if r['saldo_dana'] > 0), 'deposit_clients': counts['dep'],
        'offset': sum(r['offset'] for r in rows), 'offset_clients': counts['off'],
    }
    shown = [r for r in rows if show not in pick or pick[show](r)]
    shown.sort(key={'deposit': lambda r: (-r['saldo_dana'], r['name'].lower()),
                    'name': lambda r: r['name'].lower()}.get(sort, lambda r: (-r['piutang'], r['name'].lower())))
    totals = {k: sum(r[k] for r in shown) for k in ('ar_debit', 'ar_credit', 'piutang', 'saldo_dana')}
    page_obj = Paginator(shown, list_per_page(request)).get_page(request.GET.get('page'))
    return inertia_render(request, 'Finance/Statements', props={
        'clients': list(page_obj), 'totals': totals, 'kpis': kpis, 'counts': counts,
        'as_of': _date.today().isoformat(),
        'filters': {'q': q, 'show': show, 'sort': sort, 'per': list_per_page(request)},
        'pagination': pagination_props(page_obj),
    })


def _bank_rows(request):
    """Accounts of the branch looked at, with the balance in the account's own
    currency (its posted cash-book rows) next to the SAR value on the ledger."""
    from django.db.models import Case, F, IntegerField, Max, Sum, When

    from ..models.bank_transaction import BankTransaction
    from ..models.branch import Branch
    from ..models.reconciliation import BankStatement
    rows = finance_queries.money_accounts_overview(include_inactive=True, branches=branch_codes(request.user))
    ids = [r['id'] for r in rows]
    native = {
        x['account_id']: x['n'] or 0 for x in BankTransaction.objects.filter(account_id__in=ids)
        .exclude(status=BankTransaction.STATUS_VOIDED)
        .values('account_id').annotate(n=Sum(Case(
            When(direction=BankTransaction.DIRECTION_IN, then=F('amount')),
            default=-F('amount'), output_field=IntegerField())))
    }
    last = dict(BankStatement.objects.filter(account_id__in=ids).values('account_id').annotate(d=Max('period_end')).values_list('account_id', 'd'))
    names = dict(Branch.objects.values_list('code', 'name'))
    for r in rows:
        if r['kind'] == 'staff':  # already in the account's own currency
            r['branch_name'] = names.get(r['branch'], r['branch'])
            r['last_reconciled'] = None
            continue
        r['native_balance'] = native.get(r['id'], 0) if r['currency'] != 'SAR' else (native.get(r['id']) if r['id'] in native else r['book_balance'])
        r['branch_name'] = names.get(r['branch'], r['branch'])
        r['last_reconciled'] = last[r['id']].isoformat() if last.get(r['id']) else None
    return rows


def sets_up_accounts(user):
    """Adding or changing a bank or cash account: 'bank' edit, and head
    office's alone (confirmed 2026-10-09). A branch reads its own accounts and
    may transfer and reconcile on them."""
    return can(user, 'bank', 'edit') and covers_all(user)


@require_perm('bank', 'view')
def bank_account_list(request):
    """Bank and Cash (Record View HMS canvas): no KPIs; the accounts in bands
    per currency, the book balance in the account's currency and its SAR
    value, and the total."""
    from datetime import date as _date

    from .helpers import csv_list
    q = request.GET.get('q', '').strip().lower()
    kinds = csv_list(request, 'kind', ['bank', 'cash', 'staff'])
    currencies = csv_list(request, 'cur', ['IDR', 'USD', 'SAR'])
    branches = csv_list(request, 'branch')
    rows = _bank_rows(request)
    count = lambda key: {v: sum(1 for r in rows if r[key] == v) for v in {r[key] for r in rows}}
    counts = {'kind': count('kind'), 'cur': count('currency'), 'branch': count('branch_name')}
    shown = [r for r in rows if (not q or q in (r['name'] + ' ' + (r['account_identifier'] or '')).lower())
             and (not kinds or r['kind'] in kinds) and (not currencies or r['currency'] in currencies)
             and (not branches or r['branch_name'] in branches or r['branch'] in branches)]
    order = {'IDR': 0, 'USD': 1, 'SAR': 2}
    shown.sort(key=lambda r: (order.get(r['currency'], 9), not r['is_active'], r['kind'], r['name']))
    return inertia_render(request, 'Finance/BankAccounts', props={
        'accounts': shown,
        'filters': {'q': q, 'kind': kinds, 'cur': currencies, 'branch': branches},
        'counts': counts,
        'as_of': _date.today().isoformat(),
        'can_set_up': sets_up_accounts(request.user),
    })


@require_perm('bank', 'export')
def bank_account_export_csv(request):
    from .helpers import csv_export_response
    return csv_export_response('accounts.csv', ['Account', 'Number', 'Type', 'Branch', 'Currency', 'Book balance', 'SAR value', 'Active'], [
        [r['name'], r['account_identifier'], r['kind'], r['branch_name'], r['currency'], r['native_balance'],
         r['book_balance'], 'yes' if r['is_active'] else 'no'] for r in _bank_rows(request)
    ])


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
            'kind': acc.kind, 'name': acc.name if acc.name != acc.account_identifier else '',
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
    from ..models.bank import MoneyAccount
    from ..models.branch import Branch
    P = request.POST
    kind = acc.kind if acc.pk else (P.get('kind') if P.get('kind') in ('bank', 'cash') else 'bank')
    data = {
        'kind': kind,
        'name': (P.get('name') or '').strip(),
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
    if kind == 'bank':
        if not data['bank_name']:
            errors['bank_name'] = 'Bank name is required.'
        if not data['account_identifier']:
            errors['account_identifier'] = 'Account number is required.'
    else:
        data['bank_name'] = data['account_identifier'] = data['account_name'] = ''
        data['show_on_invoice'] = False
        if not data['name']:
            errors['name'] = 'Name the cash box, for example Kas Surabaya.'
        elif MoneyAccount.objects.filter(kind='cash', branch_id=data['branch'], name__iexact=data['name'],
                                         currency=data['currency']).exclude(pk=acc.pk).exists():
            errors['name'] = 'This branch already has a cash box with this name.'
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
    dup = MoneyAccount.objects.filter(
        kind='bank', bank_name__iexact=data['bank_name'], account_identifier=data['account_identifier'], currency=data['currency'],
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

    acc.kind = kind
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
    # A bank account without a label of its own goes by its number.
    acc.name = data['name'] or data['account_identifier']
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


@require_perm('bank', 'edit')
def bank_account_new(request):
    if not sets_up_accounts(request.user):
        return _deny(request)
    from django.contrib import messages
    from django.shortcuts import redirect

    from ..models.bank import MoneyAccount
    if request.method == 'POST':
        acc = MoneyAccount()
        errors, data = _save_bank_account(request, acc)
        if errors:
            return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(None, data, errors))
        messages.success(request, tr(request, f'Account {acc} added.', f'Rekening {acc} ditambahkan.'))
        return redirect('bank_account_list')
    return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(
        None, {'kind': 'bank', 'branch': request.GET.get('branch', ''), 'currency': 'IDR', 'is_active': True},
    ))


@require_perm('bank', 'edit')
def bank_account_edit(request, pk):
    if not sets_up_accounts(request.user):
        return _deny(request)
    from django.contrib import messages
    from django.shortcuts import redirect

    from ..models.bank import MoneyAccount
    acc = get_object_or_404(MoneyAccount.objects.exclude(kind=MoneyAccount.KIND_STAFF), pk=pk)
    if request.method == 'POST':
        errors, data = _save_bank_account(request, acc)
        if errors:
            return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(acc, data, errors))
        messages.success(request, tr(request, f'Account {acc} updated.', f'Rekening {acc} diperbarui.'))
        return redirect('bank_account_list')
    return inertia_render(request, 'Finance/BankAccountForm', props=_bank_form_props(acc))


@require_perm('bank', 'view')
def bank_account_transactions(request, kind, pk):
    """Drill-down riwayat BankTransaction satu rekening (v2.0 §64 follow-up).
    Saldo berjalan di sini murni kumulatif BankTransaction — beda dari
    book_balance (proyeksi JournalLine) yang dipakai di bank_account_list."""
    if kind not in ('bank', 'cash', 'staff'):
        raise Http404

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    from ..models.bank import MoneyAccount
    # Any branch the user covers, not only the one picked: a link still opens.
    get_in_scope_or_404(MoneyAccount.objects.filter(kind=kind), request.user, pk=pk)
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


def _pending_out_rows(user, client=None):
    """Refund / transfer deposit yang menunggu persetujuan, untuk layar.
    `can_decide`: user ini boleh menyetujui/menolaknya (bukan pencatatnya,
    kecuali admin, dan punya hak payments.approve: keputusan uang keluar)."""
    from ..finance.deposit import can_approve, pending_out
    may_decide = can(user, 'payments', 'approve')
    refunds, transfers = pending_out(client)
    # Only the user's branches' clients.
    refunds = [r for r in refunds if in_view(user, r.client.owner_branch_id)]
    transfers = [t for t in transfers if in_view(user, t.from_client.owner_branch_id)
                 or in_view(user, t.to_client.owner_branch_id)]
    rows = [{
        'kind': 'refund', 'id': r.pk, 'number': r.refund_number, 'date': r.refund_date.isoformat(),
        'client': r.client.name, 'client_id': r.client_id,
        'detail': f'{r.money_account}' + (f' · {r.amount_paid:,} {r.money_account.currency}' if r.money_account.currency != 'SAR' else ''),
        'amount_sar': r.amount_sar, 'note': r.note, 'created_by': r.created_by.username,
        'can_decide': may_decide and can_approve(r, user),
    } for r in refunds] + [{
        'kind': 'transfer', 'id': t.pk, 'number': t.transfer_number, 'date': t.transfer_date.isoformat(),
        'client': t.from_client.name, 'client_id': t.from_client_id,
        'detail': f'→ {t.to_client.name}',
        'amount_sar': t.amount_sar, 'note': t.note, 'created_by': t.created_by.username,
        'can_decide': may_decide and can_approve(t, user),
    } for t in transfers]
    return sorted(rows, key=lambda r: r['date'], reverse=True)


STATEMENT_PAGE_SIZE = 50

@require_perm('statements', 'view')
def client_finance_statement(request, pk):
    """Client finance statement from JournalEntries (unified query path).

    Supports two modes, mirroring QuickBooks/Xero/Zoho:
      - `balance` (default): Balance Forward — opening + running balance rows.
      - `open`: Open Item — daftar invoice yang belum lunas per client.
    """
    client = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)

    mode = request.GET.get('mode', 'balance')
    if mode not in ('balance', 'open'):
        mode = 'balance'

    date_from = request.GET.get('from')
    date_to = request.GET.get('to')

    if date_from:
        date_from = _parse_date(date_from)
    if date_to:
        date_to = _parse_date(date_to)

    from django.utils import timezone as _tz
    # A statement opens on the last three calendar months: the opening balance
    # carries everything before it, so nothing is lost, and the page stays
    # short for a client with years of history. Only a bare URL gets the
    # default; an explicit empty `from` (the "All time" choice) means all time.
    if mode == 'balance' and 'from' not in request.GET and 'to' not in request.GET:
        today = _tz.localdate()
        month = today.month - 2
        date_from = date(today.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)

    # The aging must speak about the same period as the statement below it,
    # otherwise a filtered statement and its aging disagree about what is owed.
    # "Today" for the overdue buckets follows the selected end date, so a
    # period-scoped statement ages its invoices as of that period's end.
    aging_as_of = date_to or _tz.localdate()
    aging = finance_queries.client_aging(client.pk, date_to=date_to)

    if mode == 'open':
        open_items = finance_queries.open_items(
            client.pk, date_to=date_to,
        )
        statement_payload = {
            "mode": "open",
            "transactions": [],
            "open_items": open_items["rows"],
            "count": len(open_items["rows"]),
            "total_open": open_items["total_remaining"],
            "opening_balance": 0,
            "closing_balance": open_items["total_remaining"],
            "total_debit": 0,
            "total_credit": 0,
        }
    else:
        # Reversed pairs are hidden unless asked for, with the running balance
        # recomputed without them (see client_ledger). Search narrows the rows
        # only; balances and totals stay the period's.
        show_voided = request.GET.get('voided') == '1'
        q = (request.GET.get('q') or '').strip()
        ledger = finance_queries.client_ledger(
            client.pk, date_from=date_from, date_to=date_to,
            hide_voided=not show_voided, q=q,
        )
        page_obj = Paginator(ledger["rows"], STATEMENT_PAGE_SIZE).get_page(request.GET.get('page'))
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
            "is_voided": r["is_voided"],
        } for r in page_obj.object_list]
        statement_payload = {
            "mode": "balance",
            "transactions": transactions,
            "open_items": [],
            "count": ledger["period_count"],
            "total_open": 0,
            "opening_balance": ledger["opening_balance"],
            "closing_balance": ledger["closing_balance"],
            "total_debit": ledger["total_debit"],
            "total_credit": ledger["total_credit"],
            "months": ledger["months"],
            "hidden_voided": ledger["hidden_voided"],
            "show_voided": show_voided,
            "q": q,
        }

    return inertia_render(request, 'Finance/ClientStatement', props={
        'pending_out': _pending_out_rows(request.user, client),
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
        'aging_as_of': aging_as_of.isoformat() if aging_as_of else None,
        'pagination': pagination_props(page_obj) if mode == 'balance' else None,
        'mode': mode,
        'date_from': date_from.isoformat() if date_from else None,
        'date_to': date_to.isoformat() if date_to else None,
        'seasons': season_choices(),
    })



def _report_branches(request):
    from ..models.branch import Branch
    return scope(Branch.objects.all(), request.user)


def _fund_flow_params(request):
    """(branch, from, to). The branch is one the user covers: Surabaya by
    default, otherwise the user's first branch."""
    today = date.today()
    date_from = _parse_date(request.GET.get('from')) or today.replace(day=1)
    date_to = _parse_date(request.GET.get('to')) or today
    branches = _report_branches(request)
    branch = request.GET.get('branch') or 'sby'
    if not branches.filter(code=branch).exists():
        fallback = 'sby' if branches.filter(code='sby').exists() else None
        branch = fallback or branches.order_by('code').values_list('code', flat=True).first()
    if branch is None:
        raise Http404
    return branch, date_from, date_to


@require_perm('statements', 'view')
def fund_flow_report(request):
    """Arus Dana: per-currency money in/out of a branch + realized FX profit."""
    from ..finance import fund_flow
    branch, date_from, date_to = _fund_flow_params(request)
    flow = fund_flow.fund_flow(branch=branch, date_from=date_from, date_to=date_to)
    fx = fund_flow.fx_profit(branch=branch, date_from=date_from, date_to=date_to)
    expenses_idr = fund_flow.branch_expenses_idr(branch, date_from=date_from, date_to=date_to)
    return inertia_render(request, 'Finance/FundFlow', props={
        'branch': branch,
        'expenses_idr': expenses_idr,
        'net_profit_idr': fund_flow.net_profit(fx),
        'branch_choices': [{'value': b.code, 'label': b.name} for b in _report_branches(request).order_by('code')],
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'seasons': season_choices(),
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
        'aging': finance_queries.ar_aging(as_of=_aging_as_of(request),
                                          clients=scope(Client.objects.all(), request.user)),
    })


@require_perm('statements', 'export')
def ar_aging_csv(request):
    from .helpers import csv_export_response
    aging = finance_queries.ar_aging(as_of=_aging_as_of(request), clients=scope(Client.objects.all(), request.user))
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


# ── Laporan cabang (Fase 3, 2026-10-19) ───────────────────────────────

def _branch_report_params(request):
    """(branch code, branches, period). Asking for a branch the user does not
    cover is a 404; covering none is handled by the views (redirect)."""
    from ..finance import branch_report as br
    branches = br.report_branches(request.user)
    codes = list(branches.values_list('code', flat=True))
    wanted = request.GET.get('branch')
    if wanted and wanted not in codes:
        raise Http404
    branch = wanted or ('sby' if 'sby' in codes else (codes[0] if codes else None))
    kind = request.GET.get('kind') if request.GET.get('kind') in br.KINDS else 'month'
    return branch, branches, br.period_bounds(kind, request.GET.get('value', ''))


def _iso_period(p):
    out = {**p, 'date_from': p['date_from'].isoformat(), 'date_to': p['date_to'].isoformat()}
    if p['prev']:
        out['prev'] = {**p['prev'], 'date_from': p['prev']['date_from'].isoformat(),
                       'date_to': p['prev']['date_to'].isoformat()}
    return out


@require_perm('statements', 'view')
def branch_report_view(request):
    """Laporan cabang: laba (= laba kurs), biaya operasional dan
    penggantiannya, posisi per akhir periode; pembanding periode sebelumnya."""
    from ..finance import branch_report as br
    branch, branches, period = _branch_report_params(request)
    if branch is None:
        messages.info(request, tr(request, 'No branch to report on.', 'Tidak ada cabang untuk dilaporkan.'))
        return redirect('fund_flow_report')
    report = br.branch_report(branch, period['date_from'], period['date_to'])
    previous = br.headline(branch, period['prev']['date_from'], period['prev']['date_to']) if period['prev'] else None
    delta = br.profit_delta(report['profit']['fx_idr'], previous['fx_idr']) if previous else None
    return inertia_render(request, 'Finance/BranchReport', props={
        'branch': branch,
        'branch_choices': [{'value': b.code, 'label': b.name} for b in branches],
        'period': _iso_period(period),
        'seasons': season_choices(),
        'report': report,
        'previous': previous,
        'profit_delta': delta,
    })


@require_perm('statements', 'export')
def branch_report_csv(request):
    from ..finance import branch_report as br
    from .helpers import csv_export_response
    branch, _branches, period = _branch_report_params(request)
    if branch is None:
        raise Http404
    rep = br.branch_report(branch, period['date_from'], period['date_to'])
    head = ['Branch report', branch, period['label'], period['date_from'].isoformat(), period['date_to'].isoformat()]
    unpriced = rep['profit']['unpriced']
    profit = rep['profit']['fx_idr']
    rows = [['Branch profit (FX, IDR)', f'Not priced ({unpriced} transfers without an original amount)' if profit is None else profit]]
    if profit is not None and unpriced:
        rows.append(['Transfers not priced', unpriced])
    rows += [[], ['Transfer', 'Date', 'SAR', 'IDR sent', 'Average rate', 'Send rate', 'FX profit (IDR)']]
    rows += [[t['remittance_number'], t['date'], t['sar'], t['idr_sent'], t['avg_rate'], t['send_rate'], t['profit_idr']]
             if t['profit_idr'] is not None else
             [t['remittance_number'], t['date'], t['sar'], t['idr_sent'], t['avg_rate'], t['send_rate'], 'Not priced']
             for t in rep['profit']['transfers']]
    e = rep['expenses']
    rows += [[], ['Operating expenses (IDR)', e['total']]]
    rows += [[c['name'], c['amount']] for c in e['by_category']]
    rows += [['Reimbursed', e['paid_back']], ['Claimed, waiting', e['claimed']], ['Not claimed yet', e['unclaimed']]]
    p = rep['position']
    rows += [[], ['Position as of', p['as_of']], ['Account', 'Kind', 'Currency', 'Balance']]
    rows += [[a['name'], a['kind'], a['currency'], a['native']] for a in p['accounts']]
    rows += [['Client receivables (SAR)', p['receivable_sar']], ['Client deposits (SAR)', p['deposits_sar']],
             ['Owed by head office (IDR)', p['owed_by_hq_idr']]]
    return csv_export_response(f'branch-report-{branch}-{period["value"]}.csv', head, rows)
