"""BankTransaction recording — the write side of hw/models/bank_transaction.py.

One call site per event that moves cash through a concrete MoneyAccount.
Idempotent per (source_type, source_id): safe to call again for
an already-recorded event (e.g. a retried request) without doubling it.
"""
from django.db import transaction

from ..models.bank import BankAccount, CashAccount
from ..models.bank_transaction import BankTransaction


def ensure_funds(account, amount, on_date, *, exclude_pk=None):
    """Uang keluar `amount` (mata uang rekening) tidak boleh membuat saldo
    buku kas rekening itu minus -- pada `on_date` maupun sesudahnya, karena
    pengeluaran bertanggal mundur ikut mengurangi semua saldo setelahnya.

    Kas dan bank tidak bisa minus: saldo yang tidak cukup berarti ada uang
    masuk yang belum dicatat (penerimaan, penukaran valas, saldo awal), dan
    itu harus dicatat dulu -- bukan ditemukan berbulan-bulan kemudian.
    Rekening dikunci sampai transaksi selesai supaya dua pengeluaran paralel
    tidak sama-sama lolos."""
    from django.db.models import Case, F, Sum, When
    from ..models.bank import MoneyAccount
    from .errors import InsufficientFundsError

    MoneyAccount.objects.select_for_update().filter(pk=account.pk).exists()
    rows = (
        BankTransaction.objects.filter(account_id=account.pk)
        .exclude(status=BankTransaction.STATUS_VOIDED).exclude(pk=exclude_pk)
        .values('transaction_date')
        .annotate(net=Sum(Case(When(direction='in', then=F('amount')), default=-F('amount'))))
        .order_by('transaction_date')
    )
    balance = lowest = None
    running = 0
    for r in rows:
        running += r['net'] or 0
        if r['transaction_date'] <= on_date:
            balance = running
        elif lowest is None or running < lowest:
            lowest = running
    available = min(x for x in (balance or 0, lowest) if x is not None)
    if amount > available:
        raise InsufficientFundsError(
            f"Saldo {account} hanya {max(available, 0):,} {account.currency}"
            f"{'' if lowest is None or lowest >= (balance or 0) else ' (setelah transaksi sesudahnya)'}"
            f" per {on_date:%d/%m/%Y}; transaksi ini mengeluarkan {amount:,} {account.currency}. "
            "Catat dulu uang yang membiayainya (penerimaan, penukaran valas, atau saldo awal)."
        )


def record_bank_transaction(*, account, direction, amount_sar, source_type, source_id,
                            transaction_date, currency='SAR', amount=None, reference='',
                            check_funds=True):
    """Log a cash movement against a concrete account. No-op if `account` is
    None (legacy/unlinked event with no resolvable MoneyAccount —
    the movement is still correct in the journal, just not in this log).

    `amount` is the money that actually moved, in `currency`; a SAR movement
    may omit it (it equals `amount_sar`). A non-SAR movement must pass it —
    the fund-flow report reads rupiah/dollars from here, not the SAR value."""
    if amount is None:
        if currency != 'SAR':
            raise ValueError(f'{source_type} #{source_id}: amount is required for a {currency} movement')
        amount = amount_sar
    if account is None:
        return None
    with transaction.atomic():
        # A repeat call for an already-recorded event moves no new money.
        if check_funds and direction == 'out' and not BankTransaction.objects.filter(
            source_type=source_type, source_id=source_id,
        ).exists():
            ensure_funds(account, amount, _as_date(transaction_date))
        tx, _created = BankTransaction.objects.get_or_create(
            source_type=source_type, source_id=source_id,
            defaults={
                'transaction_date': transaction_date, 'direction': direction,
                'amount_sar': amount_sar, 'currency': currency, 'amount': amount, 'reference': reference,
                'account': account,
            },
        )
    return tx


def sync_bank_transaction(*, account, direction, amount_sar, source_type, source_id,
                          transaction_date, currency='SAR', amount=None, reference=''):
    """Like record_bank_transaction, but an existing row follows the document
    when it changed (an edited transfer). A row already matched to a bank
    statement is not rewritten."""
    from .errors import FinanceError
    tx = BankTransaction.objects.filter(source_type=source_type, source_id=source_id).first()
    if tx is None:
        return record_bank_transaction(
            account=account, direction=direction, amount_sar=amount_sar, source_type=source_type,
            source_id=source_id, transaction_date=transaction_date, currency=currency, amount=amount,
            reference=reference,
        )
    wanted = dict(account=account, direction=direction, amount_sar=amount_sar, currency=currency,
                  amount=amount if amount is not None else amount_sar, transaction_date=transaction_date,
                  reference=reference)
    if all(getattr(tx, k) == v for k, v in wanted.items()):
        return tx
    if tx.status == BankTransaction.STATUS_RECONCILED or tx.statement_lines.exists():
        raise FinanceError('Transaksi ini sudah dicocokkan dengan mutasi bank — batalkan pencocokannya dulu.')
    with transaction.atomic():
        if direction == 'out':
            # The edited row replaces the old one: check the account without it.
            ensure_funds(account, wanted['amount'], _as_date(transaction_date), exclude_pk=tx.pk)
        BankTransaction.objects.filter(pk=tx.pk).update(**wanted)
    return tx


