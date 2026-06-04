from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0008_merge_0007_hotel_model_0007_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotel',
            name='city',
            field=models.CharField(
                choices=[('makkah', 'Makkah'), ('madinah', 'Madinah')],
                default='makkah',
                max_length=20,
            ),
        ),
    ]
