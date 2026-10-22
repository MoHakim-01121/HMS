"""Bank reconciliation views — statement entry/import + line matching.

UI surface for hw/finance/reconciliation_service.py and statement_import.py.
Gated under 'bank' with bank accounts and transfers: reading needs view,
entering a statement and matching lines need edit.

Amounts are in the account's own currency throughout.
"""
import json
from datetime import date

from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..branch_scope import branch_codes, get_in_scope_or_404, in_scope, scope
from ..finance import reconciliation_service as rs
from ..finance import statement_import as si
from ..finance.errors import FinanceError
from ..i18n import tr
from ..models.bank_transaction import BankTransaction
from ..models.reconciliation import BankStatement, BankStatementLine
from ..permissions import require_perm
from ..utils import round_half_up
from .helpers import _parse_date, _to_float, money_account_choices, request_data, resolve_money_account

# Cash-book source → page that explains the movement.
_SOURCE_LINKS = {
    'PaymentRecord': '/finance/payments/{id}/',
    'Remittance': '/remittance/{id}/',
    'ExpensePayment': None,
    'CurrencyExchangeIn': '/finance/exchanges/',
    'CurrencyExchangeOut': '/finance/exchanges/',
}


def _tx_props(tx):
    link = _SOURCE_LINKS.get(tx.source_type)
    return {
        'id': tx.pk, 'direction': tx.direction, 'amount': tx.amount, 'currency': tx.currency,
        'source_type': tx.source_type, 'source_id': tx.source_id, 'reference': tx.reference,
        'transaction_date': tx.transaction_date.isoformat(),
        'link': link.format(id=tx.source_id) if link else None,
    }


def _line_props(line, candidates=None, suggested=None):
    tx = line.matched_transaction
    return {
        'id': line.pk,
        'line_date': line.line_date.isoformat(),
        'description': line.description,
        'direction': line.direction,
        'amount': line.amount,
        'reference': line.reference,
        'matched_transaction': _tx_props(tx) if tx else None,
        'suggested': _tx_props(suggested) if suggested else None,
        'candidates': [_tx_props(c) for c in (candidates or [])],
    }


def _statement_props(statement, with_lines=False):
    props = {
        'id': statement.pk,
        'account_label': str(statement.account),
        'period_start': statement.period_start.isoformat(),
        'period_end': statement.period_end.isoformat(),
        'opening_balance': statement.opening_balance,
        'closing_balance': statement.closing_balance,
        'note': statement.note,
        'source_filename': statement.source_filename,
        **rs.statement_summary(statement),
    }
    if with_lines:
        suggestions = rs.suggest_matches(statement)
        props['lines'] = [
            _line_props(
                l,
                rs.unmatched_transaction_candidates(l) if not l.matched_transaction_id else None,
                suggestions.get(l.pk),
            )
            for l in statement.lines.select_related('matched_transaction').all()
        ]
        props['suggested_count'] = len(suggestions)
    return props


def _account_choices(user):
    return money_account_choices(branches=branch_codes(user))


def _resolve_account(request, value):
    """An active account of the user's branches, or None."""
    account = resolve_money_account(value)
    return account if account is not None and in_scope(request.user, account.branch_id) else None


