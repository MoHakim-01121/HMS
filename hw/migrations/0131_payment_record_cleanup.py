"""Schema v2 F5c — PaymentRecord tanpa salinan dan tanpa status turunan.

* Rekening penerima wajib. Mata uang, cabang penerima, nama bank, dan nomor
  rekening dibaca dari rekening itu; kolom salinannya dihapus.
* Periode tidak disimpan: selalu periode tempat tanggal pembayaran jatuh.
* Status hanya siklus hidup (pending, confirmed, rejected, reversed, voided).
  received / allocated / partially_applied / applied adalah keadaan alokasi,
  dihitung dari baris alokasi.
* deposited_sar: bagian pembayaran yang sudah dipindah ke deposit client.
  Σ alokasi + deposited_sar tidak boleh melebihi nilai pembayaran (trigger).
* Services hanya boleh dibayar ke rekening cabang penerbit invoice-nya (B12).

Migrasi berhenti bila ada pembayaran tanpa rekening yang tidak bisa dipetakan
ke rekening bawaan cabangnya, atau yang mata uangnya berbeda dari rekeningnya.
"""
import django.db.models.deletion
from django.db import migrations, models

from hw.db_pg import pg_sql, settle_constraints

DERIVED = ('received', 'allocated', 'partially_applied', 'applied')


def normalise_payments(apps, schema_editor):
    Payment = apps.get_model('hw', 'PaymentRecord')
    Account = apps.get_model('hw', 'MoneyAccount')

    problems = []
    for p in Payment.objects.select_related('receiving_account').order_by('pk'):
        account = p.receiving_account
        if account is None:
            same = Account.objects.filter(branch_id=p.received_in, currency=p.currency, is_active=True)
            account = same.filter(kind='cash').order_by('id').first() or same.filter(kind='bank').order_by('id').first()
            if account is None:
                problems.append(f'{p.payment_number}: tidak ada rekening {p.currency} di cabang {p.received_in}')
                continue
            Payment.objects.filter(pk=p.pk).update(receiving_account_id=account.pk)
        elif account.currency != p.currency:
            problems.append(f'{p.payment_number}: {p.currency} tapi rekeningnya {account.currency}')
    if problems:
        raise RuntimeError(
            'Pembayaran berikut perlu dibereskan dulu: ' + '; '.join(problems[:40])
            + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
        )
    Payment.objects.filter(status__in=DERIVED).update(status='confirmed')
    settle_constraints(schema_editor)


