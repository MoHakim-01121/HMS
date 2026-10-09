"""Transfer & currency exchange (Penukaran Valas) pages — hw/finance/exchange_service.py."""
from datetime import date

from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..finance import exchange_service
from ..finance.errors import FinanceError
from ..models.currency_exchange import CurrencyExchange
from ..branch_scope import branch_codes, get_in_scope_or_404, scope
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
        'exchange_date': ex.exchange_date.strftime('%d/%m/%Y'),
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


@require_perm('payments', 'view')
def exchange_list(request):
    qs = scope(CurrencyExchange.objects.all(), request.user).select_related('from_account', 'to_account')
    return inertia_render(request, 'Finance/Exchanges', props={'exchanges': [_row(ex) for ex in qs]})


def _form_props(user, data=None, error=None):
    # A transfer stays inside one branch: the user's own accounts.
    choices = money_account_choices(branches=branch_codes(user))
    # Last active rate per pair, so the form can warn about a likely typo live.
    last_rates = {}
    for ex in scope(CurrencyExchange.objects.filter(status=CurrencyExchange.STATUS_ACTIVE), user).order_by('-exchange_date', '-pk').select_related('from_account', 'to_account')[:50]:
        last_rates.setdefault(f'{ex.from_currency}>{ex.to_currency}', float(ex.rate))
    return {
        'account_choices': choices,
        'last_rates': last_rates,
        'warning_pct': float(exchange_service.RATE_WARNING_PCT),
        'form': data or {'exchange_date': date.today().isoformat()},
        'error': error,
    }


@require_perm('payments', 'create')
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
            ex = exchange_service.record_exchange(
                from_account=resolve_money_account(data['from_account']),
                amount_out=_int(data['amount_out']),
                to_account=resolve_money_account(data['to_account']),
                amount_in=_int(data['amount_in']),
                exchange_date=exchange_date, created_by=request.user,
                reference=data['reference'].strip(), note=data['note'].strip(), proof=proof,
            )
        except FinanceError as e:
            error = str(e)
    if error:
        return inertia_render(request, 'Finance/ExchangeForm', props=_form_props(request.user, data, error))
    messages.success(request, f'{ex.exchange_number} tercatat: {ex.amount_out:,} {ex.from_currency} → {ex.amount_in:,} {ex.to_currency}.')
    return redirect('exchange_list')


@require_perm('payments', 'delete')
@require_POST
def exchange_void(request, pk):
    ex = get_in_scope_or_404(CurrencyExchange.objects.all(), request.user, pk=pk)
    try:
        exchange_service.void_exchange(
            ex, reason=(request.POST.get('reason') or '').strip(), voided_by=request.user,
        )
        messages.success(request, f'{ex.exchange_number} dibatalkan.')
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('exchange_list')
