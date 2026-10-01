"""Schema v2 F6 — setoran cabang ke Pusat dengan satu jalur.

Remittance: rekening asal dan rekening SAR Pusat penerima wajib; amount_idr →
amount_sent (mata uang rekening asal); kurs rencana wajib; status dan nominal
diterima manual (jalur lama) dihapus — status dihitung dari penerimaan.

RemittanceLine (alokasi): selalu milik satu penerimaan, dan menunjuk baris
hotel invoice reservasinya, bukan nomor CL sebagai teks. Kolom remittance dan
invoice dihapus (dibaca dari penerimaan dan baris invoice).

Data jalur lama dipetakan: nominal diterima manual menjadi satu penerimaan,
dan baris yang dialokasikan saat kirim menempel ke penerimaan itu. Migrasi
berhenti dengan nomor RMT bila ada transfer yang tidak bisa dipetakan.
"""
import django.db.models.deletion
from django.db import migrations, models

from hw.db_pg import settle_constraints


def map_legacy(apps, schema_editor):
    Remittance = apps.get_model('hw', 'Remittance')
    Settlement = apps.get_model('hw', 'RemittanceSettlement')
    Line = apps.get_model('hw', 'RemittanceLine')
    InvoiceLine = apps.get_model('hw', 'InvoiceLine')
    Account = apps.get_model('hw', 'MoneyAccount')
    JournalEntry = apps.get_model('hw', 'JournalEntry')
    JournalLine = apps.get_model('hw', 'JournalLine')

    hq_sar = (
        Account.objects.filter(branch_id='pusat', currency='SAR', is_active=True, kind='cash').order_by('id').first()
        or Account.objects.filter(branch_id='pusat', currency='SAR', is_active=True).order_by('id').first()
    )
    problems = []
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
    legacy_receive = set(
        JournalLine.objects.filter(
            journal_entry__reference_type='Remittance', journal_entry__is_reversal=False,
            account_id='1000-KAS-PUSAT', debit__gt=0,
        ).exclude(journal_entry_id__in=reversed_ids).values_list('journal_entry__reference_id', flat=True)
    )
    for rem in Remittance.objects.order_by('pk'):
        if rem.from_account_id is None:
            problems.append(f'{rem.remittance_number}: tanpa rekening asal')
        if not rem.amount_idr or not rem.exchange_rate:
            problems.append(f'{rem.remittance_number}: tanpa nominal kirim / kurs')
        if rem.pk in legacy_receive:
            problems.append(f'{rem.remittance_number}: penerimaan tercatat di jurnal kirim (jalur lama)')
        if hq_sar is None:
            problems.append('Pusat belum punya rekening SAR')
            break
        Remittance.objects.filter(pk=rem.pk).update(to_account_id=hq_sar.pk)

        settlements = list(Settlement.objects.filter(remittance_id=rem.pk).order_by('received_date', 'pk'))
        if rem.received_amount_sar and not settlements:
            settlements = [Settlement.objects.create(
                remittance_id=rem.pk, received_amount_sar=rem.received_amount_sar,
                received_date=rem.date, reference=rem.receipt_reference,
                note='Dipindahkan dari nominal diterima manual (jalur lama)',
            )]
        loose = Line.objects.filter(remittance_id=rem.pk, settlement__isnull=True)
        if loose.exists():
            if len(settlements) == 1:
                loose.update(settlement_id=settlements[0].pk)
            else:
                problems.append(f'{rem.remittance_number}: baris alokasi tanpa penerimaan yang jelas')

    for line in Line.objects.order_by('pk'):
        candidates = InvoiceLine.objects.filter(
            kind='hotel', confirmation_letter__confirmation_number=line.linked_number,
        )
        if line.invoice_id:
            candidates = candidates.filter(invoice_id=line.invoice_id)
        target = candidates.filter(voided_at__isnull=True).first() or candidates.order_by('-voided_at').first()
        if target is None:
            problems.append(f'alokasi {line.pk} ({line.linked_number}): tidak ada baris invoice reservasinya')
            continue
        Line.objects.filter(pk=line.pk).update(invoice_line_id=target.pk)

    if problems:
        raise RuntimeError(
            'Setoran berikut perlu dibereskan dulu: ' + '; '.join(problems[:40])
            + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
        )
    settle_constraints(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0132_client_refund_transfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='remittance', name='to_account',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='remittances_received', to='hw.moneyaccount',
            ),
        ),
        migrations.AddField(
            model_name='remittanceline', name='invoice_line',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='remittance_allocations', to='hw.invoiceline',
            ),
        ),
        migrations.RunPython(map_legacy, migrations.RunPython.noop),

        migrations.RenameField(model_name='remittance', old_name='amount_idr', new_name='amount_sent'),
        migrations.RemoveField(model_name='remittance', name='received_amount_sar'),
        migrations.RemoveField(model_name='remittance', name='status'),
        migrations.AlterField(
            model_name='remittance', name='amount_sent', field=models.BigIntegerField(),
        ),
        migrations.AlterField(
            model_name='remittance', name='exchange_rate', field=models.DecimalField(decimal_places=4, max_digits=14),
        ),
        migrations.AlterField(
            model_name='remittance', name='from_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='remittances_sent', to='hw.moneyaccount'),
        ),
        migrations.AlterField(
            model_name='remittance', name='to_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='remittances_received', to='hw.moneyaccount'),
        ),
        migrations.AddConstraint(
            model_name='remittance',
            constraint=models.CheckConstraint(condition=models.Q(('amount_sent__gt', 0)), name='remittance_amount_positive'),
        ),
        migrations.AddConstraint(
            model_name='remittance',
            constraint=models.CheckConstraint(condition=models.Q(('exchange_rate__gt', 0)), name='remittance_rate_positive'),
        ),
        migrations.AddConstraint(
            model_name='remittance',
            constraint=models.CheckConstraint(
                condition=~models.Q(('from_account', models.F('to_account'))), name='remittance_two_accounts',
            ),
        ),

        migrations.RemoveField(model_name='remittanceline', name='remittance'),
        migrations.RemoveField(model_name='remittanceline', name='invoice'),
        migrations.RemoveField(model_name='remittanceline', name='linked_number'),
        migrations.AlterField(
            model_name='remittanceline', name='settlement',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='hw.remittancesettlement'),
        ),
        migrations.AlterField(
            model_name='remittanceline', name='invoice_line',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='remittance_allocations', to='hw.invoiceline'),
        ),
        migrations.AlterField(
            model_name='remittanceline', name='amount_sar', field=models.PositiveIntegerField(),
        ),
        migrations.AddConstraint(
            model_name='remittanceline',
            constraint=models.CheckConstraint(condition=models.Q(('amount_sar__gt', 0)), name='remittance_line_amount_positive'),
        ),
        migrations.AlterModelOptions(
            name='remittanceline',
            options={'verbose_name': 'Remittance Allocation', 'verbose_name_plural': 'Remittance Allocations'},
        ),
    ]
