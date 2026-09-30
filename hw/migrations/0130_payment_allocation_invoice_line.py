"""Schema v2 F5b — alokasi pembayaran menunjuk satu baris invoice.

PaymentAllocation: tiga kolom tujuan (reservation, service_item, penalty)
diganti satu kolom `invoice_line` (PROTECT). Denda tidak lagi jadi tujuan
sendiri: uangnya dialokasikan ke baris hotel reservasinya.

PaymentRecord: tautan langsung ke satu reservasi / service dihapus. Pembayaran
yang memakainya (tanpa baris alokasi) dibuatkan satu alokasi penuh.

Di PostgreSQL, trigger menolak alokasi ke baris denda dan ke invoice milik
client lain.
"""
import django.db.models.deletion
from django.db import migrations, models

from hw.db_pg import pg_sql, settle_constraints

DEAD = ('rejected', 'reversed', 'voided')


def move_targets(apps, schema_editor):
    Allocation = apps.get_model('hw', 'PaymentAllocation')
    Payment = apps.get_model('hw', 'PaymentRecord')
    Line = apps.get_model('hw', 'InvoiceLine')

    problems = []
    for alloc in Allocation.objects.select_related('payment').order_by('pk'):
        target = alloc.reservation_id or alloc.service_item_id
        if target is None and alloc.penalty_id:
            # Uang denda → baris hotel reservasi yang didenda, di invoice yang menagihnya.
            pen_line = Line.objects.filter(kind='penalty', penalty_id=alloc.penalty_id).order_by('voided_at').last()
            hotel = Line.objects.filter(
                kind='hotel', invoice_id=pen_line.invoice_id, confirmation_letter_id=pen_line.penalty.cl_id,
            ).order_by('voided_at').last() if pen_line else None
            target = hotel.pk if hotel else None
        if target is None:
            problems.append(f'{alloc.payment.payment_number}: alokasi {alloc.amount_sar:,} tanpa tujuan')
            continue
        Allocation.objects.filter(pk=alloc.pk).update(invoice_line_id=target)

    for payment in Payment.objects.exclude(status__in=DEAD).order_by('pk'):
        target = payment.reservation_id or payment.service_item_id
        if target is None or Allocation.objects.filter(payment_id=payment.pk).exists():
            continue
        Allocation.objects.create(payment_id=payment.pk, invoice_line_id=target, amount_sar=payment.amount_sar)

    if problems:
        raise RuntimeError(
            'Alokasi pembayaran berikut tidak punya baris invoice: ' + '; '.join(problems[:40])
            + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
        )
    settle_constraints(schema_editor)


PG_UP = """
CREATE OR REPLACE FUNCTION hw_paymentallocation_line_check() RETURNS trigger AS $$
DECLARE
    line_kind text;
    line_client bigint;
    pay_client bigint;
BEGIN
    SELECT l.kind, i.client_id INTO line_kind, line_client
        FROM hw_invoiceline l JOIN hw_invoice i ON i.id = l.invoice_id WHERE l.id = NEW.invoice_line_id;
    SELECT client_id INTO pay_client FROM hw_paymentrecord WHERE id = NEW.payment_id;
    IF line_kind = 'penalty' THEN
        RAISE EXCEPTION 'payment allocation: denda dibayar lewat baris hotel reservasinya, bukan baris denda';
    END IF;
    IF line_client <> pay_client THEN
        RAISE EXCEPTION 'payment allocation: baris invoice milik client lain dari pembayaran ini';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_paymentallocation_line_check
    BEFORE INSERT OR UPDATE OF invoice_line_id, payment_id ON hw_paymentallocation
    FOR EACH ROW EXECUTE FUNCTION hw_paymentallocation_line_check();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_paymentallocation_line_check ON hw_paymentallocation;
DROP FUNCTION IF EXISTS hw_paymentallocation_line_check();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0129_penalty_billed_on_invoice'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentallocation', name='invoice_line',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='payment_allocations', to='hw.invoiceline',
            ),
        ),
        migrations.RunPython(move_targets, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='paymentallocation', name='paymentallocation_exactly_one_target'),
        migrations.RemoveField(model_name='paymentallocation', name='reservation'),
        migrations.RemoveField(model_name='paymentallocation', name='service_item'),
        migrations.RemoveField(model_name='paymentallocation', name='penalty'),
        migrations.AlterField(
            model_name='paymentallocation', name='invoice_line',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payment_allocations', to='hw.invoiceline',
            ),
        ),
        migrations.RemoveField(model_name='paymentrecord', name='reservation'),
        migrations.RemoveField(model_name='paymentrecord', name='service_item'),
        pg_sql(PG_UP, PG_DOWN),
    ]
