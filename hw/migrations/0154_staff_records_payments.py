"""Staff records client payments again.

0153 gave Staff view, create and export on 'payments' (decided 2026-10-20),
but the Staff row restored from production came back without 'payments' at
all: staff could not record a client payment, and the dashboard's "Payments I
uploaded" and the Payments menu were gone (found 2026-10-22). Put the three
actions back, keeping anything else the row already allows.
"""
from django.db import migrations

CACHE_KEY = 'hw:role_matrix:v1'

STAFF_PAYMENTS = {'view', 'create', 'export'}


def _clear_cache():
    from django.core.cache import cache
    from django.db import transaction
    try:
        with transaction.atomic():  # a savepoint: a failure must not poison the migration
            cache.delete(CACHE_KEY)
    except Exception:
        pass  # a fresh database may not have the cache table yet; nothing cached then


def give_payments(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    role = RoleDefinition.objects.filter(slug='staff').first()
    if role is None:
        return
    perms = dict(role.permissions or {})
    perms['payments'] = sorted(set(perms.get('payments') or []) | STAFF_PAYMENTS)
    role.permissions = perms
    role.save(update_fields=['permissions'])
    _clear_cache()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0153_bank_module'),
    ]

    operations = [
        migrations.RunPython(give_payments, migrations.RunPython.noop),
    ]
