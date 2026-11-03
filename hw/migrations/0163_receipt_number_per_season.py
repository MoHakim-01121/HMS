import django.db.models.deletion
from django.db import migrations, models


def assign_receipt_seasons(apps, schema_editor):
    Receipt = apps.get_model('hw', 'Receipt')
    Season = apps.get_model('hw', 'Season')
    db = schema_editor.connection.alias
    for receipt in Receipt.objects.using(db).only('pk', 'receipt_date').iterator():
        season_id = Season.objects.using(db).filter(
            date_from__lte=receipt.receipt_date, date_to__gte=receipt.receipt_date,
        ).values_list('pk', flat=True).first()
        if season_id:
            Receipt.objects.using(db).filter(pk=receipt.pk).update(season_id=season_id)


class Migration(migrations.Migration):
    dependencies = [
        ('hw', '0162_invoice_number_per_season'),
    ]

    operations = [
        migrations.AddField(
            model_name='receipt',
            name='season',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='receipts', to='hw.season',
            ),
        ),
        migrations.RunPython(assign_receipt_seasons, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='receipt',
            name='receipt_number',
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AddConstraint(
            model_name='receipt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('season__isnull', False)),
                fields=('season', 'receipt_number'), name='receipt_number_season_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='receipt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('season__isnull', True)),
                fields=('receipt_number',), name='receipt_number_no_season_uniq',
            ),
        ),
    ]
