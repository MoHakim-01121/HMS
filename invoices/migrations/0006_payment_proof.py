from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0005_client_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='proof',
            field=models.FileField(blank=True, null=True, upload_to='payments/proof/'),
        ),
    ]