def _as_date(value):
    """Tanggal transaksi kadang masih string ISO dari form."""
    from datetime import date
    return date.fromisoformat(value) if isinstance(value, str) else value


def void_bank_transactions(source_type, source_ids):
    """Void the cash-log rows of reversed/voided source documents so they stop
    counting as money that moved. Refuses rows already matched to a bank
    statement line: that match says the money did move, so it has to be
    unmatched deliberately first rather than silently contradicted."""
    from django.db.models import Q
    from .errors import FinanceError

    if isinstance(source_ids, int):
        source_ids = [source_ids]
    qs = BankTransaction.objects.filter(
        source_type=source_type, source_id__in=list(source_ids),
    ).exclude(status=BankTransaction.STATUS_VOIDED)
    if qs.filter(Q(status=BankTransaction.STATUS_RECONCILED) | Q(statement_lines__isnull=False)).exists():
        raise FinanceError(
            'Transaksi ini sudah dicocokkan dengan mutasi bank di Reconciliation — '
            'batalkan pencocokannya dulu.'
        )
    return qs.update(status=BankTransaction.STATUS_VOIDED)


def opening_source_type(account):
    return 'OpeningBalance'


def sync_opening_balance(account):
    """Mirror account.opening_balance/opening_date as one cash-book row.

    Zero (or no date) voids any existing row. A row already matched to a bank
    statement line is not rewritten — that would contradict the match."""
    from .errors import FinanceError

    source_type = opening_source_type(account)
    tx = BankTransaction.objects.filter(source_type=source_type, source_id=account.pk).first()
    wanted = bool(account.opening_balance) and account.opening_date is not None
    if tx is not None:
        same = (
            wanted and tx.status != BankTransaction.STATUS_VOIDED
            and tx.amount == abs(account.opening_balance) and tx.transaction_date == account.opening_date
            and tx.direction == ('in' if account.opening_balance > 0 else 'out')
        )
        if same:
            return tx
        if tx.status == BankTransaction.STATUS_RECONCILED or tx.statement_lines.exists():
            raise FinanceError('Saldo awal sudah dicocokkan dengan mutasi bank — batalkan pencocokannya dulu.')
        if not wanted:
            BankTransaction.objects.filter(pk=tx.pk).update(status=BankTransaction.STATUS_VOIDED)
            return None
        BankTransaction.objects.filter(pk=tx.pk).update(
            status=BankTransaction.STATUS_POSTED, amount=abs(account.opening_balance),
            direction='in' if account.opening_balance > 0 else 'out',
            transaction_date=account.opening_date, currency=account.currency,
        )
        return tx
    if not wanted:
        return None
    # amount_sar = 0: the SAR ledger already carries its own history; this row
    # only anchors the real-currency cash book.
    return record_bank_transaction(
        account=account, direction='in' if account.opening_balance > 0 else 'out', amount_sar=0,
        currency=account.currency, amount=abs(account.opening_balance),
        source_type=source_type, source_id=account.pk,
        transaction_date=account.opening_date, reference='Opening balance', check_funds=False,
    )


def default_account(branch_id, currency):
    """The account a branch receives `currency` into when the caller did not
    name one: its cash account in that currency, else its first bank account
    in that currency. None when the branch holds no such account — never an
    account in another currency, which would book rupiah into a riyal till."""
    cash = CashAccount.objects.filter(branch_id=branch_id, currency=currency, is_active=True).order_by('id').first()
    if cash:
        return cash
    return BankAccount.objects.filter(branch_id=branch_id, currency=currency, is_active=True).order_by('id').first()


def ensure_hq_receives_sar(branch_id, currency):
    """HQ (Pusat) only ever receives SAR — rupiah and dollars are collected by
    the branches, exchanged there, and reach HQ as SAR through remittances."""
    from .accounts import HQ_BRANCH
    from .errors import FinanceError
    if branch_id == HQ_BRANCH and currency != 'SAR':
        raise FinanceError(f'Pusat hanya menerima SAR — {currency} diterima dan dicatat di cabang.')


def ensure_account_currency(account, currency):
    """Money moves into/out of an account in that account's own currency."""
    from .errors import FinanceError
    if account is not None and account.currency != currency:
        raise FinanceError(
            f'Rekening {account} memakai {account.currency}, bukan {currency} — '
            f'pilih rekening {currency}.'
        )


def ledger_currency_conflict(ledger_code, currency, *, exclude_pk=None):
    """Mata uang lain yang sudah dipakai rekening pada akun buku besar ini
    (None bila tidak ada). Satu akun buku besar satu mata uang (T4)."""
    from ..models.bank import MoneyAccount
    return (
        MoneyAccount.objects.filter(ledger_account_id=ledger_code).exclude(currency=currency)
        .exclude(pk=exclude_pk).values_list('currency', flat=True).first()
    )
