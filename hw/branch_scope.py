"""Branch scope: whose records a user may see and act on.

A role says what a user may do (permissions.can); the branch scope says on
which branches' records. A profile either covers every branch (head office,
and always the admin role) or only the branches listed in UserBranchAccess (a
branch's own staff). A record outside the scope does not exist for the user:
lists leave it out and opening it answers 404.

Some work is head office's alone (HEAD_OFFICE, applied inside can()): the
whole organisation's data — the ledger, accounting periods and seasons, the
landing page, the shared hotel catalogue — and head office's own tasks:
issuing and changing CLs, setting cancellation penalties, the calendar's
arrival estimates and reminder settings. A branch's staff read their branch's
CLs and penalties but do not change them.
"""
from django.db.models import Q
from django.http import Http404

from .models.role import ADMIN_SLUG

EVERY_ACTION = '*'

_CHANGES = frozenset({'create', 'edit', 'delete'})

# module -> actions reserved for users covering every branch (head office).
HEAD_OFFICE = {
    'journal': EVERY_ACTION,
    'periods': EVERY_ACTION,
    'landing': EVERY_ACTION,
    'users': EVERY_ACTION,
    'dev': EVERY_ACTION,
    # Every branch reads the catalogue; changing it changes it for all.
    'hotels': _CHANGES,
    # Head office issues CLs and sets penalties (business rules 2026-09-29,
    # confirmed 2026-10-09: a branch only reads its own).
    'cl': _CHANGES,
    'penalty': _CHANGES,
    'calendar': frozenset({'edit'}),
    # Setting up bank and cash accounts (confirmed 2026-10-09); a branch reads
    # its own accounts' balances and movements.
    'statements': _CHANGES,
}

# Model name -> lookup path from the model to the branch that owns its records.
BRANCH_FIELD = {
    'Branch': 'code',
    'Client': 'owner_branch',
    # A CL (and its penalty) belongs to its client's branch.
    'ConfirmationLetter': 'client__owner_branch',
    'CancellationPenalty': 'cl__client__owner_branch',
    # An invoice (hotel or services) belongs to the branch that issued it.
    'Invoice': 'branch',
    'InvoiceLine': 'invoice__branch',
    # An attachment hangs on an invoice or on a CL: either path may own it.
    'Attachment': ('invoice__branch', 'cl__client__owner_branch'),
    'Expense': 'branch',
    'ExpensePayment': 'expense__branch',
    # Money: the account it moved through, and for a client's money the
    # client's branch too — a branch works on its clients' payments even when
    # head office received them (confirmed 2026-10-09).
    'MoneyAccount': 'branch',
    'BankAccount': 'branch',
    'CashAccount': 'branch',
    'BankTransaction': 'account__branch',
    'BankStatement': 'account__branch',
    'BankStatementLine': 'statement__account__branch',
    'PaymentRecord': ('receiving_account__branch', 'client__owner_branch'),
    'CurrencyExchange': 'from_account__branch',
    'Remittance': 'from_account__branch',
    'RemittanceSettlement': 'remittance__from_account__branch',
    'ClientRefund': 'client__owner_branch',
    'ClientTransfer': ('from_client__owner_branch', 'to_client__owner_branch'),
    'CreditNote': 'invoice__branch',
    'Receipt': ('invoice__branch', 'client__owner_branch'),
}


def is_head_office_only(module, action):
    actions = HEAD_OFFICE.get(module)
    return actions is not None and (actions == EVERY_ACTION or action in actions)


def branch_codes(user):
    """Branch codes `user` covers, or None for every branch.

    Superusers and the admin role cover every branch whatever their profile
    says, so a misconfigured profile can never lock the administrator out."""
    if user is None or not user.is_authenticated:
        return frozenset()
    cached = getattr(user, '_branch_codes', False)
    if cached is not False:
        return cached
    profile = getattr(user, 'profile', None)
    if user.is_superuser or profile is None or profile.role == ADMIN_SLUG or profile.all_branches:
        codes = None
    else:
        codes = frozenset(profile.branch_access.values_list('branch_id', flat=True))
    user._branch_codes = codes  # once per request: can() asks for every module
    return codes


def covers_all(user):
    return branch_codes(user) is None


def in_scope(user, branch_code):
    codes = branch_codes(user)
    return codes is None or branch_code in codes


def scope(queryset, user, field=None):
    """`queryset` narrowed to the user's branches. `field` is the lookup path
    from the model to its branch (or a tuple of alternative paths); by default
    BRANCH_FIELD's."""
    codes = branch_codes(user)
    if codes is None:
        return queryset
    field = field or BRANCH_FIELD[queryset.model.__name__]
    paths = field if isinstance(field, tuple) else (field,)
    match = Q()
    for path in paths:
        match |= Q(**{f'{path}__in': codes})
    return queryset.filter(match)


def get_in_scope_or_404(queryset, user, field=None, **lookup):
    """One record of the user's branches; anything else is a 404."""
    try:
        return scope(queryset, user, field).get(**lookup)
    except queryset.model.DoesNotExist:
        raise Http404


def with_head_office(user):
    """Branch codes whose accounts the user may move a client's money through:
    their own and head office's (a client of theirs paying or refunded at head
    office, confirmed 2026-10-09). None = every branch."""
    from .models.branch import Branch
    codes = branch_codes(user)
    if codes is None:
        return None
    return frozenset(codes) | frozenset(Branch.objects.filter(is_hq=True).values_list('code', flat=True))


def head_office_only(view):
    """Guard a view (under its require_perm) for head office's own steps that
    share a permission with branch work — e.g. recording what head office
    received of a remittance, which a branch never does. Others get a 404."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not covers_all(request.user):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper


def operating_branches(user):
    """Active branches other than head office that the user covers — where a
    branch's own business (its expenses) is recorded."""
    from .models.branch import Branch
    return scope(Branch.objects.filter(is_active=True, is_hq=False), user)
