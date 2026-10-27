from django.db import migrations


def seed_retained_earnings(apps, schema_editor):
    """Laba Ditahan: laba tahun-tahun buku sebelumnya. Tidak pernah diposting;
    trial balance menghitungnya dengan tutup tahun virtual."""
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    LedgerAccount.objects.get_or_create(code='3200-RETAINED', defaults={
        'name': 'Laba Ditahan', 'type': 'equity', 'normal_balance': 'credit',
        'is_postable': False, 'is_active': True,
    })


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0154_staff_records_payments'),
    ]

    operations = [
        migrations.RunPython(seed_retained_earnings, migrations.RunPython.noop),
    ]
