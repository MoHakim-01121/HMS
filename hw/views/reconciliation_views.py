"""Bank reconciliation views — statement entry + line matching.

UI surface for hw/finance/reconciliation_service.py (FASE I remainder, §52).
Reading is gated under 'statements' (same read-only-reporting class as
Client Ledger / Trial Balance / Bank Balances — that module is genuinely
view/export-only for every role, see permissions.py). Entering a statement
and matching lines are real edits, gated under 'remittance' instead — same
cash-movement sensitivity class already used for Settlement, and the one
'statements' itself deliberately never grants.
"""
import json


from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models.bank_transaction import BankTransaction
from ..models.reconciliation import BankStatement, BankStatementLine
from ..finance import reconciliation_service as rs
from ..finance.errors import FinanceError
from ..permissions import require_perm
from .helpers import _parse_date, _to_float, money_account_choices, resolve_money_account


def _line_props(line, candidates=None):
    tx = line.matched_transaction
    return {
        'id': line.pk,
        'line_date': line.line_date.isoformat(),
        'description': line.description,
        'direction': line.direction,
        'amount_sar': line.amount_sar,
        'reference': line.reference,
        'matched_transaction': {
            'id': tx.pk, 'direction': tx.direction, 'amount_sar': tx.amount_sar,
            'source_type': tx.source_type, 'source_id': tx.source_id,
            'transaction_date': tx.transaction_date.isoformat(),
        } if tx else None,
        'candidates': [{
            'id': c.pk, 'direction': c.direction, 'amount_sar': c.amount_sar,
            'source_type': c.source_type, 'source_id': c.source_id,
            'transaction_date': c.transaction_date.isoformat(), 'reference': c.reference,
        } for c in (candidates or [])],
    }


def _statement_props(statement, with_candidates=False):
    summary = rs.statement_summary(statement)
    return {
        'id': statement.pk,
        'account_label': str(statement.account),
        'period_start': statement.period_start.isoformat(),
        'period_end': statement.period_end.isoformat(),
        'opening_balance_sar': statement.opening_balance_sar,
        'closing_balance_sar': statement.closing_balance_sar,
        'note': statement.note,
        **summary,
        'lines': [
            _line_props(l, rs.unmatched_transaction_candidates(l) if with_candidates and not l.matched_transaction_id else None)
            for l in statement.lines.select_related('matched_transaction').all()
        ],
    }


@require_perm('statements', 'view')
def reconciliation_list(request):
    statements = BankStatement.objects.select_related('bank_account', 'cash_account').all()
    return inertia_render(request, 'Reconciliation/List', props={
        'statements': [_statement_props(s) for s in statements],
        'account_choices': money_account_choices(),
    })


@require_perm('remittance', 'edit')
def reconciliation_new(request):
    if request.method != 'POST':
        return redirect('reconciliation_list')

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    bank_account, cash_account = resolve_money_account(data.get('account'))
    account = bank_account or cash_account
    if account is None:
        messages.error(request, 'Rekening harus dipilih.')
        return redirect('reconciliation_list')

    period_start = _parse_date(data.get('period_start'))
    period_end = _parse_date(data.get('period_end'))
    if not period_start or not period_end:
        messages.error(request, 'Periode harus diisi.')
        return redirect('reconciliation_list')

    raw_lines = data.get('lines', '')
    try:
        line_rows = json.loads(raw_lines) if isinstance(raw_lines, str) else (raw_lines or [])
    except (json.JSONDecodeError, ValueError):
        line_rows = []

    lines = []
    for row in line_rows:
        amt = _to_float(row.get('amount_sar', 0))
        line_date = _parse_date(row.get('line_date'))
        if not amt or amt <= 0 or not line_date or row.get('direction') not in ('in', 'out'):
            continue
        lines.append({
            'line_date': line_date, 'direction': row['direction'], 'amount_sar': int(amt),
            'description': row.get('description', ''), 'reference': row.get('reference', ''),
        })

    try:
        statement = rs.create_statement(
            account=account, period_start=period_start, period_end=period_end,
            opening_balance_sar=int(_to_float(data.get('opening_balance_sar', 0))),
            closing_balance_sar=int(_to_float(data.get('closing_balance_sar', 0))),
            lines=lines, created_by=request.user, note=data.get('note', ''),
        )
    except FinanceError as e:
        messages.error(request, str(e))
        return redirect('reconciliation_list')

    messages.success(request, 'Statement tercatat.')
    return redirect('reconciliation_detail', pk=statement.pk)


@require_perm('statements', 'view')
def reconciliation_detail(request, pk):
    statement = get_object_or_404(BankStatement, pk=pk)
    return inertia_render(request, 'Reconciliation/Detail', props={
        'statement': _statement_props(statement, with_candidates=True),
    })


@require_perm('remittance', 'edit')
def reconciliation_match(request, pk):
    line = get_object_or_404(BankStatementLine, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

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
def reconciliation_unmatch(request, pk):
    line = get_object_or_404(BankStatementLine, pk=pk)
    if request.method != 'POST':
        return redirect('reconciliation_detail', pk=line.statement_id)
    rs.unmatch_line(line)
    messages.success(request, 'Pencocokan dibatalkan.')
    return redirect('reconciliation_detail', pk=line.statement_id)
