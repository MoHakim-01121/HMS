"""Role-based access control for HMS.

A role maps to a matrix of module x action permissions. Roles are rows in
``hw.models.role.RoleDefinition`` and are edited from /roles/;
``DEFAULT_ROLE_MATRIX`` below only seeds that table and serves as the
fallback if it cannot be read. Read the live matrix through ``role_matrix()``,
never the constant.

Django superusers bypass the role matrix entirely — they are the break-glass
account and must never be lockable out of user management. For the same
reason the ``admin`` role is force-granted every permission regardless of
what the database says.

Backend views declare their requirement with ``@require_perm(module, action)``;
the same matrix is serialised into Inertia props by ``perms_payload()`` so the
React shell can hide what the backend would refuse anyway. The frontend copy is
a convenience, never the enforcement point.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect

from .branch_scope import head_office_allows
from .models.role import ADMIN_SLUG, MATRIX_CACHE_KEY, RoleDefinition
from .models.user import Role

# Every guarded area of the app. Keep in sync with SIDEBAR_NAV keys in
# frontend/layouts/AppLayout.jsx so nav gating and view gating agree.
MODULES = (
    'cl', 'invoice', 'hotels', 'clients',
    'remittance', 'calendar', 'penalty', 'users', 'dev',
    'landing',
    # Finance areas, each its own module so money operations can be granted
    # independently (least privilege / segregation of duties).
    'payments', 'journal', 'statements', 'periods', 'expenses',
    # Bank and cash accounts, transfers and exchanges between them, and
    # reconciliation: the bank side, apart from recording client payments.
    'bank',
)

# 'approve' is the second person's decision on money: confirming a payment,
# approving a refund or deposit transfer, voiding an invoice or issuing a
# credit note. Kept apart from 'delete' so the power to decide can be granted
# on its own.
ACTIONS = ('view', 'create', 'edit', 'delete', 'export', 'approve')

# Modules only the admin role ever holds, whatever a role row says. Account and
# role management decide who may do everything else: handing any part of it to
# another role lets that role make itself admin (create an admin account, reset
# an admin's password, widen its own permissions through a second role).
ADMIN_ONLY_MODULES = ('users',)

# Modules a role row may grant — what the role editor offers.
GRANTABLE_MODULES = tuple(m for m in MODULES if m not in ADMIN_ONLY_MODULES)

_ALL = set(ACTIONS)
_CRUD = {'view', 'create', 'edit', 'delete', 'export'}
_READ = {'view', 'export'}
_NO_DELETE = {'view', 'create', 'edit', 'export'}

# The operational modules (bookings, billing, clients, catalogue) and the money
# modules. Only Admin and Finance work on money; Manager reads it (decided
# 2026-10-09); Staff records client payments only (decided 2026-10-20).
OPERATIONAL_MODULES = ('cl', 'invoice', 'hotels', 'clients', 'calendar', 'penalty')
MONEY_MODULES = ('payments', 'bank', 'expenses', 'remittance')

# role -> module -> allowed actions. A module missing from a role's dict means
# no access at all (not even 'view').
#
# This is the *seed*, not the live matrix. Migrations 0037 and 0143 copy it
# into RoleDefinition rows; after that, edits happen in the UI (/roles/), where
# any role can be widened or narrowed. It stays here as the fallback for a
# database that has no roles yet (fresh install mid-migration).
DEFAULT_ROLE_MATRIX = {
    Role.ADMIN.value: {m: set(_ALL) for m in MODULES},

    # Works on money: records and approves payments, refunds, transfers,
    # expenses and remittances, reconciles accounts, closes periods (head
    # office only). Reads the operational side to do so.
    Role.FINANCE.value: {
        **{m: set(_ALL) for m in MONEY_MODULES},
        'statements': set(_READ),
        'journal':    set(_READ),
        'periods':    set(_NO_DELETE),
        **{m: set(_READ) for m in OPERATIONAL_MODULES},
    },

    # Runs the operation: full CRUD on bookings, billing, clients and the
    # catalogue; reads money and the books, never moves money. Approves (or
    # rejects) branch expenses before Finance pays them (decided 2026-10-11).
    Role.MANAGER.value: {
        **{m: set(_CRUD) for m in OPERATIONAL_MODULES + ('landing',)},
        **{m: set(_READ) for m in MONEY_MODULES + ('statements', 'journal', 'periods')},
        'expenses': set(_READ) | {'approve'},
    },

    # Day-to-day operators: create and edit their work, never delete it. Of
    # money they only record client payments, which Admin or Finance confirm;
    # the bank, remittances, expenses and the books are not theirs (decided
    # 2026-10-20).
    Role.STAFF.value: {
        **{m: set(_NO_DELETE) for m in OPERATIONAL_MODULES + ('landing',)},
        'payments': {'view', 'create', 'export'},
    },

    # Read-only account: reporting, exports, PDF — nothing that mutates.
    Role.VIEWER.value: {
        m: set(_READ)
        for m in OPERATIONAL_MODULES + ('landing',) + MONEY_MODULES + ('statements', 'journal', 'periods')
    },
}


# Presentation metadata for the seeded roles. Only used by the seeding
# migrations and by a fallback matrix; once the rows exist these live in the
# database too.
DEFAULT_ROLE_META = {
    Role.ADMIN.value: {
        'label': 'Administrator',
        'description': 'Full access, including user and role management.',
        'grants_django_staff': True,
        'order': 10,
    },
    Role.FINANCE.value: {
        'label': 'Finance',
        'description': 'Records and approves money: payments, refunds, transfers, expenses, remittances, reconciliation. Reads the rest.',
        'grants_django_staff': False,
        'order': 15,
    },
    Role.MANAGER.value: {
        'label': 'Manager',
        'description': 'Full access to bookings, billing and clients; reads money and the books.',
        'grants_django_staff': False,
        'order': 20,
    },
    Role.STAFF.value: {
        'label': 'Staff',
        'description': 'Create and edit operational records; no deleting; records client payments for Finance to confirm.',
        'grants_django_staff': False,
        'order': 30,
    },
    Role.VIEWER.value: {
        'label': 'Viewer',
        'description': 'Read-only across every module, including exports and PDFs.',
        'grants_django_staff': False,
        'order': 40,
    },
}

# ---------------------------------------------------------------------------
# Live matrix
# ---------------------------------------------------------------------------

def _sanitise(permissions):
    """Keep only modules and actions this build actually guards, minus the
    admin-only modules.

    A role row can outlive the module it referenced (a feature gets removed, a
    slug gets renamed). Dropping unknown keys on read means a stale row grants
    nothing rather than silently carrying dead permissions forward. The admin
    role gets the admin-only modules back in role_matrix().
    """
    clean = {}
    for module, actions in (permissions or {}).items():
        if module not in GRANTABLE_MODULES:
            continue
        kept = {a for a in actions if a in ACTIONS}
        if kept:
            clean[module] = kept
    return clean


def _fallback_matrix():
    return {role: {m: set(a) for m, a in mods.items()}
            for role, mods in DEFAULT_ROLE_MATRIX.items()}


def role_matrix():
    """The live role -> module -> actions matrix.

    Cached because ``can()`` runs several times per request and the table is
    tiny; every write to RoleDefinition drops the key, so a permission change
    takes effect on the next request across every worker (the cache backend is
    the shared database table).
    """
    cached = cache.get(MATRIX_CACHE_KEY)
    if cached is None:
        try:
            cached = RoleDefinition.objects.all().as_matrix()
        except DatabaseError:
            # Table not migrated yet (fresh checkout, or mid-deploy). Fall back
            # rather than 500 — losing editability beats losing the app.
            return _fallback_matrix()
        if not cached:
            return _fallback_matrix()
        cache.set(MATRIX_CACHE_KEY, cached, 300)

    matrix = {role: _sanitise(mods) for role, mods in cached.items()}
    # Break-glass: whatever the row says, an administrator has everything. The
    # screen that could undo a bad edit is itself permission-gated.
    matrix[ADMIN_SLUG] = {m: set(ACTIONS) for m in MODULES}
    return matrix


def role_definitions():
    """Role rows for pickers and admin screens, ordered. Falls back to the seed."""
    try:
        rows = list(RoleDefinition.objects.all())
    except DatabaseError:
        rows = []
    if rows:
        return rows
    return []


def role_choices():
    """[{value, label, description}] for every selectable role."""
    rows = role_definitions()
    if rows:
        return [{'value': r.slug, 'label': r.label, 'description': r.description}
                for r in rows]
    return [{'value': v, 'label': DEFAULT_ROLE_META[v]['label'],
             'description': DEFAULT_ROLE_META[v]['description']}
            for v in DEFAULT_ROLE_MATRIX]


def role_labels():
    """{slug: label} for every known role."""
    return {c['value']: c['label'] for c in role_choices()}


def is_valid_role(slug):
    return slug in role_matrix()


def get_role(user):
    """Effective role string for a user. Superusers are always administrators."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMIN_SLUG
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', None) or Role.STAFF.value


