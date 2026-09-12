"""Seed the standard board-type codes (v2.0 §10)."""
from django.db import migrations

SEED = [
    ('RO', 'Room Only'),
    ('BB', 'Bed & Breakfast'),
    ('HB', 'Half Board'),
    ('FB', 'Full Board'),
]


def seed(apps, schema_editor):
    MealPlan = apps.get_model('hw', 'MealPlan')
    for code, name in SEED:
        MealPlan.objects.update_or_create(code=code, defaults={'name': name, 'is_active': True})


def unseed(apps, schema_editor):
    apps.get_model('hw', 'MealPlan').objects.filter(code__in=[c for c, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0092_mealplan_roomtype_occupancy_roomtype_view_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
