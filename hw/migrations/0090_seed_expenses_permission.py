"""Grant the new 'expenses' module to existing RoleDefinition rows.

Same merge-only pattern as 0045 (visits), 0050 (landing), 0076 (finance
modules) -- a business that has since customised roles through /roles/
keeps those edits. 'admin' needs no row change (force-granted in code).
'manager' is granted here explicitly even though DEFAULT_ROLE_MATRIX derives
it from "every module except a deny-list", because the live table is what
role_matrix() actually reads once rows exist.
"""
from django.db import migrations

NO_DELETE = ['create', 'edit', 'export', 'view']
EVERY     = ['create', 'delete', 'edit', 'export', 'view']
READ      = ['export', 'view']

GRANTS = {
    'manager': {'expenses': EVERY},
    'staff':   {'expenses': NO_DELETE},
    'viewer':  {'expenses': READ},
}


def grant(apps, schema_editor):
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    for slug, modules in GRANTS.items():
        row = RoleDefinition.objects.filter(slug=slug).first()
        if row is None:
            continue
        merged = row.permissions or {}
        changed = False
        for module, actions in modules.items():
            if module not in merged:
                merged[module] = list(actions)
                changed = True
        if changed:
            row.permissions = merged
            row.save(update_fields=['permissions'])


def unseed(apps, schema_editor):
    """No-op, same rationale as 0076."""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0089_allocation_aggregate_pg_triggers'),
    ]

    operations = [
        migrations.RunPython(grant, unseed),
    ]
