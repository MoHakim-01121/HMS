"""Bank reconciliation orchestration (Master Architecture v2.0 §52).

A statement is entered by hand or imported from the bank's CSV export
(statement_import.py). Everything is in the account's own currency and is
compared against that account's cash book (BankTransaction.amount).

Matching stays an explicit human action: the system SUGGESTS a transaction
for a line (same direction, same amount, date within a few days, each
transaction used once) but never links anything on its own. A mismatch is
surfaced as a difference for a human to resolve, not corrected silently.

A match is a group (BankMatch): one or more statement lines against one or
more cash-book rows whose signed amounts add up to the same total — one
transfer paying two invoices, or a salary run and its transfer fees booked
as one expense.
"""
from datetime import timedelta

from django.db import transaction

from ..models.bank_transaction import BankTransaction
from ..models.reconciliation import BankMatch, BankStatement, BankStatementLine
from .errors import FinanceError

# How far a statement line's date may be from the cash-book date and still be
# suggested as the same movement (bank value dates lag a day or two).
SUGGEST_DAYS = 3


@transaction.atomic
def create_statement(*, account, period_start, period_end, opening_balance, closing_balance,
                     lines, created_by=None, note='', source_filename=''):
    """lines: iterable of {line_date, description, direction, amount, reference}
    in the account's currency."""
    if account is None:
        raise FinanceError('Rekening harus dipilih.')
    if not period_start or not period_end or period_end < period_start:
        raise FinanceError('Periode statement tidak valid.')
    rows = []
    for l in lines:
        amt = int(l.get('amount') or 0)
        if amt <= 0:
            continue
        if l.get('direction') not in ('in', 'out'):
            raise FinanceError('Arah baris harus masuk atau keluar.')
        if not (period_start <= l['line_date'] <= period_end):
            raise FinanceError(f"Baris tanggal {l['line_date']:%d/%m/%Y} di luar periode statement.")
        rows.append(l | {'amount': amt})
    statement = BankStatement.objects.create(
        currency=account.currency, period_start=period_start, period_end=period_end,
        opening_balance=int(opening_balance or 0), closing_balance=int(closing_balance or 0),
        note=note, source_filename=source_filename, created_by=created_by, account=account,
    )
    BankStatementLine.objects.bulk_create([
        BankStatementLine(
            statement=statement, line_date=l['line_date'], description=(l.get('description') or '')[:255],
            direction=l['direction'], amount=l['amount'], reference=(l.get('reference') or '')[:200],
        ) for l in rows
    ])
    return statement


def _open_transactions(statement):
    """Live cash-book rows of the statement's account not yet matched."""
    return BankTransaction.objects.filter(
        match__isnull=True, amount__isnull=False, account=statement.account,
    ).exclude(status=BankTransaction.STATUS_VOIDED)


def unmatched_transaction_candidates(statement_line):
    """Unmatched cash-book rows of the same account, closest first: same
    direction and amount before anything else, then by date distance."""
    line = statement_line
    rows = list(_open_transactions(line.statement).filter(
        transaction_date__gte=line.statement.period_start - timedelta(days=31),
        transaction_date__lte=line.statement.period_end + timedelta(days=31),
    ))
    rows.sort(key=lambda tx: (
        not (tx.direction == line.direction and tx.amount == line.amount),
        tx.direction != line.direction,
        abs((tx.transaction_date - line.line_date).days),
    ))
    return rows[:25]


def suggest_matches(statement):
    """{line_id: transaction} for unmatched lines with exactly one sensible
    partner: same direction, same amount, within SUGGEST_DAYS days. Closest
    date wins; a transaction is suggested for one line only."""
    lines = list(statement.lines.filter(match__isnull=True).order_by('line_date', 'pk'))
    if not lines:
        return {}
    pool = list(_open_transactions(statement).filter(
        transaction_date__gte=statement.period_start - timedelta(days=SUGGEST_DAYS),
        transaction_date__lte=statement.period_end + timedelta(days=SUGGEST_DAYS),
    ))
    pairs = []
    for line in lines:
        for tx in pool:
            gap = abs((tx.transaction_date - line.line_date).days)
            if tx.direction == line.direction and tx.amount == line.amount and gap <= SUGGEST_DAYS:
                pairs.append((gap, line.pk, tx.pk, line, tx))
    pairs.sort(key=lambda p: p[:3])
    out, used = {}, set()
    for _gap, line_id, tx_id, _line, tx in pairs:
        if line_id in out or tx_id in used:
            continue
        out[line_id] = tx
        used.add(tx_id)
    return out


class MatchMismatchError(FinanceError):
    """Line(s) and transaction(s) disagree on the amount — surfaced, not silently forced."""


def _signed(direction, amount):
    return amount if direction == 'in' else -amount


