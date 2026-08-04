# Move the hardcoded ROLE_MATRIX into editable rows.

from django.db import migrations, models


def seed_roles(apps, schema_editor):
    """Copy the code matrix into the table, verbatim.

    Seeding from a literal rather than importing hw.permissions keeps the
    migration reproducible: a later edit to the constant must not retroactively
    change what an already-migrated database was given.
    """
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')

    modules = [
        'cl', 'invoice', 'services', 'hotels', 'clients',
        'remittance', 'calendar', 'penalty', 'users', 'dev',
    ]
    every = ['create', 'delete', 'edit', 'export', 'view']
    read = ['export', 'view']
    no_delete = ['create', 'edit', 'export', 'view']
    operational = ['cl', 'invoice', 'services', 'hotels', 'clients', 'calendar', 'penalty']

    staff_perms = {m: list(no_delete) for m in operational}
    staff_perms['remittance'] = list(read)

    viewer_perms = {m: list(read) for m in operational}
    viewer_perms['remittance'] = list(read)

    rows = [
        {
            'slug': 'admin', 'label': 'Administrator', 'order': 10,
            'description': 'Full access, including user and role management.',
            'grants_django_staff': True,
            'permissions': {m: list(every) for m in modules},
        },
        {
            'slug': 'manager', 'label': 'Manager', 'order': 20,
            'description': 'Full access to all operational modules; cannot manage users.',
            'grants_django_staff': True,
            'permissions': {m: list(every) for m in modules if m not in ('users', 'dev')},
        },
        {
            'slug': 'staff', 'label': 'Staff', 'order': 30,
            'description': 'Create and edit operational records; no deleting, remittance read-only.',
            'grants_django_staff': False,
            'permissions': staff_perms,
        },
        {
            'slug': 'viewer', 'label': 'Viewer', 'order': 40,
            'description': 'Read-only across every module, including exports and PDFs.',
            'grants_django_staff': False,
            'permissions': viewer_perms,
        },
    ]

    for row in rows:
        RoleDefinition.objects.update_or_create(
            slug=row.pop('slug'), defaults={**row, 'is_system': True},
        )


def unseed_roles(apps, schema_editor):
    """No-op: DeleteModel in the reverse operation takes the rows with it."""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0036_userprofile_company_access_userprofile_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoleDefinition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=32, unique=True)),
                ('label', models.CharField(max_length=64)),
                ('description', models.CharField(blank=True, max_length=200)),
                ('permissions', models.JSONField(blank=True, default=dict)),
                ('grants_django_staff', models.BooleanField(default=False, help_text='Members of this role also get Django admin (is_staff).')),
                ('is_system', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=100)),
            ],
            options={
                'verbose_name': 'Role',
                'verbose_name_plural': 'Roles',
                'ordering': ('order', 'label'),
            },
        ),
        # Custom role slugs can be longer than the four built-ins, and the valid
        # set is now a table rather than a fixed choices list.
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(default='staff', max_length=32),
        ),
        migrations.RunPython(seed_roles, unseed_roles),
    ]
