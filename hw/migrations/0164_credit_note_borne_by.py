from django.db import migrations, models


def seed_branch_discount_account(apps, schema_editor):
    """Beban Diskon Ditanggung Cabang: the debit of a credit note the branch
    bears. Databases past 0066 do not get it from the initial seed."""
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    LedgerAccount.objects.get_or_create(code='5350-EXP-BR-DISC', defaults={
        'name': 'Beban Diskon Ditanggung Cabang', 'type': 'expense', 'normal_balance': 'debit',
        'is_postable': True, 'is_active': True,
    })


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0163_receipt_number_per_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditnote',
            name='borne_by',
            field=models.CharField(choices=[('hq', 'Head office'), ('branch', 'Branch')], db_index=True, default='hq', max_length=10),
        ),
        migrations.RunPython(seed_branch_discount_account, migrations.RunPython.noop),
    ]
