"""Schema v2 F8b — satu akun buku besar satu mata uang (T4).

Rekening rupiah/dolar cabang tidak lagi berbagi akun kas cabang (SAR) tetapi
memakai akun anaknya, 1000-KAS-<CABANG>-<MATA UANG>. Baris jurnal kas yang
sudah ada dipindah ke akun rekening sumbernya (pembayaran, beban, transfer,
penerimaan, refund; pembalik mengikuti entry yang dibaliknya), lalu rantai
hash dihitung ulang. Di PostgreSQL trigger menolak rekening yang mata uangnya
beda dengan rekening lain di akun buku besar yang sama.
"""
import hashlib
import json
from decimal import Decimal

from django.db import migrations

from hw.db_pg import pg_sql, settle_constraints, user_triggers_disabled


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


def split_cash(apps, schema_editor):
    Ledger = apps.get_model('hw', 'LedgerAccount')
    Money = apps.get_model('hw', 'MoneyAccount')
    Entry = apps.get_model('hw', 'JournalEntry')
    Line = apps.get_model('hw', 'JournalLine')
    Payment = apps.get_model('hw', 'PaymentRecord')
    ExpensePayment = apps.get_model('hw', 'ExpensePayment')
    Remittance = apps.get_model('hw', 'Remittance')
    Settlement = apps.get_model('hw', 'RemittanceSettlement')
    Refund = apps.get_model('hw', 'ClientRefund')

    problems = []
    moved = {}  # money account id → new ledger code
    for acc in Money.objects.exclude(currency='SAR').select_related('ledger_account'):
        ledger = acc.ledger_account
        others = set(Money.objects.filter(ledger_account_id=ledger.code).values_list('currency', flat=True))
        if others == {acc.currency}:
            continue  # already alone on its ledger account
        if not (ledger.code.startswith('1000-KAS-') and ledger.parent_id is None):
            problems.append(f'rekening {acc.pk} ({acc.currency}) berbagi akun {ledger.code} dengan mata uang lain')
            continue
        code = f'{ledger.code}-{acc.currency}'
        Ledger.objects.get_or_create(code=code, defaults={
            'name': f'{ledger.name} {acc.currency}', 'type': ledger.type, 'normal_balance': ledger.normal_balance,
            'parent_id': ledger.code, 'is_postable': True, 'is_active': True,
        })
        moved[acc.pk] = (ledger.code, code)
    if problems:
        raise RuntimeError('Rekening berikut perlu dibereskan sebelum migrasi 0137: ' + '; '.join(problems))
    if not moved:
        return

    roots = {old for old, _ in moved.values()}
    money_of = {
        'source_payment': dict(Payment.objects.values_list('pk', 'receiving_account_id')),
        'source_expense_payment': dict(ExpensePayment.objects.values_list('pk', 'source_account_id')),
        'source_client_refund': dict(Refund.objects.values_list('pk', 'money_account_id')),
    }
    remit_from = dict(Remittance.objects.values_list('pk', 'from_account_id'))
    remit_to = dict(Remittance.objects.values_list('pk', 'to_account_id'))
    settle_rem = dict(Settlement._base_manager.values_list('pk', 'remittance_id'))  # yang dibatalkan juga

    def target(entry, line):
        """Rekening (money account id) yang digerakkan baris kas ini."""
        if entry.source_remittance_id:
            return remit_from[entry.source_remittance_id]
        if entry.source_remittance_settlement_id:
            rem = settle_rem[entry.source_remittance_settlement_id]
            return remit_to[rem] if entry.entry_type == 'remittance' else remit_from[rem]
        for field, mapping in money_of.items():
            sid = getattr(entry, f'{field}_id')
            if sid:
                return mapping[sid]
        return None

    new_account = {}  # line pk → code
    entries = {e.pk: e for e in Entry.objects.all()}
    lines = list(Line.objects.filter(account_id__in=roots).order_by('journal_entry__seq', 'pk'))
    for ln in lines:
        e = entries[ln.journal_entry_id]
        if e.reverses_id:
            continue
        acc = target(e, ln)
        if acc is None:
            problems.append(f'{e.entry_number} baris {ln.line_no}: rekening tidak diketahui')
        elif acc in moved and moved[acc][0] == ln.account_id:
            new_account[ln.pk] = moved[acc][1]
    by_entry_line = {(l.journal_entry_id, l.line_no): l.pk for l in lines}
    for ln in lines:
        e = entries[ln.journal_entry_id]
        if e.reverses_id:
            orig = by_entry_line.get((e.reverses_id, ln.line_no))
            if orig in new_account:
                new_account[ln.pk] = new_account[orig]
    if problems:
        raise RuntimeError('Jurnal kas berikut perlu dibereskan sebelum migrasi 0137: ' + '; '.join(problems[:40]))

    tables = ('hw_journalentry', 'hw_journalline')
    with user_triggers_disabled(*tables, using=schema_editor.connection):
        for pk, code in new_account.items():
            Line.objects.filter(pk=pk).update(account_id=code)
        for acc_id, (_, code) in moved.items():
            Money.objects.filter(pk=acc_id).update(ledger_account_id=code)
        prev = ''
        for entry in Entry.objects.filter(seq__isnull=False).order_by('seq').prefetch_related('lines'):
            new_hash = _entry_hash(entry, list(entry.lines.all()), prev)
            if new_hash != entry.entry_hash or prev != entry.prev_hash:
                Entry.objects.filter(pk=entry.pk).update(prev_hash=prev, entry_hash=new_hash)
            prev = new_hash
    settle_constraints(schema_editor)


PG_UP = """
CREATE OR REPLACE FUNCTION hw_moneyaccount_ledger_currency() RETURNS trigger AS $$
DECLARE
    other text;
BEGIN
    SELECT currency INTO other FROM hw_moneyaccount
     WHERE ledger_account_id = NEW.ledger_account_id AND currency <> NEW.currency AND id <> NEW.id
     LIMIT 1;
    IF other IS NOT NULL THEN
        RAISE EXCEPTION 'akun buku besar % sudah dipakai rekening %; satu akun satu mata uang',
            NEW.ledger_account_id, other USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_moneyaccount_ledger_currency ON hw_moneyaccount;
CREATE TRIGGER trg_moneyaccount_ledger_currency
    BEFORE INSERT OR UPDATE OF ledger_account_id, currency ON hw_moneyaccount
    FOR EACH ROW EXECUTE FUNCTION hw_moneyaccount_ledger_currency();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_moneyaccount_ledger_currency ON hw_moneyaccount;
DROP FUNCTION IF EXISTS hw_moneyaccount_ledger_currency();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0136_access_and_audit'),
    ]

    operations = [
        migrations.RunPython(split_cash, migrations.RunPython.noop),
        pg_sql(PG_UP, PG_DOWN),
    ]
