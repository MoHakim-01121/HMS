"""Seed Branch rows and backfill Reservation.owner_branch.

FASE A. Semua reservasi historis milik Surabaya (satu-satunya cabang operasional
saat ini). Jakarta & Pusat di-seed non-aktif untuk kesiapan — v2.0 memilih
'Pusat = Branch biasa'.
"""
from django.db import migrations

SEED = [
    ('sby',   'Surabaya', True),
    ('jkt',   'Jakarta',  False),
    ('pusat', 'Pusat',    True),
]


def seed(apps, schema_editor):
    Branch = apps.get_model('hw', 'Branch')
    for code, name, is_active in SEED:
        Branch.objects.update_or_create(
            code=code, defaults={'name': name, 'is_active': is_active},
        )
    Reservation = apps.get_model('hw', 'Reservation')
    Reservation.objects.filter(owner_branch__isnull=True).update(owner_branch_id='sby')


def unseed(apps, schema_editor):
    Reservation = apps.get_model('hw', 'Reservation')
    Reservation.objects.update(owner_branch=None)
    Branch = apps.get_model('hw', 'Branch')
    Branch.objects.filter(code__in=[c for c, _, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0080_branch_userprofile_branch_access_journalline_branch_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
