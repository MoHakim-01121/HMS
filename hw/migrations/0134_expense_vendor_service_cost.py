"""Schema v2 F7 — beban cabang tanpa salinan, vendor sebagai master, biaya vendor Services.

* Expense.vendor: teks → FK ke Vendor (dibuat dari nama-nama yang ada).
* Expense: total_amount / total_amount_sar dan periode dihapus (dihitung dari
  baris dan tanggal); status hanya siklus hidup (draft / posted / voided).
* ExpenseLine.service_line: biaya vendor untuk satu baris Services (B13).
* ExpensePayment.currency dihapus (mata uang rekening pembayarnya).
* Akun "Biaya Vendor Services" dan kategori SVC-VENDOR.
"""
import django.db.models.deletion
from django.db import migrations, models

from hw.db_pg import settle_constraints
from hw.models.client import client_name_key

CURRENCIES = ['SAR', 'USD', 'IDR']


def normalise(apps, schema_editor):
    Expense = apps.get_model('hw', 'Expense')
    Vendor = apps.get_model('hw', 'Vendor')
    Payment = apps.get_model('hw', 'ExpensePayment')
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    Category = apps.get_model('hw', 'ExpenseCategory')

    problems = []
    for e in Expense.objects.order_by('pk'):
        updates = {}
        name = (e.vendor or '').strip()
        if name:
            key = client_name_key(name)
            vendor = Vendor.objects.filter(name_key=key).first() or Vendor.objects.create(name=name, name_key=key)
            updates['vendor_ref_id'] = vendor.pk
        if e.status in ('partially_paid', 'paid'):
            updates['status'] = 'posted'
        if (e.currency or '').upper() not in CURRENCIES:
            problems.append(f'{e.expense_number}: mata uang "{e.currency}"')
        if updates:
            Expense.objects.filter(pk=e.pk).update(**updates)
    for p in Payment.objects.select_related('source_account', 'expense'):
        if p.currency != p.source_account.currency:
            problems.append(f'{p.expense.expense_number}: pembayaran {p.currency} dari rekening {p.source_account.currency}')
    if problems:
        raise RuntimeError('Beban berikut perlu dibereskan dulu: ' + '; '.join(problems[:40]))

    account, _ = LedgerAccount.objects.get_or_create(
        code='5500-EXP-SVC-VENDOR',
        defaults={'name': 'Biaya Vendor Services', 'type': 'expense', 'normal_balance': 'debit',
                  'is_postable': True, 'is_active': True},
    )
    Category.objects.get_or_create(
        code='SVC-VENDOR', defaults={'name': 'Biaya vendor Services', 'ledger_account': account},
    )
    settle_constraints(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0133_remittance_single_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense', name='vendor_ref',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='expenses', to='hw.vendor',
            ),
        ),
        migrations.RunPython(normalise, migrations.RunPython.noop),
        migrations.RemoveField(model_name='expense', name='vendor'),
        migrations.RenameField(model_name='expense', old_name='vendor_ref', new_name='vendor'),
        migrations.RemoveField(model_name='expense', name='total_amount'),
        migrations.RemoveField(model_name='expense', name='total_amount_sar'),
        migrations.RemoveField(model_name='expense', name='period'),
        migrations.AlterField(
            model_name='expense', name='currency', field=models.CharField(default='SAR', max_length=3),
        ),
        migrations.AlterField(
            model_name='expense', name='status',
            field=models.CharField(
                choices=[('draft', 'Draft'), ('posted', 'Posted'), ('voided', 'Voided')],
                db_index=True, default='draft', max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='expense',
            constraint=models.CheckConstraint(
                condition=models.Q(('status__in', ['draft', 'posted', 'voided'])), name='expense_status_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='expense',
            constraint=models.CheckConstraint(condition=models.Q(('currency__in', CURRENCIES)), name='expense_currency_valid'),
        ),
        migrations.AddField(
            model_name='expenseline', name='service_line',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='vendor_costs', to='hw.invoiceline',
            ),
        ),
        migrations.AlterField(model_name='expenseline', name='amount', field=models.PositiveIntegerField()),
        migrations.AlterField(model_name='expenseline', name='amount_sar', field=models.PositiveIntegerField()),
        migrations.AddConstraint(
            model_name='expenseline',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='expense_line_amount_positive'),
        ),
        migrations.RemoveField(model_name='expensepayment', name='currency'),
        migrations.AddConstraint(
            model_name='expensepayment',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='expense_payment_amount_positive'),
        ),
    ]
