"""Cash-book rows for effective payments recorded before the cash book
(BankTransaction) existed, so the fund-flow report sees all money received.
Idempotent: skips payments that already have a row."""
from django.db import migrations

EFFECTIVE = ('received', 'confirmed', 'allocated', 'partially_applied', 'applied')


def backfill(apps, schema_editor):
    PaymentRecord = apps.get_model('hw', 'PaymentRecord')
    BankTransaction = apps.get_model('hw', 'BankTransaction')
    have = set(BankTransaction.objects.filter(source_type='PaymentRecord').values_list('source_id', flat=True))
    rows = []
    for p in PaymentRecord.objects.filter(status__in=EFFECTIVE).exclude(pk__in=have):
        if not (p.bank_account_id or p.cash_account_id):
            continue
        rows.append(BankTransaction(
            bank_account_id=p.bank_account_id, cash_account_id=p.cash_account_id,
            transaction_date=p.payment_date, direction='in', amount_sar=p.amount_sar,
            currency=p.currency, amount=p.amount, source_type='PaymentRecord', source_id=p.pk,
            reference=(p.reference or '')[:200], status='posted',
        ))
    BankTransaction.objects.bulk_create(rows)


class Migration(migrations.Migration):
    dependencies = [('hw', '0114_money_account_opening_balance')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
