"""BankTransaction recording — the write side of hw/models/bank_transaction.py.

One call site per event that moves cash through a concrete BankAccount/
CashAccount. Idempotent per (source_type, source_id): safe to call again for
an already-recorded event (e.g. a retried request) without doubling it.
"""
from ..models.bank import BankAccount
from ..models.bank_transaction import BankTransaction


def record_bank_transaction(*, account, direction, amount_sar, source_type, source_id,
                            transaction_date, currency='SAR', reference=''):
    """Log a cash movement against a concrete account. No-op if `account` is
    None (legacy/unlinked event with no resolvable BankAccount/CashAccount —
    the movement is still correct in the journal, just not in this log)."""
    if account is None:
        return None
    kwargs = {'bank_account': account} if isinstance(account, BankAccount) else {'cash_account': account}
    tx, _created = BankTransaction.objects.get_or_create(
        source_type=source_type, source_id=source_id,
        defaults={
            'transaction_date': transaction_date, 'direction': direction,
            'amount_sar': amount_sar, 'currency': currency, 'reference': reference,
            **kwargs,
        },
    )
    return tx
