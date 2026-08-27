"""Append-only enforcement di level DB (Postgres).

Trigger BEFORE UPDATE OR DELETE pada tabel journal → RAISE EXCEPTION.
Menutup celah queryset .update()/.delete() massal yang lolos dari
override AppendOnlyModel di app layer. SQLite (dev) hanya mengandalkan
app layer + `check_finance`.
"""
from django.db import migrations

PG_UP = """
CREATE OR REPLACE FUNCTION hw_journal_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger append-only: % pada % ditolak', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_journalentry_append_only ON hw_journalentry;
CREATE TRIGGER trg_journalentry_append_only
    BEFORE UPDATE OR DELETE ON hw_journalentry
    FOR EACH ROW EXECUTE FUNCTION hw_journal_block_mutation();

DROP TRIGGER IF EXISTS trg_journalline_append_only ON hw_journalline;
CREATE TRIGGER trg_journalline_append_only
    BEFORE UPDATE OR DELETE ON hw_journalline
    FOR EACH ROW EXECUTE FUNCTION hw_journal_block_mutation();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_journalentry_append_only ON hw_journalentry;
DROP TRIGGER IF EXISTS trg_journalline_append_only ON hw_journalline;
DROP FUNCTION IF EXISTS hw_journal_block_mutation();
"""


def up(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PG_UP)


def down(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PG_DOWN)


class Migration(migrations.Migration):
    dependencies = [("hw", "0068_journalentry_journal_entry_company_seq_uniq")]
    operations = [migrations.RunPython(up, down)]
