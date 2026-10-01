"""Schema v2 F8 — buku besar: sumber jurnal bertipe, satu dimensi baris invoice.

* JournalEntry.reference_type / reference_id (teks + id bebas) diganti satu FK
  per jenis dokumen sumber (`source_*`); paling banyak satu terisi, entry
  pembalik hanya menunjuk `reverses` (unik: dibalik paling banyak sekali).
  `is_reversal` dan `reversed_by` (kolom) dihapus — turunan dari `reverses`.
  Selisih penerimaan transfer dan alokasi penerimaan Pusat mendapat jenis
  entry sendiri (`remittance_diff`, `allocate`) karena sumbernya dokumen yang
  sama dengan entry penerimaan.
* ClientRefund / ClientTransfer tidak lagi menunjuk entry-nya; entry yang
  menunjuk dokumennya (`source_client_refund` / `source_client_transfer`).
* JournalLine.reservation + service_item (keduanya baris invoice sejak F4)
  menjadi satu `invoice_line`. orig_amount → amount_txn; orig_currency dihapus
  (`currency` = mata uang transaksi).
* Rantai hash dihitung ulang dengan isi kanonik baru.
"""
import hashlib
import json
from decimal import Decimal

import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models

from hw.db_pg import pg_sql, settle_constraints, user_triggers_disabled

SOURCES = {
    'Invoice': 'source_invoice',
    'CreditNote': 'source_credit_note',
    'PaymentRecord': 'source_payment',
    'Remittance': 'source_remittance',
    'RemittanceSettlement': 'source_remittance_settlement',
    'Expense': 'source_expense',
    'ExpensePayment': 'source_expense_payment',
}
# reference_type lama → (kolom sumber, jenis entry baru)
ALIASES = {
    'RemittanceDiff': ('source_remittance', 'remittance_diff'),
    'RemittanceAllocation': ('source_remittance_settlement', 'allocate'),
}
SOURCE_MODELS = {
    'source_invoice': 'Invoice',
    'source_credit_note': 'CreditNote',
    'source_payment': 'PaymentRecord',
    'source_remittance': 'Remittance',
    'source_remittance_settlement': 'RemittanceSettlement',
    'source_expense': 'Expense',
    'source_expense_payment': 'ExpensePayment',
}


# ── Rantai hash jurnal (salinan hw.finance.hashing saat migrasi ini ditulis) ──

_ENTRY_FIELDS = (
    'entry_number', 'entry_type', 'entry_date', 'seq', 'reverses_id',
    'source_invoice_id', 'source_credit_note_id', 'source_payment_id',
    'source_remittance_id', 'source_remittance_settlement_id', 'source_expense_id',
    'source_expense_payment_id', 'source_client_refund_id', 'source_client_transfer_id',
    'description',
)
_LINE_FIELDS = (
    'line_no', 'account_id', 'debit', 'credit', 'currency', 'amount_txn', 'fx_rate',
    'client_id', 'invoice_id', 'invoice_line_id', 'penalty_id', 'remittance_id', 'note',
)


