"""Move payments recorded into an account of another currency (IDR payments
auto-assigned the SAR branch cash account) to the branch's account in the
payment's own currency, together with their cash-book rows. Rows already
matched to a bank statement are left alone. The SAR journal is unaffected:
the accounts share the branch cash ledger."""
from django.db import migrations


def _target(CashAccount, BankAccount, branch_id, currency):
    cash = CashAccount.objects.filter(branch_id=branch_id, currency=currency, is_active=True).order_by('id').first()
    if cash:
        return None, cash.pk
    bank = BankAccount.objects.filter(branch_id=branch_id, currency=currency, is_active=True).order_by('id').first()
    return (bank.pk, None) if bank else None


def fix(apps, schema_editor):
    CashAccount = apps.get_model('hw', 'CashAccount')
    BankAccount = apps.get_model('hw', 'BankAccount')
    BankTransaction = apps.get_model('hw', 'BankTransaction')
    for model_name, source_type in (('PaymentRecord', 'PaymentRecord'), ('ExpensePayment', 'ExpensePayment')):
        Model = apps.get_model('hw', model_name)
        for obj in Model.objects.select_related('bank_account', 'cash_account'):
            account = obj.bank_account or obj.cash_account
            if account is None or account.currency == obj.currency:
                continue
            target = _target(CashAccount, BankAccount, account.branch_id, obj.currency)
            if target is None:
                continue
            rows = BankTransaction.objects.filter(source_type=source_type, source_id=obj.pk)
            if rows.filter(statement_lines__isnull=False).exists():
                continue
            bank_id, cash_id = target
            Model.objects.filter(pk=obj.pk).update(bank_account_id=bank_id, cash_account_id=cash_id)
            rows.update(bank_account_id=bank_id, cash_account_id=cash_id)


class Migration(migrations.Migration):
    dependencies = [('hw', '0116_void_stale_cash_rows')]
    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
