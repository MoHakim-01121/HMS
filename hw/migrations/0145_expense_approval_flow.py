"""Beban: diajukan, disetujui, dibayar; selalu rupiah; kategori Gaji.

Keputusan user 2026-10-11: beban dicatat Finance, disetujui Finance (boleh
pencatatnya sendiri), Manager atau Admin, lalu dibayar dari rekening IDR
cabangnya; pembukuan saat dibayar. Data lama (bila ada) dipetakan: draft →
submitted, posted dengan pembayaran → paid, posted tanpa pembayaran →
approved. Kategori "Gaji & Honor" dengan akunnya sendiri; Manager boleh
menyetujui beban.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SALARY_ACCOUNT = '5400-EXP-SALARY'


def map_statuses(apps, schema_editor):
    Expense = apps.get_model('hw', 'Expense')
    ExpensePayment = apps.get_model('hw', 'ExpensePayment')
    Expense.objects.filter(status='draft').update(status='submitted')
    paid = ExpensePayment.objects.filter(status='paid').values('expense_id')
    Expense.objects.filter(status='posted', pk__in=paid).update(status='paid')
    Expense.objects.filter(status='posted').update(status='approved')
    ExpensePayment.objects.filter(status='pending').update(status='void')


def seed_salary_and_manager_approval(apps, schema_editor):
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    ExpenseCategory = apps.get_model('hw', 'ExpenseCategory')
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')
    LedgerAccount.objects.get_or_create(code=SALARY_ACCOUNT, defaults={
        'name': 'Beban Gaji & Honor', 'type': 'expense', 'normal_balance': 'debit',
        'is_postable': True, 'is_active': True,
    })
    ExpenseCategory.objects.get_or_create(code='SALARY', defaults={
        'name': 'Gaji & Honor', 'ledger_account_id': SALARY_ACCOUNT,
    })
    manager = RoleDefinition.objects.filter(slug='manager').first()
    if manager is not None:
        perms = dict(manager.permissions or {})
        actions = set(perms.get('expenses', [])) | {'view', 'export', 'approve'}
        perms['expenses'] = sorted(actions)
        manager.permissions = perms
        manager.save(update_fields=['permissions'])
    from django.core.cache import cache
    from django.db import transaction
    try:
        with transaction.atomic():
            cache.delete('hw:role_matrix:v1')
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0144_delete_watarget'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='expense',
            name='expense_status_valid',
        ),
        migrations.AddField(
            model_name='expense',
            name='decided_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='decided_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='expense',
            name='decision_note',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='expense',
            name='currency',
            field=models.CharField(default='IDR', max_length=3),
        ),
        migrations.AlterField(
            model_name='expense',
            name='status',
            field=models.CharField(choices=[('submitted', 'Submitted'), ('approved', 'Approved'), ('paid', 'Paid'), ('rejected', 'Rejected'), ('voided', 'Voided')], db_index=True, default='submitted', max_length=20),
        ),
        migrations.AlterField(
            model_name='expenseline',
            name='amount_sar',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='expensepayment',
            name='status',
            field=models.CharField(choices=[('paid', 'Paid'), ('void', 'Void')], default='paid', max_length=10),
        ),
        migrations.RunPython(map_statuses, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='expense',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['submitted', 'approved', 'paid', 'rejected', 'voided'])), name='expense_status_valid'),
        ),
        migrations.RunPython(seed_salary_and_manager_approval, migrations.RunPython.noop),
    ]
