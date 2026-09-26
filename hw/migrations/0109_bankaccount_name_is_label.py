from django.db import migrations


def strip_doubled_name(apps, schema_editor):
    """Accounts created from the Bank Balances form stored name as
    "<bank_name> <currency>", which str(BankAccount) — "<bank_name> <name>
    (<currency>)" — then printed twice. Make name the account's own label
    (its number), matching what the form now saves."""
    BankAccount = apps.get_model('hw', 'BankAccount')
    for acc in BankAccount.objects.exclude(account_identifier=''):
        if acc.name == f'{acc.bank_name} {acc.currency}':
            BankAccount.objects.filter(pk=acc.pk).update(name=acc.account_identifier)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0108_invoice_branch_bank_show_on_invoice'),
    ]

    operations = [
        migrations.RunPython(strip_doubled_name, migrations.RunPython.noop),
    ]