PG_UP = """
-- Σ alokasi + bagian yang dipindah ke deposit tidak melebihi nilai pembayaran.
CREATE OR REPLACE FUNCTION hw_payment_check_sum(pay bigint) RETURNS void AS $$
DECLARE
    total bigint;
    cap bigint;
    moved bigint;
BEGIN
    SELECT COALESCE(SUM(amount_sar), 0) INTO total FROM hw_paymentallocation WHERE payment_id = pay;
    SELECT amount_sar, deposited_sar INTO cap, moved FROM hw_paymentrecord WHERE id = pay;
    IF cap IS NOT NULL AND total + moved > cap THEN
        RAISE EXCEPTION 'PaymentAllocation sum (%) plus deposit (%) exceeds PaymentRecord.amount_sar (%) for payment_id=%',
            total, moved, cap, pay;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION hw_paymentallocation_check_sum() RETURNS trigger AS $$
BEGIN
    PERFORM hw_payment_check_sum(NEW.payment_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION hw_paymentrecord_check_sum() RETURNS trigger AS $$
BEGIN
    PERFORM hw_payment_check_sum(NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_paymentrecord_check_sum
    AFTER UPDATE OF amount_sar, deposited_sar ON hw_paymentrecord
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION hw_paymentrecord_check_sum();

-- Alokasi: bukan ke baris denda, invoice milik client pembayaran itu, dan
-- baris service hanya dari rekening cabang penerbit invoice-nya.
CREATE OR REPLACE FUNCTION hw_paymentallocation_line_check() RETURNS trigger AS $$
DECLARE
    line_kind text;
    line_client bigint;
    line_branch text;
    pay_client bigint;
    pay_branch text;
BEGIN
    SELECT l.kind, i.client_id, i.branch_id INTO line_kind, line_client, line_branch
        FROM hw_invoiceline l JOIN hw_invoice i ON i.id = l.invoice_id WHERE l.id = NEW.invoice_line_id;
    SELECT p.client_id, a.branch_id INTO pay_client, pay_branch
        FROM hw_paymentrecord p JOIN hw_moneyaccount a ON a.id = p.receiving_account_id WHERE p.id = NEW.payment_id;
    IF line_kind = 'penalty' THEN
        RAISE EXCEPTION 'payment allocation: denda dibayar lewat baris hotel reservasinya, bukan baris denda';
    END IF;
    IF line_client <> pay_client THEN
        RAISE EXCEPTION 'payment allocation: baris invoice milik client lain dari pembayaran ini';
    END IF;
    IF line_kind = 'service' AND line_branch <> pay_branch THEN
        RAISE EXCEPTION 'payment allocation: Services hanya dibayar ke rekening cabang penerbit invoice-nya';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_paymentrecord_check_sum ON hw_paymentrecord;
DROP FUNCTION IF EXISTS hw_paymentrecord_check_sum();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0130_payment_allocation_invoice_line'),
    ]

    operations = [
        migrations.RunPython(normalise_payments, migrations.RunPython.noop),
        migrations.RemoveField(model_name='paymentrecord', name='currency'),
        migrations.RemoveField(model_name='paymentrecord', name='received_in'),
        migrations.RemoveField(model_name='paymentrecord', name='bank_name'),
        migrations.RemoveField(model_name='paymentrecord', name='account_number'),
        migrations.RemoveField(model_name='paymentrecord', name='period'),
        migrations.AlterField(
            model_name='paymentrecord', name='receiving_account',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='payments_received', to='hw.moneyaccount',
            ),
        ),
        migrations.AlterField(
            model_name='paymentrecord', name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'), ('confirmed', 'Confirmed'), ('rejected', 'Rejected'),
                    ('reversed', 'Reversed'), ('voided', 'Voided'),
                ],
                default='pending', max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='paymentrecord',
            constraint=models.CheckConstraint(
                condition=models.Q(('status__in', ['pending', 'confirmed', 'rejected', 'reversed', 'voided'])),
                name='payment_status_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='paymentrecord',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='payment_amount_positive'),
        ),
        migrations.AddConstraint(
            model_name='paymentrecord',
            constraint=models.CheckConstraint(condition=models.Q(('amount_sar__gt', 0)), name='payment_amount_sar_positive'),
        ),
        migrations.AddConstraint(
            model_name='paymentrecord',
            constraint=models.CheckConstraint(condition=models.Q(('exchange_rate__gt', 0)), name='payment_rate_positive'),
        ),
        migrations.AddField(
            model_name='paymentrecord', name='deposited_sar', field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name='paymentrecord',
            constraint=models.CheckConstraint(
                condition=models.Q(('deposited_sar__lte', models.F('amount_sar'))), name='payment_deposited_within_amount',
            ),
        ),
        migrations.AlterField(
            model_name='paymentlog', name='action',
            field=models.CharField(
                choices=[
                    ('created', 'Created'), ('received', 'Received'), ('confirmed', 'Confirmed'),
                    ('allocated', 'Allocated'), ('applied', 'Applied'), ('rejected', 'Rejected'),
                    ('updated', 'Updated'), ('reversed', 'Reversed'), ('voided', 'Voided'),
                    ('deposited', 'Moved to deposit'),
                ],
                max_length=20,
            ),
        ),
        pg_sql(PG_UP, PG_DOWN),
    ]
