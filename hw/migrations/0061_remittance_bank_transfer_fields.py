from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0060_paymentrecord_received_in_jakarta'),
    ]

    operations = [
        migrations.AddField(
            model_name='remittance',
            name='amount_idr',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='remittance',
            name='exchange_rate',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='remittance',
            name='received_amount_sar',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
