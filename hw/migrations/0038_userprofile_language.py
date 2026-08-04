from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0037_roledefinition'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='language',
            field=models.CharField(
                choices=[('en', 'English'), ('id', 'Indonesian')],
                default='en', max_length=5,
            ),
        ),
    ]
