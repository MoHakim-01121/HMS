"""Bantuan untuk aturan database yang hanya ada di PostgreSQL.

Produksi memakai PostgreSQL; trigger, EXCLUDE constraint, dan constraint
trigger tidak ada di SQLite. Migrasi memakai ``pg_sql`` supaya tetap bisa
jalan di SQLite (tanpa aturan tambahan itu), dan test memakai ``pg_only`` untuk
aturan yang hanya bisa diuji di PostgreSQL. Jalankan test di PostgreSQL dengan
TEST_DATABASE_URL (lihat config/settings.py) sebelum menyatakan aturan DB beres.
"""
import unittest
from contextlib import contextmanager

from django.db import connection, migrations


def pg_sql(up, down):
    """Operasi migrasi: jalankan `up`/`down` hanya di PostgreSQL."""
    def forward(apps, schema_editor):
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(up, params=None)

    def backward(apps, schema_editor):
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(down, params=None)

    return migrations.RunPython(forward, backward)


def settle_constraints(schema_editor):
    """Panggil di akhir RunPython yang mengubah data sebelum operasi skema.

    Di PostgreSQL, foreign key Django bersifat DEFERRABLE INITIALLY DEFERRED:
    pemeriksaannya menggantung sampai COMMIT, dan ALTER TABLE pada tabel itu
    dalam transaksi yang sama ditolak ("pending trigger events"). Memaksa
    pemeriksaan selesai sekarang membuat migrasi data + skema tetap satu
    transaksi (semua atau tidak sama sekali)."""
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE', params=None)
        schema_editor.execute('SET CONSTRAINTS ALL DEFERRED', params=None)


@contextmanager
def user_triggers_disabled(*tables, using=None):
    """Matikan trigger buatan kita pada `tables` selama blok ini (PostgreSQL).

    Hanya untuk dua keperluan: migrasi skema yang harus menulis ulang kunci di
    tabel append-only, dan test yang meniru orang yang mengutak-atik data
    langsung di database. Kode aplikasi tidak boleh memakainya. Butuh hak
    pemilik tabel; pemeriksaan foreign key tetap berjalan."""
    conn = using or connection
    if conn.vendor != 'postgresql':
        yield
        return
    with conn.cursor() as cur:
        cur.execute('SET CONSTRAINTS ALL IMMEDIATE')
        for table in tables:
            cur.execute(f'ALTER TABLE {conn.ops.quote_name(table)} DISABLE TRIGGER USER')
    try:
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for table in tables:
                cur.execute(f'ALTER TABLE {conn.ops.quote_name(table)} ENABLE TRIGGER USER')
            cur.execute('SET CONSTRAINTS ALL DEFERRED')


pg_only = unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Aturan ini hanya ada di PostgreSQL — jalankan dengan TEST_DATABASE_URL.',
)
