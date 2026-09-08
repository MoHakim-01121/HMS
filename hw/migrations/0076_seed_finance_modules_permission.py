"""Grant the new per-area finance modules to existing RoleDefinition rows.

The finance surface used to be guarded through proxy modules (payments under
'invoice', periods under 'remittance', statements under 'clients'). That made
it impossible to grant money operations independently from their operational
neighbours (least privilege / segregation of duties). These new modules are now
the real gate: 'payments', 'journal', 'statements' and 'periods'.

Like 0045 (visits) and 0050 (landing), this merges the new keys into each row's
permissions dict without touching anything else, so a business that has since
customised roles through /roles/ keeps those edits. 'admin' needs no row
change: it is force-granted every module in code (hw.permissions.role_matrix)
regardless of what this table says.
"""
from django.db import migrations

NO_DELETE = ['create', 'edit', 'export', 'view']
EVERY     = ['create', 'delete', 'edit', 'export', 'view']
READ      = ['export', 'view']

GRANTS = {
    # Managers control money movement but never hand-edit the system-generated
    # journal/statements; periods can be opened/closed/locked but not deleted.
    'manager': {
        'payments':    EVERY,
        'journal':     READ,
        'statements':  READ,
        'periods':     NO_DELETE,
    },
    # Staff record and amend payments; the rest of the ledger stays read-only
    # (closing/locking a period is a control decision).
    'staff': {
        'payments':    NO_DELETE,
        'journal':     READ,
        'statements':  READ,
        'periods':     READ,
    },
    # Read-only account: everyone gets at least the ledger reports.
    'viewer': {
        'payments':    READ,
        'journal':     READ,
        'statements':  READ,
        'periods':     READ,
    },
}


def grant_finance(apps, schema_editor):
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


def unseed_finance(apps, schema_editor):
    """No-op: reversing a module grant isn't meaningful once a business may
    have edited roles through /roles/ since; nothing downstream depends on
    this migration's reverse running cleanly."""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0075_journalentry_proof'),
    ]

    operations = [
        migrations.RunPython(grant_finance, unseed_finance),
    ]
