"""Seed akun beban baru + AP + kategori Expense default (FASE D)."""
from django.db import migrations


def seed(apps, schema_editor):
    from hw.finance.accounts import (
        ACCOUNTS, DEFAULT_EXPENSE_CATEGORIES, normal_balance_for,
    )
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    ExpenseCategory = apps.get_model('hw', 'ExpenseCategory')

    for spec in ACCOUNTS:
        LedgerAccount.objects.update_or_create(
            code=spec['code'],
            defaults={
                'name': spec['name'],
                'type': spec['type'],
                'normal_balance': normal_balance_for(spec['type']),
                'is_postable': spec.get('is_postable', True),
                'is_active': True,
            },
        )
    for code, name, ledger_code in DEFAULT_EXPENSE_CATEGORIES:
        ExpenseCategory.objects.update_or_create(
            code=code,
            defaults={'name': name, 'ledger_account_id': ledger_code, 'is_active': True},
        )


def unseed(apps, schema_editor):
    ExpenseCategory = apps.get_model('hw', 'ExpenseCategory')
    ExpenseCategory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0086_alter_journalentry_entry_type_expense_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