def role_label(user):
    role = get_role(user)
    if not role:
        return 'Standard User'
    return role_labels().get(role) or dict(Role.choices).get(role) or 'Standard User'


def can(user, module, action):
    """True when ``user`` may perform ``action`` on ``module``: the role grants
    it, and for head office's own work the user covers every branch
    (branch_scope.HEAD_OFFICE)."""
    role = get_role(user)
    if role is None:
        return False
    if action not in role_matrix().get(role, {}).get(module, ()):
        return False
    return head_office_allows(user, module, action)


def perms_payload(user):
    """Serialise what ``user`` may do for Inertia props: {module: [actions]},
    the same answer can() gives."""
    role = get_role(user)
    matrix = role_matrix().get(role, {})
    payload = {
        module: sorted(a for a in actions if head_office_allows(user, module, a))
        for module, actions in matrix.items()
    }
    return {module: actions for module, actions in payload.items() if actions}


def _deny(request, message=None):
    """Refuse a request in the shape its caller expects.

    XHR/JSON callers get a 403 payload; Inertia and plain navigations get a
    flash message and a bounce to home, which the Inertia client follows.
    """
    if message is None:
        from .i18n import tr
        message = tr(request, "You don't have access to that page. Ask an Administrator if you need it.",
                     'Anda tidak punya akses ke halaman itu. Minta ke Administrator kalau perlu.')
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    if wants_json and not request.headers.get('X-Inertia'):
        return JsonResponse({'error': message}, status=403)
    messages.error(request, message)
    return redirect('home')


def require_perm(module, action):
    """Guard a view with a module/action permission.

    Wraps ``login_required`` so an unauthenticated hit still redirects to the
    login page rather than reporting a permission problem.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not can(request.user, module, action):
                return _deny(request)
            return view_func(request, *args, **kwargs)
        wrapper.access_guard = ('perm', module, action)
        return wrapper
    return decorator
