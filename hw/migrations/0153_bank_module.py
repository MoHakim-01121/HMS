"""'bank' module, and Staff records client payments only.

Decided 2026-10-20. Bank and cash accounts, transfers and exchanges, and
reconciliation leave 'payments' (and 'statements') for a module of their own,
so recording a client payment no longer carries the power to move money
between accounts, which is booked straight away with no second person.

Every role row gets on 'bank' what it had on 'payments', so nobody gains or
loses the bank side by the split. Staff then drops to recording payments: view,
create and export on 'payments', nothing on 'bank', 'remittance' or 'expenses'
(Admin or Finance confirm what Staff records, and handle the rest).
"""
from django.db import migrations

CACHE_KEY = 'hw:role_matrix:v1'

STAFF_DESCRIPTION = 'Create and edit operational records; no deleting; records client payments for Finance to confirm.'


def _clear_cache():
    from django.core.cache import cache
    from django.db import transaction
    try:
        with transaction.atomic():  # a savepoint: a failure must not poison the migration
            cache.delete(CACHE_KEY)
    except Exception:
        pass  # a fresh database may not have the cache table yet; nothing cached then


def split_bank(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    for role in RoleDefinition.objects.all():
        perms = dict(role.permissions or {})
        if perms.get('payments'):
            perms['bank'] = sorted(perms['payments'])
        if role.slug == 'staff':
            perms['payments'] = ['create', 'export', 'view']
            for module in ('bank', 'remittance', 'expenses'):
                perms.pop(module, None)
            role.description = STAFF_DESCRIPTION
        role.permissions = perms
        role.save(update_fields=['permissions', 'description'])
    _clear_cache()


def join_bank(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    for role in RoleDefinition.objects.all():
        perms = dict(role.permissions or {})
        perms.pop('bank', None)
        if role.slug == 'staff':
            perms['payments'] = ['export', 'view']
            perms['remittance'] = ['export', 'view']
            perms['expenses'] = ['export', 'view']
            role.description = 'Create and edit operational records; no deleting; money read-only.'
        role.permissions = perms
        role.save(update_fields=['permissions', 'description'])
    _clear_cache()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0152_expense_claims'),
    ]

    operations = [
        migrations.RunPython(split_bank, join_bank),
    ]
