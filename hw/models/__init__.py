from .choices import Company, HotelCity, InvoiceType
from .branch import Branch
from .user import BranchAccess, CompanyAccess, Language, Role, UserProfile
from .role import RoleDefinition
from .activity import ActivityLog, log_activity
from .client import Client
from .confirmation import ConfirmationLetter, Room
from .invoice import (
    Invoice, Reservation, ServiceItem, Payment,
    Attachment, _attachment_path,
)
from .remittance import Remittance, RemittanceLine
from .ledger import ChargeReason, AllocationReason, Charge, Allocation, CashMovement
from .bank import BankAccount, CashAccount
from .expense import Expense, ExpenseCategory, ExpenseLine, ExpensePayment
from .settlement import HQObligation, RemittanceAllocation, RemittanceSettlement
from .hotel import Hotel, RoomType, Occupancy, RoomView, HARAM_LAT, HARAM_LNG, NABAWI_LAT, NABAWI_LNG
from .meal_plan import MealPlan
from .penalty import CancellationPenalty
from .reminder import WATarget, MessageTemplate
from .visit import Visit, VisitPhoto
from .landing import Pricelist, TeamMember
from .receipt import Receipt

# ── Finance Redesign (new models) ──────────────────────────────
from .period import FinancialPeriod
from .payment import PaymentRecord, PaymentLog, PaymentAllocation
from .journal import AccountType, Account, LedgerAccount, JournalEntry, JournalLine

__all__ = [
    # Choices
    'Company', 'HotelCity', 'InvoiceType',
    # Branch
    'Branch',
    # User
    'UserProfile', 'Role', 'CompanyAccess', 'BranchAccess', 'Language', 'RoleDefinition',
    # Activity
    'ActivityLog', 'log_activity',
    # Core
    'Client',
    'ConfirmationLetter', 'Room',
    # Invoice (legacy — kept for backward compat during migration)
    'Invoice', 'Reservation', 'ServiceItem', 'Payment', 'Attachment', '_attachment_path',
    # Remittance
    'Remittance', 'RemittanceLine',
    # Ledger (legacy — kept for backward compat during migration)
    'ChargeReason', 'AllocationReason', 'Charge', 'Allocation', 'CashMovement',
    # Bank / Cash accounts (Master Architecture v2.0 FASE B)
    'BankAccount', 'CashAccount',
    # Expense (Master Architecture v2.0 FASE D)
    'Expense', 'ExpenseCategory', 'ExpenseLine', 'ExpensePayment',
    # Settlement (Master Architecture v2.0 FASE E)
    'HQObligation', 'RemittanceSettlement', 'RemittanceAllocation',
    # Hotel
    'Hotel', 'RoomType', 'Occupancy', 'RoomView', 'HARAM_LAT', 'HARAM_LNG', 'NABAWI_LAT', 'NABAWI_LNG',
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
    'AccountType', 'Account', 'LedgerAccount', 'JournalEntry', 'JournalLine',
]