def _s(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return f'{v:.8f}'
    return v.isoformat() if hasattr(v, 'isoformat') else str(v)


def _entry_hash(entry, lines, prev_hash):
    payload = {
        'entry': {f: _s(getattr(entry, f, None)) for f in _ENTRY_FIELDS},
        'lines': [
            {f: _s(getattr(line, f, None)) for f in _LINE_FIELDS}
            for line in sorted(lines, key=lambda l: l.line_no or 0)
        ],
        'prev_hash': prev_hash or '',
    }
    blob = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _fail(problems):
    raise RuntimeError(
        'Jurnal berikut perlu dibereskan sebelum migrasi 0135: ' + '; '.join(problems[:40])
    )


def move_sources(apps, schema_editor):
    Entry = apps.get_model('hw', 'JournalEntry')
    Line = apps.get_model('hw', 'JournalLine')
    Refund = apps.get_model('hw', 'ClientRefund')
    Transfer = apps.get_model('hw', 'ClientTransfer')

    existing = {
        field: set(apps.get_model('hw', model).objects.values_list('pk', flat=True))
        for field, model in SOURCE_MODELS.items()
    }
    refund_of = dict(Refund.objects.values_list('journal_entry_id', 'pk'))
    transfer_of = dict(Transfer.objects.values_list('journal_entry_id', 'pk'))

    problems = []
    updates = {}
    for e in Entry.objects.order_by('pk'):
        ref, ref_id = e.reference_type or '', e.reference_id
        change = {}
        if e.reverses_id is not None:
            if ref not in ('', 'JournalEntry') or (ref == 'JournalEntry' and ref_id != e.reverses_id):
                problems.append(f'{e.entry_number}: pembalik dengan sumber {ref}#{ref_id}')
        elif e.is_reversal:
            problems.append(f'{e.entry_number}: bertanda pembalik tanpa entry yang dibalik')
        elif ref in SOURCES or ref in ALIASES:
            field, entry_type = (SOURCES[ref], None) if ref in SOURCES else ALIASES[ref]
            if ref_id not in existing[field]:
                problems.append(f'{e.entry_number}: sumber {ref}#{ref_id} tidak ada')
            change[f'{field}_id'] = ref_id
            if entry_type:
                change['entry_type'] = entry_type
        elif ref == '':
            if e.pk in refund_of:
                change['source_client_refund_id'] = refund_of[e.pk]
            elif e.pk in transfer_of:
                change['source_client_transfer_id'] = transfer_of[e.pk]
        else:
            problems.append(f'{e.entry_number}: sumber tak dikenal {ref}#{ref_id}')
        if change:
            updates[e.pk] = change

    line_updates = {}
    for ln in Line.objects.order_by('pk'):
        change = {}
        if ln.reservation_id and ln.service_item_id:
            problems.append(f'baris jurnal {ln.pk}: reservasi dan service sekaligus')
        line_id = ln.reservation_id or ln.service_item_id
        if line_id:
            change['invoice_line_id'] = line_id
        if ln.penalty_id and not line_id:
            problems.append(f'baris jurnal {ln.pk}: denda tanpa baris reservasi')
        if ln.orig_amount is not None:
            if ln.orig_amount <= 0:
                problems.append(f'baris jurnal {ln.pk}: nominal asli {ln.orig_amount}')
            change['amount_txn'] = ln.orig_amount
        if ln.orig_currency and ln.orig_currency != ln.currency:
            change['currency'] = ln.orig_currency
        if change:
            line_updates[ln.pk] = change

    if problems:
        _fail(problems)

    tables = ('hw_journalentry', 'hw_journalline')
    with user_triggers_disabled(*tables, using=schema_editor.connection):
        for pk, change in updates.items():
            Entry.objects.filter(pk=pk).update(**change)
        for pk, change in line_updates.items():
            Line.objects.filter(pk=pk).update(**change)
    settle_constraints(schema_editor)


def rechain(apps, schema_editor):
    Entry = apps.get_model('hw', 'JournalEntry')
    prev = ''
    with user_triggers_disabled('hw_journalentry', using=schema_editor.connection):
        for entry in Entry.objects.filter(seq__isnull=False).order_by('seq').prefetch_related('lines'):
            new_hash = _entry_hash(entry, list(entry.lines.all()), prev)
            Entry.objects.filter(pk=entry.pk).update(prev_hash=prev, entry_hash=new_hash)
            prev = new_hash
    settle_constraints(schema_editor)


PG_UP = """
CREATE OR REPLACE FUNCTION hw_journalline_dims_check() RETURNS trigger AS $$
DECLARE
    line_invoice bigint;
BEGIN
    IF NEW.invoice_line_id IS NOT NULL THEN
        SELECT invoice_id INTO line_invoice FROM hw_invoiceline WHERE id = NEW.invoice_line_id;
        IF NEW.invoice_id IS DISTINCT FROM line_invoice THEN
            RAISE EXCEPTION 'baris jurnal: baris invoice % bukan milik invoice %',
                NEW.invoice_line_id, NEW.invoice_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_journalline_dims_check ON hw_journalline;
CREATE TRIGGER trg_journalline_dims_check
    BEFORE INSERT ON hw_journalline
    FOR EACH ROW EXECUTE FUNCTION hw_journalline_dims_check();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_journalline_dims_check ON hw_journalline;
DROP FUNCTION IF EXISTS hw_journalline_dims_check();
"""


def _source_fk(to, one_to_one=False):
    cls = models.OneToOneField if one_to_one else models.ForeignKey
    return cls(
        blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=to,
    )


def _one_source():
    cols = (
        'source_invoice', 'source_credit_note', 'source_payment', 'source_remittance',
        'source_remittance_settlement', 'source_expense', 'source_expense_payment',
        'source_client_refund', 'source_client_transfer', 'reverses',
    )
    condition = models.Q(**{f'{c}__isnull': True for c in cols})
    for c in cols:
        condition |= models.Q(**{f'{c}__isnull': False}) & models.Q(**{f'{o}__isnull': True for o in cols if o != c})
    return condition


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0134_expense_vendor_service_cost'),
    ]

    operations = [
        migrations.AddField(model_name='journalentry', name='source_invoice', field=_source_fk('hw.invoice')),
        migrations.AddField(model_name='journalentry', name='source_credit_note', field=_source_fk('hw.creditnote')),
        migrations.AddField(model_name='journalentry', name='source_payment', field=_source_fk('hw.paymentrecord')),
        migrations.AddField(model_name='journalentry', name='source_remittance', field=_source_fk('hw.remittance')),
        migrations.AddField(
            model_name='journalentry', name='source_remittance_settlement', field=_source_fk('hw.remittancesettlement'),
        ),
        migrations.AddField(model_name='journalentry', name='source_expense', field=_source_fk('hw.expense')),
        migrations.AddField(model_name='journalentry', name='source_expense_payment', field=_source_fk('hw.expensepayment')),
        migrations.AddField(
            model_name='journalentry', name='source_client_refund', field=_source_fk('hw.clientrefund', one_to_one=True),
        ),
        migrations.AddField(
            model_name='journalentry', name='source_client_transfer',
            field=_source_fk('hw.clienttransfer', one_to_one=True),
        ),
        migrations.AddField(
            model_name='journalline', name='invoice_line',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.invoiceline',
            ),
        ),
        migrations.AddField(model_name='journalline', name='amount_txn', field=models.BigIntegerField(blank=True, null=True)),
        migrations.RunPython(move_sources, migrations.RunPython.noop),

        # Kolom lama.
        migrations.RemoveConstraint(model_name='journalentry', name='journal_entry_ref_requires_id'),
        migrations.RemoveField(model_name='journalentry', name='reference_type'),
        migrations.RemoveField(model_name='journalentry', name='reference_id'),
        migrations.RemoveField(model_name='journalentry', name='is_reversal'),
        migrations.RemoveField(model_name='journalentry', name='reversed_by'),
        migrations.RemoveField(model_name='clientrefund', name='journal_entry'),
        migrations.RemoveField(model_name='clienttransfer', name='journal_entry'),
        migrations.RemoveIndex(model_name='journalline', name='journal_res_acct_idx'),
        migrations.RemoveField(model_name='journalline', name='reservation'),
        migrations.RemoveField(model_name='journalline', name='service_item'),
        migrations.RemoveField(model_name='journalline', name='orig_amount'),
        migrations.RemoveField(model_name='journalline', name='orig_currency'),

        # Bentuk akhir.
        migrations.AlterField(
            model_name='journalentry', name='entry_type',
            field=models.CharField(choices=[
                ('charge', 'Charge'), ('payment', 'Payment'), ('allocate', 'Allocation'), ('transfer', 'Transfer'),
                ('refund', 'Refund'), ('penalty', 'Penalty'), ('remittance', 'Remittance'), ('expense', 'Expense'),
                ('reversal', 'Reversal'), ('adjustment', 'Adjustment'), ('credit_note', 'Credit note'),
                ('remittance_diff', 'Remittance difference'),
            ], max_length=20),
        ),
        migrations.AlterField(
            model_name='journalentry', name='reverses',
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reversed_by',
                to='hw.journalentry',
            ),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_invoice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.invoice'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_credit_note',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.creditnote'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_payment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.paymentrecord'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_remittance',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.remittance'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_remittance_settlement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.remittancesettlement'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_expense',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.expense'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_expense_payment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='journal_entries', to='hw.expensepayment'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_client_refund',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                       related_name='journal_entry', to='hw.clientrefund'),
        ),
        migrations.AlterField(
            model_name='journalentry', name='source_client_transfer',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                       related_name='journal_entry', to='hw.clienttransfer'),
        ),
        migrations.AlterField(
            model_name='journalline', name='penalty',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='+', to='hw.cancellationpenalty'),
        ),
        migrations.AlterField(
            model_name='journalline', name='remittance',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='+', to='hw.remittance'),
        ),
        migrations.AddIndex(
            model_name='journalline',
            index=models.Index(fields=['invoice_line', 'account'], name='journal_line_acct_idx'),
        ),
        migrations.RunPython(rechain, migrations.RunPython.noop),
        migrations.AddField(
            model_name='remittancesettlement', name='voided_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelManagers(
            name='remittancesettlement',
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('all_objects', django.db.models.manager.Manager()),
            ],
        ),
        migrations.AlterModelOptions(
            name='remittancesettlement',
            options={'base_manager_name': 'all_objects', 'ordering': ['received_date', 'id'],
                     'verbose_name': 'Remittance Settlement', 'verbose_name_plural': 'Remittance Settlements'},
        ),
        migrations.AddConstraint(
            model_name='journalentry',
            constraint=models.CheckConstraint(condition=_one_source(), name='journal_entry_one_source'),
        ),
        migrations.AddConstraint(
            model_name='journalentry',
            constraint=models.CheckConstraint(condition=models.Q(entry_type__in=[
                'charge', 'payment', 'allocate', 'transfer', 'refund', 'penalty', 'remittance',
                'expense', 'reversal', 'adjustment', 'credit_note', 'remittance_diff',
            ]), name='journal_entry_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='journalline',
            constraint=models.CheckConstraint(
                condition=models.Q(amount_txn__isnull=True) | models.Q(amount_txn__gt=0),
                name='journal_line_amount_txn_positive',
            ),
        ),
        migrations.AddConstraint(
            model_name='journalline',
            constraint=models.CheckConstraint(
                condition=models.Q(currency__in=['SAR', 'USD', 'IDR']), name='journal_line_currency_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='journalline',
            constraint=models.CheckConstraint(
                condition=models.Q(penalty__isnull=True) | models.Q(invoice_line__isnull=False),
                name='journal_line_penalty_on_line',
            ),
        ),
        pg_sql(PG_UP, PG_DOWN),
    ]
