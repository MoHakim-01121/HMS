"""Per-hotel board types (v2.0 §10 follow-up).

Until now every hotel implicitly allowed anything, because the CL form took
Meals as free text. Backfilling every active hotel with the full seeded set
keeps that same freedom on day one — operators then narrow it per hotel —
rather than starting from empty, which would silently disable the new
dropdown everywhere and force a round of data entry before any CL could be
written the new way.
"""
from django.db import migrations, models


def grant_all_plans(apps, schema_editor):
    Hotel = apps.get_model('hw', 'Hotel')
    MealPlan = apps.get_model('hw', 'MealPlan')
    codes = list(MealPlan.objects.filter(is_active=True))
    if not codes:
        return
    for hotel in Hotel.objects.filter(is_active=True):
        hotel.meal_plans.set(codes)


def revoke_all_plans(apps, schema_editor):
    Hotel = apps.get_model('hw', 'Hotel')
    for hotel in Hotel.objects.all():
        hotel.meal_plans.clear()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0103_remittanceline_settlement'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotel',
            name='meal_plans',
            field=models.ManyToManyField(blank=True, related_name='hotels', to='hw.mealplan'),
        ),
        migrations.RunPython(grant_all_plans, revoke_all_plans),
    ]
