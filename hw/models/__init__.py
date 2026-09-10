from .choices import Company, HotelCity, InvoiceType
from .user import CompanyAccess, Language, Role, UserProfile
from .role import RoleDefinition
from .activity import ActivityLog, log_activity
from .client import Client
from .confirmation import ConfirmationLetter, Room
from .invoice import (
    Invoice, Reservation, ServiceItem, Payment,
    Attachment, _attachment_path,
)
from .remittance import Remittance, RemittanceLine
from .ledger import CashAccount, ChargeReason, AllocationReason, Charge, Allocation, CashMovement
from .hotel import Hotel, HARAM_LAT, HARAM_LNG, NABAWI_LAT, NABAWI_LNG
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
    # User
    'UserProfile', 'Role', 'CompanyAccess', 'Language', 'RoleDefinition',
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
    'CashAccount', 'ChargeReason', 'AllocationReason', 'Charge', 'Allocation', 'CashMovement',
    # Hotel
    'Hotel', 'HARAM_LAT', 'HARAM_LNG', 'NABAWI_LAT', 'NABAWI_LNG',
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
