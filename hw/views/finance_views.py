from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404

from inertia import render as inertia_render

from .. import ledger
from ..models import Client
from ..models.journal import JournalEntry, JournalLine, LedgerAccount
from ..permissions import require_perm
from .helpers import get_active_company, _parse_date, serialize_journal_entry, journal_line_dimension


@require_perm('invoice', 'view')
def journal_list(request):
    company = get_active_company(request)
    qs = JournalEntry.objects.filter(company=company).annotate(
        debit=Sum('lines__debit'),
        credit=Sum('lines__credit'),
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
        'entries': [serialize_journal_entry(e) for e in page.object_list],
        'type_choices': JournalEntry.TYPE_CHOICES,
        'page_num': page.number,
        'num_pages': paginator.num_pages,
        'total': paginator.count,
        'filters': {'type': entry_type, 'date_from': date_from.isoformat() if date_from else '', 'date_to': date_to.isoformat() if date_to else '', 'q': q},
    })


@require_perm('invoice', 'view')
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


@require_perm('invoice', 'view')
def trial_balance(request):
    company = get_active_company(request)
    qs = JournalLine.objects.filter(journal_entry__company=company)

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


@require_perm('clients', 'view')
def statements_list(request):
    overview = ledger.clients_overview()
    clients = Client.objects.in_bulk([r['client_id'] for r in overview])
    rows = []
    for r in overview:
        client = clients.get(r['client_id'])
        rows.append({
            **r,
            'name': client.name if client else f"Client #{r['client_id']}",
        })
    return inertia_render(request, 'Finance/Statements', props={'clients': rows})
