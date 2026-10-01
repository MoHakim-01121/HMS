"""Schema v2 F9 — akses dan audit.

* UserProfile.branch_access (teks 'all' atau satu kode cabang) menjadi
  `all_branches` + tabel UserBranchAccess (satu baris per cabang).
* UserProfile.role tetap teks slug, tetapi di PostgreSQL menjadi FOREIGN KEY
  ke hw_roledefinition.slug (pola yang sama dengan money_account.currency, F2c).
* ActivityLog tidak ikut terhapus bersama akunnya: user SET_NULL + snapshot
  `actor_username`; aksi dibatasi CHECK.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from hw.db_pg import pg_sql, settle_constraints


def normalise(apps, schema_editor):
    Profile = apps.get_model('hw', 'UserProfile')
    Access = apps.get_model('hw', 'UserBranchAccess')
    Branch = apps.get_model('hw', 'Branch')
    Role = apps.get_model('hw', 'RoleDefinition')
    Log = apps.get_model('hw', 'ActivityLog')

    roles = set(Role.objects.values_list('slug', flat=True))
    branches = set(Branch.objects.values_list('code', flat=True))
    problems = []
    for p in Profile.objects.select_related('user'):
        if p.role not in roles:
            problems.append(f'{p.user.username}: peran "{p.role}" tidak ada')
        if p.branch_access != 'all':
            if p.branch_access not in branches:
                problems.append(f'{p.user.username}: cabang "{p.branch_access}" tidak ada')
                continue
            Profile.objects.filter(pk=p.pk).update(all_branches=False)
            Access.objects.create(profile_id=p.pk, branch_id=p.branch_access)
    if problems:
        raise RuntimeError('Profil berikut perlu dibereskan sebelum migrasi 0136: ' + '; '.join(problems[:40]))

    usernames = dict(apps.get_model(*settings.AUTH_USER_MODEL.split('.')).objects.values_list('pk', 'username'))
    for user_id, username in usernames.items():
        Log.objects.filter(user_id=user_id).update(actor_username=username)
    bad = Log.objects.exclude(action__in=['login', 'create', 'edit', 'delete', 'pdf']).values_list('action', flat=True)
    if bad.exists():
        raise RuntimeError(f'ActivityLog dengan aksi tak dikenal: {sorted(set(bad))[:10]}')
    settle_constraints(schema_editor)


PG_UP = """
ALTER TABLE hw_userprofile
    ADD CONSTRAINT hw_userprofile_role_fk FOREIGN KEY (role)
    REFERENCES hw_roledefinition (slug) ON UPDATE CASCADE DEFERRABLE INITIALLY DEFERRED;
"""
PG_DOWN = "ALTER TABLE hw_userprofile DROP CONSTRAINT IF EXISTS hw_userprofile_role_fk;"


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0135_journal_typed_sources'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='userprofile', name='all_branches', field=models.BooleanField(default=True)),
        migrations.CreateModel(
            name='UserBranchAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.branch')),
                ('profile', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='hw.userprofile',
                )),
            ],
            options={'verbose_name': 'User Branch Access', 'verbose_name_plural': 'User Branch Access'},
        ),
        migrations.AddConstraint(
            model_name='userbranchaccess',
            constraint=models.UniqueConstraint(fields=('profile', 'branch'), name='user_branch_access_uniq'),
        ),
        migrations.AddField(
            model_name='activitylog', name='actor_username', field=models.CharField(default='', max_length=150),
            preserve_default=False,
        ),
        migrations.RunPython(normalise, migrations.RunPython.noop),
        migrations.RemoveField(model_name='userprofile', name='branch_access'),
        migrations.AlterField(
            model_name='userbranchaccess', name='profile',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='branch_access', to='hw.userprofile',
            ),
        ),
        migrations.AlterField(
            model_name='activitylog', name='user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='activity_logs', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name='activitylog',
            constraint=models.CheckConstraint(
                condition=models.Q(action__in=['login', 'create', 'edit', 'delete', 'pdf']),
                name='activity_log_action_valid',
            ),
        ),
        pg_sql(PG_UP, PG_DOWN),
    ]
