from .choices import Company, HotelCity, InvoiceType
from .user import CompanyAccess, Language, Role, UserProfile
from .role import RoleDefinition
from .activity import ActivityLog, log_activity
from .client import Client
from .confirmation import ConfirmationLetter, Room
from .invoice import (
    Invoice, Reservation, ServiceItem, Payment,
    Attachment, _attachment_path,
    Remittance, RemittanceLine,
)
from .ledger import Account, ChargeReason, AllocationReason, Charge, Allocation, CashMovement
from .hotel import Hotel, HARAM_LAT, HARAM_LNG, NABAWI_LAT, NABAWI_LNG
from .penalty import CancellationPenalty
from .reminder import ReminderLog, RecapLog, WATarget, MessageTemplate
from .billing import BillingLog
from .visit import Visit, VisitPhoto
from .landing import Pricelist, TeamMember

# ── Finance Redesign (new models) ──────────────────────────────
from .period import FinancialPeriod
from .payment import PaymentRecord, PaymentLog
from .journal import AccountType, Account as LedgerAccount, JournalEntry, JournalLine

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
    'Remittance', 'RemittanceLine',
    # Ledger (legacy — kept for backward compat during migration)
    'Account', 'ChargeReason', 'AllocationReason', 'Charge', 'Allocation', 'CashMovement',
    # Hotel
    'Hotel', 'HARAM_LAT', 'HARAM_LNG', 'NABAWI_LAT', 'NABAWI_LNG',
    # Penalty
    'CancellationPenalty',
    # Reminder
    'ReminderLog', 'RecapLog', 'WATarget', 'MessageTemplate',
    # Billing
    'BillingLog',
    # Visit
    'Visit', 'VisitPhoto',
    # Landing
    'Pricelist', 'TeamMember',
    # ── Finance Redesign ──
    'FinancialPeriod',
    'PaymentRecord', 'PaymentLog',
    'AccountType', 'LedgerAccount', 'JournalEntry', 'JournalLine',
]
