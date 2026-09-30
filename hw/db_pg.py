"""Bantuan untuk aturan database yang hanya ada di PostgreSQL.

Produksi memakai PostgreSQL; trigger, EXCLUDE constraint, dan constraint
trigger tidak ada di SQLite. Migrasi memakai ``pg_sql`` supaya tetap bisa
jalan di SQLite (tanpa aturan tambahan itu), dan test memakai ``pg_only`` untuk
aturan yang hanya bisa diuji di PostgreSQL. Jalankan test di PostgreSQL dengan
TEST_DATABASE_URL (lihat config/settings.py) sebelum menyatakan aturan DB beres.
"""
import unittest

from django.db import connection, migrations


def pg_sql(up, down):
    """Operasi migrasi: jalankan `up`/`down` hanya di PostgreSQL."""
    def forward(apps, schema_editor):
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(up)

    def backward(apps, schema_editor):
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(down)

    return migrations.RunPython(forward, backward)


def is_postgres():
    return connection.vendor == 'postgresql'


pg_only = unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Aturan ini hanya ada di PostgreSQL — jalankan dengan TEST_DATABASE_URL.',
)
