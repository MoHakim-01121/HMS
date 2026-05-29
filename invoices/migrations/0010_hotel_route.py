from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0009_hotel_city'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotel',
            name='route',
            field=models.JSONField(blank=True, help_text='Intermediate waypoints [[lat,lng],...] between mosque and hotel', null=True),
        ),
    ]
