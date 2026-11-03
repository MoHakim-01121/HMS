import django.db.models.deletion
from django.db import migrations, models


def assign_invoice_seasons(apps, schema_editor):
    Invoice = apps.get_model('hw', 'Invoice')
    Season = apps.get_model('hw', 'Season')
    db = schema_editor.connection.alias
    for invoice in Invoice.objects.using(db).filter(issued_date__isnull=False).only('pk', 'issued_date').iterator():
        season_id = Season.objects.using(db).filter(
            date_from__lte=invoice.issued_date, date_to__gte=invoice.issued_date,
        ).values_list('pk', flat=True).first()
        if season_id:
            Invoice.objects.using(db).filter(pk=invoice.pk).update(season_id=season_id)


class Migration(migrations.Migration):
    dependencies = [
        ('hw', '0161_bank_match'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='season',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='invoices', to='hw.season',
            ),
        ),
        migrations.RunPython(assign_invoice_seasons, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='invoice',
            name='invoice_number',
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.UniqueConstraint(
                condition=models.Q(('season__isnull', False)),
                fields=('season', 'invoice_number'), name='invoice_number_season_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.UniqueConstraint(
                condition=models.Q(('season__isnull', True)),
                fields=('invoice_number',), name='invoice_number_no_season_uniq',
            ),
        ),
    ]