@require_perm('bank', 'view')
def reconciliation_list(request):
    """Bank Reconciliation (Record View HMS canvas): no KPIs; one row per
    statement with its closing balance, lines matched and the difference."""
    from django.core.paginator import Paginator

    from .helpers import csv_list, list_per_page, pagination_props
    q = request.GET.get('q', '').strip().lower()
    statuses = csv_list(request, 'status', ['wip', 'done'])
    accounts = csv_list(request, 'acct')
    statements = scope(BankStatement.objects.all(), request.user).select_related('account').order_by('-period_end', '-pk')
    rows = [_statement_props(s) for s in statements]
    for r in rows:
        r['state'] = 'done' if r['is_fully_matched'] and r['difference'] == 0 else 'wip'
    counts = {'wip': sum(1 for r in rows if r['state'] == 'wip'), 'done': sum(1 for r in rows if r['state'] == 'done')}
    acc_n = {}
    for r in rows:
        acc_n[r['account_label']] = acc_n.get(r['account_label'], 0) + 1
    shown = [r for r in rows if (not q or q in f"{r['account_label']} {r['period_start']} {r['period_end']}".lower())
             and (not statuses or r['state'] in statuses) and (not accounts or r['account_label'] in accounts)]
    page_obj = Paginator(shown, list_per_page(request)).get_page(request.GET.get('page'))
    return inertia_render(request, 'Reconciliation/List', props={
        'statements': list(page_obj),
        'account_choices': _account_choices(request.user),
        'filters': {'q': q, 'status': statuses, 'acct': accounts, 'per': list_per_page(request)},
        'counts': counts, 'account_counts': [{'name': k, 'count': v} for k, v in sorted(acc_n.items())],
        'pagination': pagination_props(page_obj),
    })


def _payload(request):
    try:
        return json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        return request.POST


@require_perm('bank', 'edit')
def reconciliation_new(request):
    if request.method != 'POST':
        return redirect('reconciliation_list')
    data = _payload(request)
    account = _resolve_account(request, data.get('account'))

    raw_lines = data.get('lines', '')
    try:
        line_rows = json.loads(raw_lines) if isinstance(raw_lines, str) else (raw_lines or [])
    except (json.JSONDecodeError, ValueError):
        line_rows = []
    lines = []
    for row in line_rows:
        amt = _to_float(row.get('amount', 0))
        line_date = _parse_date(row.get('line_date'))
        if not amt or amt <= 0 or not line_date or row.get('direction') not in ('in', 'out'):
            continue
        lines.append({
            'line_date': line_date, 'direction': row['direction'], 'amount': round_half_up(amt),
            'description': row.get('description', ''), 'reference': row.get('reference', ''),
        })

    try:
        statement = rs.create_statement(
            account=account, period_start=_parse_date(data.get('period_start')),
            period_end=_parse_date(data.get('period_end')),
            opening_balance=round_half_up(_to_float(data.get('opening_balance', 0))),
            closing_balance=round_half_up(_to_float(data.get('closing_balance', 0))),
            lines=lines, created_by=request.user, note=data.get('note', ''),
        )
    except FinanceError as e:
        messages.error(request, str(e))
        return redirect('reconciliation_list')

    messages.success(request, tr(request, 'Statement recorded.', 'Statement tercatat.'))
    return redirect('reconciliation_detail', pk=statement.pk)


def _import_props(user, form=None, preview=None, error=None):
    return {
        'account_choices': _account_choices(user),
        'fields': list(si.FIELDS),
        'form': form or {},
        'preview': preview,
        'error': error,
    }


def _preview_props(result):
    return {
        'headers': result['headers'],
        'mapping': result['mapping'],
        'lines': [{**l, 'line_date': l['line_date'].isoformat()} for l in result['lines']],
        'skipped': result['skipped'],
        'opening_balance': result['opening_balance'],
        'closing_balance': result['closing_balance'],
        'period_start': result['period_start'].isoformat() if result['period_start'] else None,
        'period_end': result['period_end'].isoformat() if result['period_end'] else None,
    }


