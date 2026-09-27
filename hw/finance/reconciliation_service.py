"""Bank reconciliation orchestration (Master Architecture v2.0 §52).

Statement entry is manual (typed in from a paper/PDF statement) — no file
parsing here. Matching a line is an explicit, individual action (never
automatic/fuzzy): the user picks one BankTransaction per line. This keeps
faith with v2.0's "never silently overwrite an internal fact with statement
data" — a mismatch surfaces as a difference for a human to resolve, not as
a correction the system applies on its own.
"""
from django.db import transaction

from django.db.models import Sum

from ..models.journal import JournalLine
from ..models.bank_transaction import BankTransaction
from ..models.reconciliation import BankStatement, BankStatementLine
from .errors import FinanceError


@transaction.atomic
def create_statement(*, account, period_start, period_end, opening_balance_sar,
                     closing_balance_sar, lines, created_by=None, note=''):
    """lines: iterable of {line_date, description, direction, amount_sar, reference}."""
    from ..models.bank import BankAccount

    kwargs = {'bank_account': account} if isinstance(account, BankAccount) else {'cash_account': account}
    statement = BankStatement.objects.create(
        period_start=period_start, period_end=period_end,
        opening_balance_sar=opening_balance_sar, closing_balance_sar=closing_balance_sar,
        note=note, created_by=created_by, **kwargs,
    )
    rows = []
    for l in lines:
        amt = int(l.get('amount_sar') or 0)
        if amt <= 0:
            continue
        rows.append(BankStatementLine(
            statement=statement, line_date=l['line_date'],
            description=l.get('description', ''), direction=l['direction'],
            amount_sar=amt, reference=l.get('reference', ''),
        ))
    BankStatementLine.objects.bulk_create(rows)
    return statement


def unmatched_transaction_candidates(statement_line):
    """BankTransaction rows on the same account, not yet matched to any
    statement line, as candidates for `match_line`. Caller narrows/sorts
    by date/amount proximity in the UI — this just scopes to the account."""
    account = statement_line.statement.account
    qs = BankTransaction.objects.filter(statement_lines__isnull=True).exclude(
        status=BankTransaction.STATUS_VOIDED,
    )
    if statement_line.statement.bank_account_id:
        qs = qs.filter(bank_account=account)
    else:
        qs = qs.filter(cash_account=account)
    return qs.order_by('-transaction_date')


class MatchMismatchError(FinanceError):
    """Line and transaction disagree on direction/amount — surfaced, not silently forced."""


@transaction.atomic
def match_line(statement_line, bank_transaction, *, force=False):
    """Link one statement line to one BankTransaction. Raises MatchMismatchError
    on a direction/amount disagreement unless `force=True` (the human has
    looked at it and decided to match anyway — e.g. a partial/combined
    transfer). Never invents or adjusts either side's numbers."""
    if not force and (
        statement_line.direction != bank_transaction.direction
        or statement_line.amount_sar != bank_transaction.amount_sar
    ):
        raise MatchMismatchError(
            f"Baris statement ({statement_line.direction} {statement_line.amount_sar:,}) "
            f"tidak cocok dengan transaksi ({bank_transaction.direction} {bank_transaction.amount_sar:,})"
        )
    statement_line.matched_transaction = bank_transaction
    statement_line.save(update_fields=['matched_transaction'])
    bank_transaction.status = BankTransaction.STATUS_RECONCILED
    bank_transaction.save(update_fields=['status'])
    return statement_line


def unmatch_line(statement_line):
    tx = statement_line.matched_transaction
    statement_line.matched_transaction = None
    statement_line.save(update_fields=['matched_transaction'])
    if tx and not tx.statement_lines.exists():
        tx.status = BankTransaction.STATUS_POSTED
        tx.save(update_fields=['status'])


def _book_balance_through(ledger_account_id, through_date):
    """Net debit-credit on an account for entries DATED on or before
    `through_date` — deliberately entry_date, not created_at: a statement
    period is about when the money moved, not when it was recorded (unlike
    queries.account_balance's `as_of`, which is a point-in-time/bitemporal
    snapshot by created_at and isn't what a reconciliation period means)."""
    agg = JournalLine.objects.filter(
        account_id=ledger_account_id, journal_entry__entry_date__lte=through_date,
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or 0) - (agg['c'] or 0)


def statement_summary(statement):
    """Book balance (JournalLine projection, as of period_end) vs the
    statement's claimed closing balance, plus match progress."""
    account = statement.account
    book_balance = _book_balance_through(account.ledger_account_id, statement.period_end)
    lines = list(statement.lines.all())
    return {
        'book_balance_sar': book_balance,
        'statement_closing_sar': statement.closing_balance_sar,
        'difference_sar': statement.closing_balance_sar - book_balance,
        'lines_total': len(lines),
        'lines_matched': sum(1 for l in lines if l.matched_transaction_id),
        'is_fully_matched': statement.is_fully_matched,
    }
