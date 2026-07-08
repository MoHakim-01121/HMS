from django.db import migrations
from django.core.management import call_command


def create_cache_table(apps, schema_editor):
    call_command('createcachetable', 'hw_cache_table')


def drop_cache_table(apps, schema_editor):
    schema_editor.execute('DROP TABLE IF EXISTS hw_cache_table')


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0029_composite_indexes'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
