"""Seed satu CashAccount per kas cabang yang sudah dipakai jurnal.

FASE B. Memetakan kas virtual lama (cash_sby/jkt/pusat → LedgerAccount
1000-KAS-*) ke master CashAccount konkret yang ber-cabang & ber-currency.
Rekening BANK riil tidak di-seed di sini (data faktual, diisi via admin).
"""
from django.db import migrations

# (branch_code, cash account name, ledger account code)
SEED = [
    ('sby',   'Kas Surabaya',   '1000-KAS-SBY'),
    ('jkt',   'Kas Jakarta',    '1000-KAS-JKT'),
    ('pusat', 'Kas Pusat (HQ)', '1000-KAS-PUSAT'),
]


def seed(apps, schema_editor):
    Branch = apps.get_model('hw', 'Branch')
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    CashAccount = apps.get_model('hw', 'CashAccount')
    for branch_code, name, ledger_code in SEED:
        try:
            branch = Branch.objects.get(code=branch_code)
            ledger = LedgerAccount.objects.get(code=ledger_code)
        except (Branch.DoesNotExist, LedgerAccount.DoesNotExist):
            continue
        CashAccount.objects.update_or_create(
            branch=branch, name=name, currency='SAR',
            defaults={'ledger_account': ledger, 'is_active': True},
        )


def unseed(apps, schema_editor):
    CashAccount = apps.get_model('hw', 'CashAccount')
    CashAccount.objects.filter(name__in=[n for _, n, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0082_bankaccount_cashaccount'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
