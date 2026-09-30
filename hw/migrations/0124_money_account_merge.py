"""Schema v2 F2c — BankAccount + CashAccount menjadi satu tabel MoneyAccount.

Urutan:
1. Lepas constraint/index yang menyebut pasangan kolom lama.
2. BankAccount → MoneyAccount (tabel diganti nama; baris bank tetap ber-id sama).
3. Kolom FK bank_account → nama barunya (account / receiving_account / …).
4. Data: setiap baris CashAccount disalin ke MoneyAccount(kind='cash') dengan id
   baru; semua rujukan cash_account diarahkan ke id baru itu. Baris buku kas
   "opening balance" memakai satu source_type ('OpeningBalance').
5. Kolom cash_account dan tabel CashAccount dihapus.

Tidak bisa dibalik: id kas lama tidak disimpan.
"""
import django.db.models.deletion
from django.db import migrations, models

# (model, kolom kas lama, kolom FK baru)
CASH_LINKS = [
    ('BankTransaction', 'cash_account', 'account'),
    ('BankStatement', 'cash_account', 'account'),
    ('PaymentRecord', 'cash_account', 'receiving_account'),
    ('ExpensePayment', 'cash_account', 'source_account'),
    ('CurrencyExchange', 'from_cash_account', 'from_account'),
    ('CurrencyExchange', 'to_cash_account', 'to_account'),
]


def merge_cash_accounts(apps, schema_editor):
    MoneyAccount = apps.get_model('hw', 'MoneyAccount')
    CashAccount = apps.get_model('hw', 'CashAccount')
    BankTransaction = apps.get_model('hw', 'BankTransaction')

    new_id = {}
    for cash in CashAccount.objects.order_by('pk'):
        money = MoneyAccount.objects.create(
            kind='cash', branch_id=cash.branch_id, name=cash.name, currency=cash.currency,
            ledger_account_id=cash.ledger_account_id, is_active=cash.is_active, note=cash.note,
            opening_balance=cash.opening_balance, opening_date=cash.opening_date,
            bank_name='', account_name='', account_identifier='', show_on_invoice=False,
        )
        MoneyAccount.objects.filter(pk=money.pk).update(created_at=cash.created_at, updated_at=cash.updated_at)
        new_id[cash.pk] = money.pk

    for model_name, cash_field, new_field in CASH_LINKS:
        model = apps.get_model('hw', model_name)
        for old, new in new_id.items():
            model.objects.filter(**{f'{cash_field}_id': old}).update(**{f'{new_field}_id': new})

    # Buku kas "saldo awal": satu source_type untuk semua akun. Bank dulu (id
    # tidak berubah), baru kas (id baru) — urutan ini menjaga UNIQUE
    # (source_type, source_id) tetap terpenuhi di setiap langkah.
    BankTransaction.objects.filter(source_type='OpeningBalanceBank').update(source_type='OpeningBalance')
    for old, new in new_id.items():
        BankTransaction.objects.filter(source_type='OpeningBalanceCash', source_id=old).update(
            source_type='OpeningBalance', source_id=new,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0123_hotel_constraints_vendor'),
    ]

    operations = [
        # 1 ─ constraint & index lama
        migrations.RemoveConstraint(model_name='bankaccount', name='uniq_bankaccount_bank_number_currency'),
        migrations.RemoveConstraint(model_name='banktransaction', name='banktransaction_exactly_one_account'),
        migrations.RemoveIndex(model_name='banktransaction', name='banktx_bank_date_idx'),
        migrations.RemoveIndex(model_name='banktransaction', name='banktx_cash_date_idx'),
        migrations.RemoveConstraint(model_name='bankstatement', name='bankstatement_exactly_one_account'),
        migrations.RemoveConstraint(model_name='currencyexchange', name='fx_exactly_one_from_account'),
        migrations.RemoveConstraint(model_name='currencyexchange', name='fx_exactly_one_to_account'),
        migrations.RemoveConstraint(model_name='paymentrecord', name='paymentrecord_one_receiving_account'),
        migrations.RemoveConstraint(model_name='expensepayment', name='expensepayment_exactly_one_account'),

        # 2 ─ tabel gabungan
        migrations.RenameModel(old_name='BankAccount', new_name='MoneyAccount'),
        migrations.AddField(
            model_name='moneyaccount', name='kind',
            field=models.CharField(choices=[('bank', 'Bank'), ('cash', 'Cash')], default='bank', max_length=4),
        ),
        migrations.AlterField(
            model_name='moneyaccount', name='bank_name',
            field=models.CharField(blank=True, max_length=120),
        ),

        # 3 ─ satu FK per tabel
        migrations.RenameField(model_name='banktransaction', old_name='bank_account', new_name='account'),
        migrations.RenameField(model_name='bankstatement', old_name='bank_account', new_name='account'),
        migrations.RenameField(model_name='currencyexchange', old_name='from_bank_account', new_name='from_account'),
        migrations.RenameField(model_name='currencyexchange', old_name='to_bank_account', new_name='to_account'),
        migrations.RenameField(model_name='paymentrecord', old_name='bank_account', new_name='receiving_account'),
        migrations.RenameField(model_name='expensepayment', old_name='bank_account', new_name='source_account'),
        migrations.RenameField(model_name='remittance', old_name='from_bank_account', new_name='from_account'),

        # 4 ─ pindahkan kas
        migrations.RunPython(merge_cash_accounts),

        # 5 ─ buang kolom & tabel kas
        migrations.RemoveField(model_name='banktransaction', name='cash_account'),
        migrations.RemoveField(model_name='bankstatement', name='cash_account'),
        migrations.RemoveField(model_name='currencyexchange', name='from_cash_account'),
        migrations.RemoveField(model_name='currencyexchange', name='to_cash_account'),
        migrations.RemoveField(model_name='paymentrecord', name='cash_account'),
        migrations.RemoveField(model_name='expensepayment', name='cash_account'),
        migrations.DeleteModel(name='CashAccount'),

        # 6 ─ FK wajib. Tidak ada baris NULL: CHECK "tepat satu akun" yang lama
        # menjamin salah satu dari pasangan selalu terisi, dan langkah 4 sudah
        # memindahkan sisi kasnya.
        migrations.AlterField(
            model_name='banktransaction', name='account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='hw.moneyaccount'),
        ),
        migrations.AlterField(
            model_name='bankstatement', name='account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='statements', to='hw.moneyaccount'),
        ),
        migrations.AlterField(
            model_name='currencyexchange', name='from_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.moneyaccount'),
        ),
        migrations.AlterField(
            model_name='currencyexchange', name='to_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.moneyaccount'),
        ),
        migrations.AlterField(
            model_name='expensepayment', name='source_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='expense_payments', to='hw.moneyaccount'),
        ),
    ]
