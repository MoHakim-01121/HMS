"""Finance role, the 'approve' action, and money out of Manager and Staff.

Decided 2026-10-09 (access control audit, phase 3): only Admin and Finance
work on money (payments, refunds, transfers, expenses, remittances,
reconciliation, approvals); Manager and Staff read it, and Staff no longer
sees the books (journal, periods, finance reports). 'approve' — confirming a
payment, approving a refund or deposit transfer, voiding an invoice, a credit
note — is now its own action instead of riding on 'delete'. Django admin is
the administrator's alone.

The built-in roles are rewritten to the new seed; any role can still be
widened or narrowed afterwards at /roles/. Seeded from literals (not
hw.permissions) so the migration means the same thing forever.
"""
from django.db import migrations

CACHE_KEY = 'hw:role_matrix:v1'

ALL = ['approve', 'create', 'delete', 'edit', 'export', 'view']
CRUD = ['create', 'delete', 'edit', 'export', 'view']
NO_DELETE = ['create', 'edit', 'export', 'view']
READ = ['export', 'view']

OPERATIONAL = ['cl', 'invoice', 'services', 'hotels', 'clients', 'calendar', 'penalty']
MONEY = ['payments', 'expenses', 'remittance']
BOOKS = ['statements', 'journal', 'periods']
EVERY = OPERATIONAL + ['remittance', 'users', 'dev', 'landing', 'payments', 'journal', 'statements',
                       'periods', 'expenses']

ROLES = [
    {
        'slug': 'admin', 'label': 'Administrator', 'order': 10, 'grants_django_staff': True,
        'description': 'Full access, including user and role management.',
        'permissions': {m: ALL for m in EVERY},
    },
    {
        'slug': 'finance', 'label': 'Finance', 'order': 15, 'grants_django_staff': False,
        'description': 'Records and approves money: payments, refunds, transfers, expenses, '
                       'remittances, reconciliation. Reads the rest.',
        'permissions': {
            **{m: ALL for m in MONEY},
            'statements': READ, 'journal': READ, 'periods': NO_DELETE,
            **{m: READ for m in OPERATIONAL},
        },
    },
    {
        'slug': 'manager', 'label': 'Manager', 'order': 20, 'grants_django_staff': False,
        'description': 'Full access to bookings, billing and clients; reads money and the books.',
        'permissions': {
            **{m: CRUD for m in OPERATIONAL + ['landing']},
            **{m: READ for m in MONEY + BOOKS},
        },
    },
    {
        'slug': 'staff', 'label': 'Staff', 'order': 30, 'grants_django_staff': False,
        'description': 'Create and edit operational records; no deleting; money read-only.',
        'permissions': {
            **{m: NO_DELETE for m in OPERATIONAL + ['landing']},
            **{m: READ for m in MONEY},
        },
    },
    {
        'slug': 'viewer', 'label': 'Viewer', 'order': 40, 'grants_django_staff': False,
        'description': 'Read-only across every module, including exports and PDFs.',
        'permissions': {m: READ for m in OPERATIONAL + ['landing'] + MONEY + BOOKS},
    },
]


def apply_roles(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    User = apps.get_model('auth', 'User')
    for row in ROLES:
        row = dict(row)
        RoleDefinition.objects.update_or_create(slug=row.pop('slug'), defaults={**row, 'is_system': True})
    # Django admin follows the role: only administrators keep it.
    for role in ('finance', 'manager', 'staff', 'viewer'):
        User.objects.filter(profile__role=role, is_superuser=False).update(is_staff=False)
    from django.core.cache import cache
    from django.db import transaction
    try:
        with transaction.atomic():  # a savepoint: a failure must not poison the migration
            cache.delete(CACHE_KEY)
    except Exception:
        pass  # a fresh database may not have the cache table yet; nothing cached then


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0142_season'),
    ]

    operations = [
        migrations.RunPython(apply_roles, migrations.RunPython.noop),
    ]
