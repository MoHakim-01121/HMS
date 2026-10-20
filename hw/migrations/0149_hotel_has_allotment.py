from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0148_cl_salesperson'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotel',
            name='has_allotment',
            field=models.BooleanField(default=False),
        ),
    ]
