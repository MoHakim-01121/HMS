"""Bank reconciliation views — statement entry/import + line matching.

UI surface for hw/finance/reconciliation_service.py and statement_import.py.
Reading is gated under 'statements' (same read-only-reporting class as
Client Ledger / Trial Balance / Bank Balances — that module is genuinely
view/export-only for every role, see permissions.py). Entering a statement
and matching lines are real edits, gated under 'remittance' instead — same
cash-movement sensitivity class already used for Settlement, and the one
'statements' itself deliberately never grants.

Amounts are in the account's own currency throughout.
"""
import json
from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models.bank_transaction import BankTransaction
from ..models.reconciliation import BankStatement, BankStatementLine
from ..finance import reconciliation_service as rs
from ..finance import statement_import as si
from ..finance.errors import FinanceError
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


def _account_choices():
    return money_account_choices()


@require_perm('statements', 'view')
def reconciliation_list(request):
    statements = BankStatement.objects.select_related('account').all()
    return inertia_render(request, 'Reconciliation/List', props={
        'statements': [_statement_props(s) for s in statements],
        'account_choices': _account_choices(),
    })


def _payload(request):
    try:
        return json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        return request.POST


@require_perm('remittance', 'edit')
def reconciliation_new(request):
    if request.method != 'POST':
        return redirect('reconciliation_list')
    data = _payload(request)
    account = resolve_money_account(data.get('account'))

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

    messages.success(request, 'Statement tercatat.')
    return redirect('reconciliation_detail', pk=statement.pk)


def _import_props(form=None, preview=None, error=None):
    return {
        'account_choices': _account_choices(),
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


@require_perm('remittance', 'edit')
def reconciliation_import(request):
    """Import a bank CSV. Two steps on one page: `preview` parses the text
    (with the user's column mapping, if any) and shows what would be saved;
    `save` creates the statement from the same text and mapping."""
    if request.method != 'POST':
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props())
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
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(form, error=str(e)))
    except (ValueError, TypeError):
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(form, error='Pemetaan kolom tidak valid.'))
    preview = _preview_props(result)
    form['mapping'] = json.dumps(result['mapping'])

    if P.get('step') != 'save':
        # Fill the statement fields the file itself answers, unless typed already.
        for key in ('period_start', 'period_end', 'opening_balance', 'closing_balance'):
            if not form[key] and preview[key] is not None:
                form[key] = str(preview[key])
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(form, preview))

    account = resolve_money_account(form['account'])
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
        return inertia_render(request, 'Reconciliation/ImportForm', props=_import_props(form, preview, str(e)))
    left_out = len(result['lines']) - len(lines)
    msg = f'{len(lines)} baris diimpor dari {form["filename"] or "CSV"}.'
    if left_out:
        msg += f' {left_out} baris di luar periode tidak diikutkan.'
    messages.success(request, msg)
    return redirect('reconciliation_detail', pk=statement.pk)


@require_perm('statements', 'view')
def reconciliation_detail(request, pk):
    statement = get_object_or_404(BankStatement, pk=pk)
    return inertia_render(request, 'Reconciliation/Detail', props={
        'statement': _statement_props(statement, with_lines=True),
    })


@require_perm('remittance', 'edit')
def reconciliation_match(request, pk):
    line = get_object_or_404(BankStatementLine, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)
    data = _payload(request)
    tx = BankTransaction.objects.filter(pk=data.get('transaction_id')).first()
    if tx is None:
        messages.error(request, 'Transaksi tidak ditemukan.')
        return redirect('reconciliation_detail', pk=line.statement_id)

    force = str(data.get('force', '')).lower() in ('1', 'true', 'on')
    try:
        rs.match_line(line, tx, force=force)
        messages.success(request, 'Baris berhasil dicocokkan.')
    except rs.MatchMismatchError as e:
        messages.error(request, f'{e} — centang "paksa cocokkan" kalau tetap ingin melanjutkan.')
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('reconciliation_detail', pk=line.statement_id)


@require_perm('remittance', 'edit')
@require_POST
def reconciliation_match_suggested(request, pk):
    statement = get_object_or_404(BankStatement, pk=pk)
    try:
        n = rs.match_suggested(statement)
        messages.success(request, f'{n} baris dicocokkan sesuai saran.')
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('reconciliation_detail', pk=pk)


@require_perm('remittance', 'edit')
def reconciliation_unmatch(request, pk):
    line = get_object_or_404(BankStatementLine, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)
    rs.unmatch_line(line)
    messages.success(request, 'Pencocokan dibatalkan.')
    return redirect('reconciliation_detail', pk=line.statement_id)