@transaction.atomic
def match_group(statement_lines, bank_transactions, *, force=False, created_by=None):
    """Link statement lines to cash-book rows of the same account as one match.
    Their signed totals must agree (money in minus money out) unless
    `force=True` (a human looked and decided to match anyway). Never invents
    or adjusts either side's numbers."""
    lines = list(statement_lines)
    txs = list(bank_transactions)
    if not lines or not txs:
        raise FinanceError('Pilih minimal satu baris statement dan satu transaksi.')
    account_id = lines[0].statement.account_id
    if any(l.statement.account_id != account_id for l in lines):
        raise FinanceError('Baris statement harus dari rekening yang sama.')
    if any(l.match_id for l in lines):
        raise FinanceError('Baris statement itu sudah dicocokkan.')
    for tx in txs:
        if tx.account_id != account_id:
            raise FinanceError('Transaksi itu bukan dari rekening statement ini.')
        if tx.status == BankTransaction.STATUS_VOIDED:
            raise FinanceError('Transaksi itu sudah dibatalkan.')
        if tx.match_id:
            raise FinanceError('Transaksi itu sudah dicocokkan dengan baris lain.')
    bank = sum(_signed(l.direction, l.amount) for l in lines)
    book = sum(_signed(tx.direction, tx.amount or 0) for tx in txs)
    if not force and bank != book:
        cur = lines[0].statement.currency
        raise MatchMismatchError(
            f'Baris statement ({bank:+,} {cur}) tidak cocok dengan transaksi ({book:+,} {cur})'
            if len(lines) + len(txs) > 2 else
            f"Baris statement ({lines[0].direction} {lines[0].amount:,} {cur}) "
            f"tidak cocok dengan transaksi ({txs[0].direction} {(txs[0].amount or 0):,} {txs[0].currency})"
        )
    match = BankMatch.objects.create(account_id=account_id, created_by=created_by)
    BankStatementLine.objects.filter(pk__in=[l.pk for l in lines]).update(match=match)
    BankTransaction.objects.filter(pk__in=[tx.pk for tx in txs]).update(
        match=match, status=BankTransaction.STATUS_RECONCILED,
    )
    for obj in (*lines, *txs):
        obj.match = match
    for tx in txs:
        tx.status = BankTransaction.STATUS_RECONCILED
    return match


def match_line(statement_line, bank_transaction, *, force=False, created_by=None):
    """One line against one cash-book row."""
    if bank_transaction.direction != statement_line.direction and not force:
        cur = statement_line.statement.currency
        raise MatchMismatchError(
            f"Baris statement ({statement_line.direction} {statement_line.amount:,} {cur}) "
            f"tidak cocok dengan transaksi ({bank_transaction.direction} {(bank_transaction.amount or 0):,} {bank_transaction.currency})"
        )
    match_group([statement_line], [bank_transaction], force=force, created_by=created_by)
    return statement_line


@transaction.atomic
def match_suggested(statement):
    """Apply every current suggestion — one explicit click by a human."""
    done = 0
    for line_id, tx in suggest_matches(statement).items():
        match_line(statement.lines.get(pk=line_id), tx)
        done += 1
    return done


@transaction.atomic
def unmatch_line(statement_line):
    """Undo the match the line belongs to, with every line and row in it."""
    match = statement_line.match
    if match is None:
        return
    BankTransaction.objects.filter(match=match).exclude(status=BankTransaction.STATUS_VOIDED).update(
        match=None, status=BankTransaction.STATUS_POSTED,
    )
    BankTransaction.objects.filter(match=match).update(match=None)
    BankStatementLine.objects.filter(match=match).update(match=None)
    match.delete()
    statement_line.match = None


def book_balance(account, through_date):
    """The account's cash-book balance (its own currency) on `through_date`:
    signed live BankTransaction amounts dated on or before it. By movement
    date, not by when it was recorded — that is what a statement period means."""
    total = 0
    for direction, amount in BankTransaction.objects.filter(
        transaction_date__lte=through_date, amount__isnull=False, account=account,
    ).exclude(status=BankTransaction.STATUS_VOIDED).values_list('direction', 'amount'):
        total += amount if direction == BankTransaction.DIRECTION_IN else -amount
    return total


def statement_summary(statement):
    """Book balance vs the statement's closing balance, the statement's own
    arithmetic (opening + lines = closing?), and match progress."""
    lines = list(statement.lines.all())
    net = sum(l.amount if l.direction == 'in' else -l.amount for l in lines)
    book = book_balance(statement.account, statement.period_end)
    return {
        'currency': statement.currency,
        'book_balance': book,
        'statement_closing': statement.closing_balance,
        'difference': statement.closing_balance - book,
        # Non-zero = lines are missing from the statement or a balance was mistyped.
        'statement_gap': statement.opening_balance + net - statement.closing_balance,
        'lines_total': len(lines),
        'lines_matched': sum(1 for l in lines if l.match_id),
        'is_fully_matched': all(l.match_id for l in lines),
    }
