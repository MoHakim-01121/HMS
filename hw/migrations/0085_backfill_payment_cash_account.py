"""Backfill PaymentRecord.cash_account dari received_in.

FASE C. received_in ('sby'/'jkt'/'pusat') → CashAccount cabang yang sudah
di-seed (0083). Baris bank riil tidak bisa diturunkan otomatis — biarkan
kosong; received_in tetap jadi fallback routing di posting layer.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    PaymentRecord = apps.get_model('hw', 'PaymentRecord')
    CashAccount = apps.get_model('hw', 'CashAccount')
    by_branch = {c.branch_id: c for c in CashAccount.objects.all()}
    for code, acc in by_branch.items():
        PaymentRecord.objects.filter(
            received_in=code, bank_account__isnull=True, cash_account__isnull=True,
        ).update(cash_account=acc)


def unbackfill(apps, schema_editor):
    PaymentRecord = apps.get_model('hw', 'PaymentRecord')
    PaymentRecord.objects.update(cash_account=None)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0084_paymentrecord_bank_account_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
