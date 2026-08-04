"""Role-based access control for HMS.

Two independent axes guard every request:

1. **What** a user may do — a role maps to a matrix of module x action
   permissions. Roles are rows in ``hw.models.role.RoleDefinition`` and are
   edited from /roles/; ``DEFAULT_ROLE_MATRIX`` below only seeds that table and
   serves as the fallback if it cannot be read. Read the live matrix through
   ``role_matrix()``, never the constant.
2. **Whose data** a user may see — ``UserProfile.company_access`` limits which
   companies the session may switch to. Company *scoping* of querysets still
   happens through ``get_active_company()``; this layer only decides which
   values that helper is allowed to return.

Django superusers bypass the role matrix entirely and may use every company —
they are the break-glass account and must never be lockable out of user
management. For the same reason the ``admin`` role is force-granted every
permission regardless of what the database says.

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
from django.http import Http404, JsonResponse
from django.shortcuts import redirect

from .models.choices import Company
from .models.role import ADMIN_SLUG, MATRIX_CACHE_KEY, RoleDefinition
from .models.user import CompanyAccess, Role

# Every guarded area of the app. Keep in sync with SIDEBAR_NAV keys in
# frontend/layouts/AppLayout.jsx so nav gating and view gating agree.
MODULES = (
    'cl', 'invoice', 'services', 'hotels', 'clients',
    'remittance', 'calendar', 'penalty', 'users', 'dev',
)

ACTIONS = ('view', 'create', 'edit', 'delete', 'export')

_ALL = set(ACTIONS)
_READ = {'view', 'export'}
_NO_DELETE = {'view', 'create', 'edit', 'export'}

# role -> module -> allowed actions. A module missing from a role's dict means
# no access at all (not even 'view').
#
# This is the *seed*, not the live matrix. Migration 0037 copies it into
# RoleDefinition rows; after that, edits happen in the UI. It stays here as the
# fallback for a database that has no roles yet (fresh install mid-migration).
DEFAULT_ROLE_MATRIX = {
    Role.ADMIN.value: {m: set(_ALL) for m in MODULES},

    # Runs the business: full CRUD on operational data, but cannot manage
    # accounts or reach the dev-only style guide.
    Role.MANAGER.value: {
        m: set(_ALL) for m in MODULES if m not in ('users', 'dev')
    },

    # Day-to-day operators: create and edit their work, never delete it, and
    # remittance (money movement) stays read-only.
    Role.STAFF.value: {
        'cl':       set(_NO_DELETE),
        'invoice':  set(_NO_DELETE),
        'services': set(_NO_DELETE),
        'hotels':   set(_NO_DELETE),
        'clients':  set(_NO_DELETE),
        'calendar': set(_NO_DELETE),
        'penalty':  set(_NO_DELETE),
        'remittance': set(_READ),
    },

    # Read-only account: reporting, exports, PDF — nothing that mutates.
    Role.VIEWER.value: {
        'cl':         set(_READ),
        'invoice':    set(_READ),
        'services':   set(_READ),
        'hotels':     set(_READ),
        'clients':    set(_READ),
        'calendar':   set(_READ),
        'penalty':    set(_READ),
        'remittance': set(_READ),
    },
}


# Presentation metadata for the seeded roles. Only used by migration 0037 and by
# a fallback matrix; once the rows exist these live in the database too.
DEFAULT_ROLE_META = {
    Role.ADMIN.value: {
        'label': 'Administrator',
        'description': 'Full access, including user and role management.',
        'grants_django_staff': True,
        'order': 10,
    },
    Role.MANAGER.value: {
        'label': 'Manager',
        'description': 'Full access to all operational modules; cannot manage users.',
        'grants_django_staff': True,
        'order': 20,
    },
    Role.STAFF.value: {
        'label': 'Staff',
        'description': 'Create and edit operational records; no deleting, remittance read-only.',
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
    """Keep only modules and actions this build actually guards.

    A role row can outlive the module it referenced (a feature gets removed, a
    slug gets renamed). Dropping unknown keys on read means a stale row grants
    nothing rather than silently carrying dead permissions forward.
    """
    clean = {}
    for module, actions in (permissions or {}).items():
        if module not in MODULES:
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
    """True when ``user`` may perform ``action`` on ``module``."""
    role = get_role(user)
    if role is None:
        return False
    return action in role_matrix().get(role, {}).get(module, ())


def perms_payload(user):
    """Serialise the user's matrix for Inertia props: {module: [actions]}."""
    role = get_role(user)
    matrix = role_matrix().get(role, {})
    return {
        module: sorted(actions)
        for module, actions in matrix.items()
        if actions
    }


def allowed_companies(user):
    """Companies this user may switch the workspace to."""
    everything = [Company.KONOZ.value, Company.IJABAH.value]
    if not user or not user.is_authenticated:
        return everything
    if user.is_superuser:
        return everything
    profile = getattr(user, 'profile', None)
    access = getattr(profile, 'company_access', None) or CompanyAccess.ALL.value
    if access == CompanyAccess.ALL.value:
        return everything
    return [access]


def default_company(user):
    """The company a session falls back to when none is set or the stored one
    is no longer permitted."""
    return allowed_companies(user)[0]


def can_use_company(user, company):
    return company in allowed_companies(user)


def _deny(request, message="Access denied."):
    """Refuse a request in the shape its caller expects.

    XHR/JSON callers get a 403 payload; Inertia and plain navigations get a
    flash message and a bounce to home, which the Inertia client follows.
    """
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
        return wrapper
    return decorator


def require_role(*roles):
    """Guard a view by role, for areas with no natural module/action pair."""
    allowed = {r.value if hasattr(r, 'value') else r for r in roles}

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if get_role(request.user) not in allowed:
                return _deny(request)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def hide_unless(module, action):
    """Like ``require_perm`` but answers 404 instead of redirecting.

    Used for endpoints whose existence should not be advertised (health check,
    dev style guide).
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not can(request.user, module, action):
                raise Http404
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