@require_perm('bank', 'edit')
def reconciliation_import(request):
    """Import a bank CSV. Two steps on one page: `preview` parses the text
    (with the user's column mapping, if any) and shows what would be saved;
    `save` creates the statement from the same text and mapping."""
    if request.method != 'POST':
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(request.user))
    P = request_data(request)
    form = {k: str(P.get(k) or '') for k in ('account', 'csv_text', 'filename', 'mapping', 'period_start',
                                       'period_end', 'opening_balance', 'closing_balance', 'note')}
    try:
        mapping = json.loads(form['mapping']) if form['mapping'] else None
        if mapping is not None and not isinstance(mapping, dict):
            mapping = None
    except ValueError:
        mapping = None
    # Some exports print dd/mm only; the year comes from the period, else today.
    hint = _parse_date(form['period_start']) or _parse_date(form['period_end']) or date.today()
    try:
        result = si.parse(form['csv_text'], mapping=mapping, default_year=hint.year)
    except si.ImportError_ as e:
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(request.user, form, error=str(e)))
    except (ValueError, TypeError):
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(request.user, form, error='Pemetaan kolom tidak valid.'))
    preview = _preview_props(result)
    form['mapping'] = json.dumps(result['mapping'])

    if P.get('step') != 'save':
        # Fill the statement fields the file itself answers, unless typed already.
        for key in ('period_start', 'period_end', 'opening_balance', 'closing_balance'):
            if not form[key] and preview[key] is not None:
                form[key] = str(preview[key])
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(request.user, form, preview))

    account = _resolve_account(request, form['account'])
    period_start, period_end = _parse_date(form['period_start']), _parse_date(form['period_end'])
    lines = [l for l in result['lines'] if period_start and period_end and period_start <= l['line_date'] <= period_end]
    try:
        statement = rs.create_statement(
            account=account, period_start=period_start, period_end=period_end,
            opening_balance=round_half_up(_to_float(form['opening_balance'])),
            closing_balance=round_half_up(_to_float(form['closing_balance'])),
            lines=lines, created_by=request.user, note=form['note'],
            source_filename=form['filename'][:255],
        )
    except FinanceError as e:
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(request.user, form, preview, str(e)))
    left_out = len(result['lines']) - len(lines)
    msg = tr(request, f'{len(lines)} lines imported from {form["filename"] or "CSV"}.',
             f'{len(lines)} baris diimpor dari {form["filename"] or "CSV"}.')
    if left_out:
        msg += tr(request, f' {left_out} lines outside the period were left out.',
                  f' {left_out} baris di luar periode tidak diikutkan.')
    messages.success(request, msg)
    return redirect('reconciliation_detail', pk=statement.pk)


@require_perm('bank', 'view')
def reconciliation_detail(request, pk):
    statement = get_in_scope_or_404(BankStatement.objects.all(), request.user, pk=pk)
    return inertia_render(request, 'Reconciliation/Detail', props={
        'statement': _statement_props(statement, with_lines=True),
    })


@require_perm('bank', 'edit')
def reconciliation_match(request, pk):
    line = get_in_scope_or_404(BankStatementLine.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)
    data = _payload(request)
    tx = BankTransaction.objects.filter(pk=data.get('transaction_id')).first()
    if tx is None:
        messages.error(request, tr(request, 'Transaction not found.', 'Transaksi tidak ditemukan.'))
        return redirect('reconciliation_detail', pk=line.statement_id)

    force = str(data.get('force', '')).lower() in ('1', 'true', 'on')
    try:
        rs.match_line(line, tx, force=force)
        messages.success(request, tr(request, 'Line matched.', 'Baris berhasil dicocokkan.'))
    except rs.MatchMismatchError as e:
        messages.error(request, tr(request, f'{e} — tick "force match" to go ahead anyway.', f'{e} — centang "paksa cocokkan" kalau tetap ingin melanjutkan.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('reconciliation_detail', pk=line.statement_id)


@require_perm('bank', 'edit')
@require_POST
def reconciliation_match_suggested(request, pk):
    statement = get_in_scope_or_404(BankStatement.objects.all(), request.user, pk=pk)
    try:
        n = rs.match_suggested(statement)
        messages.success(request, tr(request, f'{n} lines matched as suggested.', f'{n} baris dicocokkan sesuai saran.'))
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('reconciliation_detail', pk=pk)


@require_perm('bank', 'edit')
def reconciliation_unmatch(request, pk):
    line = get_in_scope_or_404(BankStatementLine.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)
    rs.unmatch_line(line)
    messages.success(request, tr(request, 'Match undone.', 'Pencocokan dibatalkan.'))
    return redirect('reconciliation_detail', pk=line.statement_id)
