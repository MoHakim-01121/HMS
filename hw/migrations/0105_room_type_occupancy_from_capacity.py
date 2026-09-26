"""Occupancy is now derived from capacity (RoomType.save()), no longer entered.

Existing rows were typed by hand, so the two can disagree ("Quad", capacity
2). Capacity wins: it is the field that has always driven the CL pax count.
"""
from django.db import migrations

OCCUPANCY_BY_CAPACITY = {2: 'double', 3: 'triple', 4: 'quad', 5: 'quint'}


def derive_occupancy(apps, schema_editor):
    RoomType = apps.get_model('hw', 'RoomType')
    for capacity, occupancy in OCCUPANCY_BY_CAPACITY.items():
        RoomType.objects.filter(capacity=capacity).update(occupancy=occupancy)
    RoomType.objects.exclude(capacity__in=OCCUPANCY_BY_CAPACITY).update(occupancy='')


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0104_hotel_meal_plans'),
    ]

    operations = [
        migrations.RunPython(derive_occupancy, migrations.RunPython.noop),
    ]
