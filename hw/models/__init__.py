from .choices import Company, HotelCity, InvoiceType
from .branch import Branch
from .user import BranchAccess, Language, Role, UserProfile
from .role import RoleDefinition
from .activity import ActivityLog, log_activity
from .client import Client
from .confirmation import ConfirmationLetter, ReservationStatus, Room
from .invoice import (
    Invoice, Reservation, ServiceItem,
    Attachment, _attachment_path,
)
from .remittance import Remittance, RemittanceLine
from .bank import BankAccount, CashAccount, MoneyAccount
from .bank_transaction import BankTransaction
from .currency_exchange import CurrencyExchange
from .credit_note import CreditNote, CreditNoteLine
from .reconciliation import BankStatement, BankStatementLine
from .expense import Expense, ExpenseCategory, ExpenseLine, ExpensePayment
from .settlement import RemittanceSettlement
from .hotel import Hotel, RoomType, Occupancy, RoomView, room_type_name, HARAM_LAT, HARAM_LNG, NABAWI_LAT, NABAWI_LNG
from .meal_plan import MealPlan
from .penalty import CancellationPenalty
from .reminder import WATarget, MessageTemplate
from .visit import Visit, VisitPhoto
from .landing import Pricelist, TeamMember
from .receipt import Receipt

# ── Finance Redesign (new models) ──────────────────────────────
from .period import FinancialPeriod
from .payment import PaymentRecord, PaymentLog, PaymentAllocation
from .journal import AccountType, LedgerAccount, JournalEntry, JournalLine

# ── Schema v2 foundation ───────────────────────────────────────
from .currency import Currency
from .sequence import DocumentSequence
from .vendor import Vendor

__all__ = [
    # Choices
    'Company', 'HotelCity', 'InvoiceType',
    # Branch
    'Branch',
    # User
    'UserProfile', 'Role', 'BranchAccess', 'Language', 'RoleDefinition',
    # Activity
    'ActivityLog', 'log_activity',
    # Core
    'Client',
    'ConfirmationLetter', 'ReservationStatus', 'Room',
    # Invoice
    'Invoice', 'Reservation', 'ServiceItem', 'Attachment', '_attachment_path',
    # Remittance
    'Remittance', 'RemittanceLine',
    # Bank / Cash accounts (Master Architecture v2.0 FASE B)
    'MoneyAccount', 'BankAccount', 'CashAccount', 'BankTransaction', 'CurrencyExchange', 'BankStatement', 'BankStatementLine',
    # Expense (Master Architecture v2.0 FASE D)
    'Expense', 'ExpenseCategory', 'ExpenseLine', 'ExpensePayment',
    # Settlement (Master Architecture v2.0 FASE E)
    'RemittanceSettlement',
    # Hotel
    'Hotel', 'RoomType', 'Occupancy', 'RoomView', 'room_type_name', 'HARAM_LAT', 'HARAM_LNG', 'NABAWI_LAT', 'NABAWI_LNG',
    'MealPlan',
    # Penalty
    'CancellationPenalty',
    # Reminder
    'WATarget', 'MessageTemplate',
    # Visit
    'Visit', 'VisitPhoto',
    # Landing
    'Pricelist', 'TeamMember',
    # Receipt
    'Receipt',
    # ── Finance Redesign ──
    'FinancialPeriod',
    'PaymentRecord', 'PaymentLog', 'PaymentAllocation',
    'AccountType', 'LedgerAccount', 'JournalEntry', 'JournalLine',
    # ── Schema v2 foundation ──
    'Currency', 'DocumentSequence', 'Vendor',
]
