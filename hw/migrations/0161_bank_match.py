"""Reconciliation by match group: a statement line and a cash-book row each
point at a BankMatch, so one line can be many rows and the other way round.
An existing one-to-one match becomes a match of its own."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def to_matches(apps, schema_editor):
    Line = apps.get_model('hw', 'BankStatementLine')
    Match = apps.get_model('hw', 'BankMatch')
    Tx = apps.get_model('hw', 'BankTransaction')
    by_tx = {}
    for line in Line.objects.filter(matched_transaction__isnull=False).select_related('statement').order_by('pk'):
        m = by_tx.get(line.matched_transaction_id)
        if m is None:
            m = by_tx[line.matched_transaction_id] = Match.objects.create(account_id=line.statement.account_id)
            Tx.objects.filter(pk=line.matched_transaction_id).update(match=m)
        Line.objects.filter(pk=line.pk).update(match=m)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0160_invoice_down_payment_percent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BankMatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.moneyaccount')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Bank Match', 'verbose_name_plural': 'Bank Matches'},
        ),
        migrations.AddField(
            model_name='bankstatementline', name='match',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lines', to='hw.bankmatch'),
        ),
        migrations.AddField(
            model_name='banktransaction', name='match',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='hw.bankmatch'),
        ),
        migrations.RunPython(to_matches, migrations.RunPython.noop),
        migrations.RemoveField(model_name='bankstatementline', name='matched_transaction'),
    ]
