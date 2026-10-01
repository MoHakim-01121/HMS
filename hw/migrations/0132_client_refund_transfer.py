"""Schema v2 F5d — refund dan transfer deposit client menjadi dokumen bernomor.

Sebelumnya keduanya hanya entry jurnal. Migrasi berhenti bila database sudah
punya entry refund (perlu dipetakan ke rekening asalnya oleh orang).
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def require_no_journal_refunds(apps, schema_editor):
    JournalEntry = apps.get_model('hw', 'JournalEntry')
    numbers = list(JournalEntry.objects.filter(entry_type='refund').values_list('entry_number', flat=True)[:40])
    if numbers:
        raise RuntimeError(
            'Refund berikut tercatat sebagai jurnal saja dan perlu dibuatkan dokumen ClientRefund '
            'secara manual (rekening asal tidak tersimpan): ' + ', '.join(numbers)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0131_payment_record_cleanup'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(require_no_journal_refunds, migrations.RunPython.noop),
        migrations.CreateModel(
            name='ClientRefund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('refund_number', models.CharField(max_length=30, unique=True)),
                ('refund_date', models.DateField()),
                ('amount_sar', models.PositiveIntegerField()),
                ('amount_paid', models.PositiveIntegerField()),
                ('note', models.TextField(blank=True)),
                ('proof', models.FileField(blank=True, null=True, upload_to='refunds/proof/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='refunds', to='hw.client')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('journal_entry', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.journalentry')),
                ('money_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='client_refunds', to='hw.moneyaccount')),
            ],
            options={
                'verbose_name': 'Client Refund', 'verbose_name_plural': 'Client Refunds',
                'ordering': ['-refund_date', '-pk'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('amount_sar__gt', 0)), name='client_refund_amount_positive'),
                    models.CheckConstraint(condition=models.Q(('amount_paid__gt', 0)), name='client_refund_paid_positive'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ClientTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transfer_number', models.CharField(max_length=30, unique=True)),
                ('transfer_date', models.DateField()),
                ('amount_sar', models.PositiveIntegerField()),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('from_client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deposit_transfers_out', to='hw.client')),
                ('journal_entry', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.journalentry')),
                ('to_client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deposit_transfers_in', to='hw.client')),
            ],
            options={
                'verbose_name': 'Client Deposit Transfer', 'verbose_name_plural': 'Client Deposit Transfers',
                'ordering': ['-transfer_date', '-pk'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('amount_sar__gt', 0)), name='client_transfer_amount_positive'),
                    models.CheckConstraint(condition=~models.Q(('from_client', models.F('to_client'))), name='client_transfer_two_clients'),
                ],
            },
        ),
    ]
