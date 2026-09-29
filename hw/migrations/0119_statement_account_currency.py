"""Bank statements in the account's own currency.

Statements used to be typed in SAR, while the cash book now holds each
account's real amounts (0110). Rename the *_sar fields, record the account's
currency on the statement, and carry existing data over: a SAR account's
figures are already right; for a foreign-currency account the line amounts
are taken from the matched cash-book row where there is one (its real
amount), and the rest is left as typed and flagged in the note for review.
"""
from django.db import migrations, models


def forwards(apps, schema_editor):
    BankStatement = apps.get_model('hw', 'BankStatement')
    for st in BankStatement.objects.select_related('bank_account', 'cash_account'):
        account = st.bank_account or st.cash_account
        currency = getattr(account, 'currency', None) or 'SAR'
        st.currency = currency
        fields = ['currency']
        if currency != 'SAR':
            unconverted = 0
            for line in st.lines.select_related('matched_transaction'):
                tx = line.matched_transaction
                if tx is not None and tx.amount:
                    line.amount = tx.amount
                    line.save(update_fields=['amount'])
                else:
                    unconverted += 1
            st.note = (st.note + '\n' if st.note else '') + (
                f'[0119] Entered in SAR before statements used the account currency ({currency}). '
                f'Check the opening/closing balance{" and " + str(unconverted) + " unmatched line(s)" if unconverted else ""}.'
            )
            fields.append('note')
        st.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0118_credit_note_and_invoice_void'),
    ]

    operations = [
        migrations.RenameField('bankstatement', 'opening_balance_sar', 'opening_balance'),
        migrations.RenameField('bankstatement', 'closing_balance_sar', 'closing_balance'),
        migrations.RenameField('bankstatementline', 'amount_sar', 'amount'),
        migrations.AlterField('bankstatement', 'opening_balance', models.BigIntegerField()),
        migrations.AlterField('bankstatement', 'closing_balance', models.BigIntegerField()),
        migrations.AlterField('bankstatementline', 'amount', models.PositiveBigIntegerField()),
        migrations.AddField('bankstatement', 'currency', models.CharField(default='SAR', max_length=3)),
        migrations.AddField('bankstatement', 'source_filename', models.CharField(blank=True, max_length=255)),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
