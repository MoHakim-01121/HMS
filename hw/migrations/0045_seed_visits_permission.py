"""Grant the new 'visits' module to existing RoleDefinition rows.

Migration 0037 seeded the table from a point-in-time literal, so a module
added afterward (this is the first one) isn't retroactively known to already-
migrated rows -- including a fresh test database, since it replays every
migration. This merges 'visits' into each row's permissions dict without
touching anything else, so a business that has since customised 'staff' or
'manager' through /roles/ keeps those edits. 'admin' needs no row change: it
is force-granted every module in code (hw.permissions.role_matrix)
regardless of what this table says.
"""
from django.db import migrations

NO_DELETE = ['create', 'edit', 'export', 'view']
EVERY     = ['create', 'delete', 'edit', 'export', 'view']
READ      = ['export', 'view']

GRANTS = {
    'manager': EVERY,
    'staff':   NO_DELETE,
    'viewer':  READ,
}


def grant_visits(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    for slug, actions in GRANTS.items():
        row = RoleDefinition.objects.filter(slug=slug).first()
        if row is None or 'visits' in (row.permissions or {}):
            continue
        row.permissions = {**(row.permissions or {}), 'visits': list(actions)}
        row.save(update_fields=['permissions'])


def unseed_visits(apps, schema_editor):
    """No-op: reversing a module grant isn't meaningful once a business may
    have edited roles through /roles/ since; nothing downstream depends on
    this migration's reverse running cleanly."""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0044_visit_visitphoto_visit_hw_visit_company_status_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(grant_visits, unseed_visits),
    ]
