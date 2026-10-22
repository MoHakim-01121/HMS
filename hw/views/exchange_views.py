"""Transfer & currency exchange (Penukaran Valas) pages — hw/finance/exchange_service.py."""
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..branch_scope import branch_codes, get_in_scope_or_404, scope
from ..finance import exchange_service
from ..finance.errors import FinanceError
from ..i18n import tr
from ..models.currency_exchange import CurrencyExchange
from ..permissions import require_perm
from .helpers import _parse_date, money_account_choices, resolve_money_account, validate_proof_file


def _int(value):
    try:
        return int(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _row(ex):
    return {
        'id': ex.pk,
        'exchange_number': ex.exchange_number,
        'exchange_date': ex.exchange_date.isoformat(),
        'from_label': str(ex.from_account),
        'from_currency': ex.from_currency,
        'amount_out': ex.amount_out,
        'to_label': str(ex.to_account),
        'to_currency': ex.to_currency,
        'amount_in': ex.amount_in,
        'rate': float(ex.rate),
        'reference': ex.reference,
        'status': ex.status,
        'proof_url': ex.proof.url if ex.proof else None,
    }


@require_perm('bank', 'view')
def exchange_list(request):
    """Transfer and Exchange (Record View HMS canvas): no KPIs; the month's
    transfers and exchanges with a summary under the table."""
    from django.core.paginator import Paginator
    from django.db.models import Q

    from .helpers import csv_list, list_per_page, list_period, pagination_props
    q = request.GET.get('q', '').strip()
    types = csv_list(request, 'type', ['transfer', 'exchange'])
    accounts = csv_list(request, 'acct')
    voided = request.GET.get('voided') == '1'
    sort = request.GET.get('sort', '-date')
    date_from, date_to, period = list_period(request)
    qs = scope(CurrencyExchange.objects.all(), request.user).select_related('from_account', 'to_account')
    if q:
        qs = qs.filter(Q(exchange_number__icontains=q) | Q(reference__icontains=q) | Q(note__icontains=q)
                       | Q(from_account__name__icontains=q) | Q(to_account__name__icontains=q))
    if date_from:
        qs = qs.filter(exchange_date__gte=date_from)
    if date_to:
        qs = qs.filter(exchange_date__lte=date_to)
    period_rows = list(qs.order_by('exchange_date' if sort == 'date' else '-exchange_date', '-pk'))
    is_ex = lambda ex: ex.from_currency != ex.to_currency
    live = [ex for ex in period_rows if ex.status == CurrencyExchange.STATUS_ACTIVE]
    acc_n = {}
    for ex in period_rows:
        for a in {str(ex.from_account), str(ex.to_account)}:
            acc_n[a] = acc_n.get(a, 0) + 1
    rows = [ex for ex in period_rows
            if (voided or ex.status == CurrencyExchange.STATUS_ACTIVE)
            and (not types or ('exchange' if is_ex(ex) else 'transfer') in types)
            and (not accounts or str(ex.from_account) in accounts or str(ex.to_account) in accounts)]
    page_obj = Paginator(rows, list_per_page(request)).get_page(request.GET.get('page'))
    ex_live = [ex for ex in live if is_ex(ex)]
    idr_to_sar = [ex for ex in ex_live if ex.from_currency == 'IDR' and ex.to_currency == 'SAR']
    summary = {
        'transfers': sum(1 for ex in live if not is_ex(ex)), 'exchanges': len(ex_live),
        'idr_out': sum(ex.amount_out for ex in idr_to_sar), 'sar_in': sum(ex.amount_in for ex in idr_to_sar),
    }
    summary['avg_rate'] = round(summary['idr_out'] / summary['sar_in']) if summary['sar_in'] else None
    years = sorted({d.year for d in scope(CurrencyExchange.objects.all(), request.user).dates('exchange_date', 'year')} | {date.today().year})
    return inertia_render(request, 'Finance/Exchanges', props={
        'exchanges': [_row(ex) for ex in page_obj],
        'filters': {'q': q, 'type': types, 'acct': accounts, 'voided': '1' if voided else '', 'sort': sort,
                    'per': list_per_page(request), **period},
        'years': years,
        'counts': {'transfer': sum(1 for ex in period_rows if not is_ex(ex)), 'exchange': sum(1 for ex in period_rows if is_ex(ex)),
                   'voided': sum(1 for ex in period_rows if ex.status != CurrencyExchange.STATUS_ACTIVE)},
        'account_counts': [{'name': k, 'count': v} for k, v in sorted(acc_n.items())],
        'summary': summary,
        'pagination': pagination_props(page_obj),
    })


@require_perm('bank', 'export')
def exchange_export_csv(request):
    from .helpers import csv_export_response
    qs = scope(CurrencyExchange.objects.all(), request.user).select_related('from_account', 'to_account').order_by('-exchange_date')
    return csv_export_response('transfers.csv', ['Number', 'Date', 'From', 'Out', 'Currency', 'To', 'In', 'Currency', 'Reference', 'Status'], [
        [ex.exchange_number, ex.exchange_date, str(ex.from_account), ex.amount_out, ex.from_currency,
         str(ex.to_account), ex.amount_in, ex.to_currency, ex.reference, ex.status] for ex in qs
    ])


def _form_props(user, data=None, error=None):
    # A transfer stays inside one branch: the user's own accounts, and the
    # advances its staff hold. "Give to staff" lists who may receive one.
    codes = branch_codes(user)
    choices = money_account_choices(branches=codes, staff=True, balances=True)
    from ..finance.staff_advance import branch_holders, display_name
    from ..models.branch import Branch
    holders = [
        {'value': f'give:{u.pk}:{b.code}', 'label': display_name(u), 'branch': b.code, 'user': u.pk}
        for b in Branch.objects.filter(is_active=True).order_by('code') if codes is None or b.code in codes
        for u in branch_holders(b.code)
    ]
    # Last active rate per pair, so the form can warn about a likely typo live.
    last_rates = {}
    for ex in scope(CurrencyExchange.objects.filter(status=CurrencyExchange.STATUS_ACTIVE), user).order_by('-exchange_date', '-pk').select_related('from_account', 'to_account')[:50]:
        last_rates.setdefault(f'{ex.from_currency}>{ex.to_currency}', float(ex.rate))
    return {
        'account_choices': choices,
        'staff_choices': holders,
        'last_rates': last_rates,
        'warning_pct': float(exchange_service.RATE_WARNING_PCT),
        'form': data or {'exchange_date': date.today().isoformat()},
        'error': error,
    }


def _target_account(user, value, source):
    """The transfer's target: an account token, or "give:<user>:<branch>" for
    a staff member who holds no advance yet in the source's currency (it is
    opened now)."""
    if not (value or '').startswith('give:'):
        return resolve_money_account(value, staff=True)
    from ..branch_scope import in_scope
    from ..finance.staff_advance import advance_account, branch_holders
    _, user_id, branch = (value.split(':') + ['', ''])[:3]
    if source is None:
        return None
    if not user_id.isdigit() or branch != source.branch_id or not in_scope(user, branch):
        raise FinanceError('Staf penerima harus dari cabang rekening asal.')
    holder = branch_holders(branch).filter(pk=user_id).first()
    if holder is None:
        raise FinanceError('Staf ini tidak aktif di cabang itu.')
    return advance_account(holder, branch, source.currency, create=True)


@require_perm('bank', 'create')
def exchange_new(request):
    if request.method != 'POST':
        return inertia_render(request, 'Finance/ExchangeForm', props=_form_props(request.user))

    P = request.POST
    data = {k: P.get(k, '') for k in ('from_account', 'amount_out', 'to_account', 'amount_in', 'exchange_date', 'reference', 'note')}
    proof = request.FILES.get('proof')
    error = validate_proof_file(proof) if proof else None
    exchange_date = _parse_date(data['exchange_date'])
    if not error and exchange_date is None:
        error = 'Tanggal transfer tidak valid.'
    if not error:
        try:
            source = resolve_money_account(data['from_account'], staff=True)
            # A staff member's first advance is opened with the transfer, and
            # only if the transfer goes through.
            with transaction.atomic():
                ex = exchange_service.record_exchange(
                    from_account=source,
                    amount_out=_int(data['amount_out']),
                    to_account=_target_account(request.user, data['to_account'], source),
                    amount_in=_int(data['amount_in']),
                    exchange_date=exchange_date, created_by=request.user,
                    reference=data['reference'].strip(), note=data['note'].strip(), proof=proof,
                )
        except FinanceError as e:
            error = str(e)
    if error:
        return inertia_render(request, 'Finance/ExchangeForm', props=_form_props(request.user, data, error))
    messages.success(request, tr(request, f'{ex.exchange_number} recorded: {ex.amount_out:,} {ex.from_currency} → {ex.amount_in:,} {ex.to_currency}.', f'{ex.exchange_number} tercatat: {ex.amount_out:,} {ex.from_currency} → {ex.amount_in:,} {ex.to_currency}.'))
    return redirect('exchange_list')


@require_perm('bank', 'delete')
@require_POST
def exchange_void(request, pk):
    ex = get_in_scope_or_404(CurrencyExchange.objects.all(), request.user, pk=pk)
    try:
        exchange_service.void_exchange(
            ex, reason=(request.POST.get('reason') or '').strip(), voided_by=request.user,
        )
        messages.success(request, tr(request, f'{ex.exchange_number} cancelled.', f'{ex.exchange_number} dibatalkan.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('exchange_list')
