"""Penegakan agregat alokasi di level DB (Postgres) — v2.0 §54:
Σ PaymentAllocation.amount_sar ≤ PaymentRecord.amount_sar,
Σ RemittanceAllocation.amount_sar ≤ RemittanceSettlement.received_amount_sar.

Row-level CHECK tidak bisa mengekspresikan SUM lintas baris — sudah
ditegakkan di service layer (posting.allocate_payment/reallocate_payment,
settlement_service.allocate_settlement); trigger ini menutup celah INSERT/
UPDATE massal yang melewati service layer. SQLite (dev/test) hanya
mengandalkan app layer, sama seperti pola trigger append-only jurnal
(lihat 0069).
"""
from django.db import migrations

PG_UP = """
CREATE OR REPLACE FUNCTION hw_paymentallocation_check_sum() RETURNS trigger AS $$
DECLARE
    total bigint;
    cap bigint;
BEGIN
    SELECT COALESCE(SUM(amount_sar), 0) INTO total
        FROM hw_paymentallocation WHERE payment_id = NEW.payment_id;
    SELECT amount_sar INTO cap FROM hw_paymentrecord WHERE id = NEW.payment_id;
    IF cap IS NOT NULL AND total > cap THEN
        RAISE EXCEPTION 'PaymentAllocation sum (%) exceeds PaymentRecord.amount_sar (%) for payment_id=%',
            total, cap, NEW.payment_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_paymentallocation_check_sum ON hw_paymentallocation;
CREATE CONSTRAINT TRIGGER trg_paymentallocation_check_sum
    AFTER INSERT OR UPDATE ON hw_paymentallocation
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION hw_paymentallocation_check_sum();

CREATE OR REPLACE FUNCTION hw_remittanceallocation_check_sum() RETURNS trigger AS $$
DECLARE
    total bigint;
    cap bigint;
BEGIN
    SELECT COALESCE(SUM(amount_sar), 0) INTO total
        FROM hw_remittanceallocation WHERE settlement_id = NEW.settlement_id;
    SELECT received_amount_sar INTO cap FROM hw_remittancesettlement WHERE id = NEW.settlement_id;
    IF cap IS NOT NULL AND total > cap THEN
        RAISE EXCEPTION 'RemittanceAllocation sum (%) exceeds RemittanceSettlement.received_amount_sar (%) for settlement_id=%',
            total, cap, NEW.settlement_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_remittanceallocation_check_sum ON hw_remittanceallocation;
CREATE CONSTRAINT TRIGGER trg_remittanceallocation_check_sum
    AFTER INSERT OR UPDATE ON hw_remittanceallocation
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION hw_remittanceallocation_check_sum();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_paymentallocation_check_sum ON hw_paymentallocation;
DROP FUNCTION IF EXISTS hw_paymentallocation_check_sum();
DROP TRIGGER IF EXISTS trg_remittanceallocation_check_sum ON hw_remittanceallocation;
DROP FUNCTION IF EXISTS hw_remittanceallocation_check_sum();
"""


def up(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PG_UP, params=None)


def down(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PG_DOWN, params=None)


class Migration(migrations.Migration):
    dependencies = [("hw", "0088_hqobligation_remittancesettlement_and_more")]
    operations = [migrations.RunPython(up, down)]
