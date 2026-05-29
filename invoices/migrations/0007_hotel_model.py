from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0006_payment_proof'),
    ]

    operations = [
        migrations.CreateModel(
            name='Hotel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company', models.CharField(choices=[('konoz', 'Konoz United'), ('ijabah', 'Ijabah')], default='konoz', max_length=20)),
                ('name', models.CharField(max_length=200)),
                ('stars', models.PositiveSmallIntegerField(default=3)),
                ('area', models.CharField(blank=True, max_length=100)),
                ('lat', models.FloatField(blank=True, null=True)),
                ('lng', models.FloatField(blank=True, null=True)),
                ('avg_occupancy', models.DecimalField(blank=True, decimal_places=2, help_text='Rata-rata orang per kamar, mis. 3.4', max_digits=5, null=True)),
                ('note', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
