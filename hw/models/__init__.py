from .activity import ActivityLog, log_activity
from .bank import BankAccount, CashAccount, MoneyAccount, StaffAccount
from .bank_transaction import BankTransaction
from .branch import Branch
from .choices import Company, HotelCity, InvoiceType
from .client import Client
from .client_money import ClientRefund, ClientTransfer
from .confirmation import ConfirmationLetter, ReservationStatus, Room
from .credit_note import CreditNote, CreditNoteLine

# ── Schema v2 foundation ───────────────────────────────────────
from .currency import Currency
from .currency_exchange import CurrencyExchange
from .expense import (
    Expense,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseClaimItem,
    ExpenseLine,
    ExpensePayment,
    ExpenseReceipt,
)
from .hotel import HARAM_LAT, HARAM_LNG, NABAWI_LAT, NABAWI_LNG, Hotel, Occupancy, RoomType, RoomView, room_type_name
from .invoice import (
    Attachment,
    Invoice,
    InvoiceLine,
    InvoiceRevision,
    Reservation,
    _attachment_path,
)
from .journal import AccountType, JournalEntry, JournalLine, LedgerAccount
from .landing import Pricelist, TeamMember
from .meal_plan import MealPlan
from .payment import PaymentAllocation, PaymentLog, PaymentRecord
from .penalty import CancellationPenalty

# ── Finance Redesign (new models) ──────────────────────────────
from .period import FinancialPeriod, Season
from .receipt import Receipt
from .reconciliation import BankStatement, BankStatementLine
from .remittance import Remittance, RemittanceLine
from .role import RoleDefinition
from .sequence import DocumentSequence
from .settlement import RemittanceSettlement
from .user import Language, Role, UserBranchAccess, UserProfile
from .vendor import Vendor

__all__ = [
    # Choices
    'Company', 'HotelCity', 'InvoiceType',
    # Branch
    'Branch',
    # User
    'UserProfile', 'UserBranchAccess', 'Role', 'Language', 'RoleDefinition',
    # Activity
    'ActivityLog', 'log_activity',
    # Core
    'Client',
    'ConfirmationLetter', 'ReservationStatus', 'Room',
    # Invoice
    'Invoice', 'InvoiceLine', 'InvoiceRevision', 'Reservation', 'Attachment', '_attachment_path',
    # Remittance
    'Remittance', 'RemittanceLine',
    # Bank / Cash accounts (Master Architecture v2.0 FASE B)
    'MoneyAccount', 'BankAccount', 'CashAccount', 'StaffAccount', 'BankTransaction', 'CurrencyExchange', 'BankStatement', 'BankStatementLine',
    # Expense (Master Architecture v2.0 FASE D)
    'Expense', 'ExpenseCategory', 'ExpenseLine', 'ExpensePayment', 'ExpenseReceipt',
    # Settlement (Master Architecture v2.0 FASE E)
    'RemittanceSettlement',
    # Hotel
    'Hotel', 'RoomType', 'Occupancy', 'RoomView', 'room_type_name', 'HARAM_LAT', 'HARAM_LNG', 'NABAWI_LAT', 'NABAWI_LNG',
    'MealPlan',
    # Penalty
    'CancellationPenalty',
    # Reminder
    # Landing
    'Pricelist', 'TeamMember',
    # Receipt
    'Receipt',
    # ── Finance Redesign ──
    'FinancialPeriod', 'Season',
    'PaymentRecord', 'PaymentLog', 'PaymentAllocation',
    'AccountType', 'LedgerAccount', 'JournalEntry', 'JournalLine',
    # ── Schema v2 foundation ──
    'Currency', 'DocumentSequence', 'Vendor', 'ClientRefund', 'ClientTransfer',
]
