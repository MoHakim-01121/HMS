from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404

from inertia import render as inertia_render

from ..finance import queries as finance_queries
from ..models import Client
from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..permissions import require_perm
from .helpers import _parse_date, serialize_journal_entry, journal_line_dimension


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
        'account', 'client', 'invoice', 'reservation', 'service_item', 'penalty',
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
    overview = finance_queries.clients_overview()
    clients = Client.objects.in_bulk([r['client_id'] for r in overview])
    rows = []
    for r in overview:
        client = clients.get(r['client_id'])
        rows.append({
            **r,
            'name': client.name if client else f"Client #{r['client_id']}",
        })
    return inertia_render(request, 'Finance/Statements', props={'clients': rows})


@require_perm('statements', 'view')
def bank_account_list(request):
    """Bank/cash balance overview (v2.0 §78). Read-only: accounts themselves
    are business-managed data (Django admin), balance is a pure projection
    from the journal (finance.queries.money_accounts_overview)."""
    from ..models.branch import Branch

    branch = request.GET.get('branch')
    rows = finance_queries.money_accounts_overview(branch=branch or None)
    return inertia_render(request, 'Finance/BankAccounts', props={
        'accounts': rows,
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True)],
        'branch_filter': branch or '',
    })


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
        },
        'statement': statement_payload,
        'aging': aging,
        'mode': mode,
        'date_from': date_from.isoformat() if date_from else None,
        'date_to': date_to.isoformat() if date_to else None,
    })

