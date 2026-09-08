"""Exception classes untuk seluruh lapisan keuangan.

Sumber tenggelam (single source of truth) -- dipakai oleh finance/posting.py,
finance_helpers.py (re-export untuk kompatibilitas), dan view. Pindah dari
finance_helpers.py saat merapikan duplikasi.
"""


class FinanceError(Exception):
    """Base exception for finance operations."""
    pass


class PeriodLockedError(FinanceError):
    """Posting to a locked period."""
    pass


class JournalImbalanceError(FinanceError):
    """Journal entry doesn't balance (debit != credit)."""
    pass


class PaymentAlreadyProcessedError(FinanceError):
    """Payment already confirmed/allocated."""
    pass


class InsufficientAllocationError(FinanceError):
    """Payment amount exceeds invoice remaining."""
    pass
