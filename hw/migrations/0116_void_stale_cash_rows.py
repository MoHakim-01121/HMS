"""Void cash-book rows whose source document was reversed/voided before the
cash book followed cancellations (reverse/void now void the row directly)."""
from django.db import migrations

EFFECTIVE = ('received', 'confirmed', 'allocated', 'partially_applied', 'applied')


def void_stale(apps, schema_editor):
    BankTransaction = apps.get_model('hw', 'BankTransaction')
    PaymentRecord = apps.get_model('hw', 'PaymentRecord')
    ExpensePayment = apps.get_model('hw', 'ExpensePayment')
    dead_payments = PaymentRecord.objects.exclude(status__in=EFFECTIVE).values_list('pk', flat=True)
    dead_expense_payments = ExpensePayment.objects.filter(status='void').values_list('pk', flat=True)
    live = BankTransaction.objects.exclude(status='voided').filter(statement_lines__isnull=True)
    live.filter(source_type='PaymentRecord', source_id__in=list(dead_payments)).update(status='voided')
    live.filter(source_type='ExpensePayment', source_id__in=list(dead_expense_payments)).update(status='voided')


class Migration(migrations.Migration):
    dependencies = [('hw', '0115_backfill_payment_cash_rows')]
    operations = [migrations.RunPython(void_stale, migrations.RunPython.noop)]
