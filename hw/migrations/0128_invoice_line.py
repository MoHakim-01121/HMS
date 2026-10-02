"""Schema v2 F4 — satu tabel baris invoice, invoice tanpa salinan.

hw_reservation + hw_serviceitem  →  hw_invoiceline (kind hotel / penalty / service)
  * baris hotel menunjuk reservasi (CL) dan tidak lagi menyimpan nomor, hotel,
    tanggal, client, cabang, atau nilai: semuanya dibaca dari CL / invoice.
  * baris service dipindahkan dari hw_serviceitem dengan id baru; semua yang
    menunjuknya (pembayaran, alokasi, nota kredit, jurnal) ikut dipetakan, dan
    rantai hash jurnal dihitung ulang dari entry pertama yang terkena.
  * ConfirmationLetter.invoice dihapus: tautannya adalah baris invoice, paling
    banyak satu baris berlaku per reservasi.
Invoice: client dan cabang wajib, customer_name dihapus (dibaca dari client),
status hanya siklus hidup (draft / issued / void), nomor unik, CHECK mata uang.
InvoiceRevision: riwayat nilai tagihan; disemai satu baris per invoice.

Migrasi berhenti dengan pesan yang menyebut nomor dokumen bila ada data yang
tidak bisa dipetakan tanpa keputusan manusia (lihat
docs/superpowers/specs/2026-09-29-keputusan-data-produksi.md).
"""
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from hw.migrations import _cutover

from hw.db_pg import pg_sql, settle_constraints, user_triggers_disabled

INVOICE_TYPES = ['hotel', 'visa']
CURRENCIES = ['SAR', 'USD', 'IDR']


def _fail(title, problems):
    raise RuntimeError(
        f'{title}: ' + '; '.join(problems[:40])
        + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
    )


def _cl_value(cl):
    """Nilai tagihan sebuah CL (aturan hw.finance.reservation_rules saat migrasi ini ditulis)."""
    if (cl.reservation_status or '').upper() == 'CANCELLED':
        return 0
    nights = (cl.check_out - cl.check_in).days or 1
    total = sum((r.price * r.quantity * nights for r in cl.rooms.all()), Decimal(0))
    return int(Decimal(total).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def normalise_invoices(apps, schema_editor):
    Invoice = apps.get_model('hw', 'Invoice')
    Reservation = apps.get_model('hw', 'Reservation')
    CL = apps.get_model('hw', 'ConfirmationLetter')

    Invoice.objects.filter(invoice_type='services').update(invoice_type='visa')

    # Reservasi yang ditautkan ke invoice lewat CL.invoice tapi belum punya
    # baris: dibuatkan barisnya, supaya tautannya tidak hilang saat kolom itu dihapus.
    for cl in CL.objects.filter(invoice__isnull=False):
        if not Reservation.objects.filter(invoice_id=cl.invoice_id, confirmation_letter_id=cl.pk).exists():
            row = Reservation.objects.filter(
                invoice_id=cl.invoice_id, confirmation_letter__isnull=True,
                reservation_number=cl.confirmation_number,
            ).first()
            if row:
                Reservation.objects.filter(pk=row.pk).update(confirmation_letter_id=cl.pk)
            else:
                Reservation.objects.create(
                    invoice_id=cl.invoice_id, confirmation_letter_id=cl.pk, client_id=cl.client_id,
                    reservation_number=cl.confirmation_number, check_in=cl.check_in, check_out=cl.check_out,
                    total_sar=_cl_value(cl),
                )
    # Baris tanpa tautan CL: cocokkan lewat nomornya.
    for row in Reservation.objects.filter(confirmation_letter__isnull=True):
        cl = CL.objects.filter(confirmation_number=row.reservation_number).first()
        if cl:
            Reservation.objects.filter(pk=row.pk).update(confirmation_letter_id=cl.pk)

    problems = []
    for inv in Invoice.objects.order_by('pk'):
        updates = {}
        if inv.client_id is None:
            clients = set(
                Reservation.objects.filter(invoice_id=inv.pk, confirmation_letter__isnull=False)
                .values_list('confirmation_letter__client_id', flat=True)
            )
            if len(clients) == 1:
                updates['client_id'] = clients.pop()
            else:
                problems.append(f'{inv.invoice_number}: tanpa client')
                continue
        client_id = updates.get('client_id', inv.client_id)
        if inv.branch_id is None:
            updates['branch_id'] = apps.get_model('hw', 'Client').objects.get(pk=client_id).owner_branch_id
        if inv.invoice_type not in INVOICE_TYPES:
            problems.append(f'{inv.invoice_number}: jenis "{inv.invoice_type}"')
        currency = (inv.currency or '').strip().upper()
        if currency not in CURRENCIES or (inv.invoice_type == 'hotel' and currency != 'SAR'):
            problems.append(f'{inv.invoice_number}: mata uang "{inv.currency}"')
        elif currency != inv.currency:
            updates['currency'] = currency
        if inv.issued_date and inv.due_date and inv.due_date < inv.issued_date:
            problems.append(f'{inv.invoice_number}: jatuh tempo sebelum tanggal terbit')
        if inv.status == 'void':
            if inv.voided_at is None:
                updates['voided_at'] = inv.updated_at
        else:
            updates['status'] = 'issued'
        if updates:
            Invoice.objects.filter(pk=inv.pk).update(**updates)

    numbers = {}
    for pk, number in Invoice.objects.values_list('pk', 'invoice_number'):
        numbers.setdefault(number, []).append(pk)
    problems += [f'nomor invoice {n} dipakai {len(pks)} invoice' for n, pks in numbers.items() if len(pks) > 1]

    live = {}
    for row in Reservation.objects.select_related('invoice', 'confirmation_letter').order_by('pk'):
        inv, cl = row.invoice, row.confirmation_letter
        if cl is None:
            problems.append(f'{inv.invoice_number}: baris "{row.reservation_number}" tidak punya CL')
            continue
        if inv.status == 'void':
            continue
        if inv.client_id is not None and cl.client_id != inv.client_id:
            problems.append(f'{inv.invoice_number}: CL {cl.confirmation_number} milik client lain')
        if cl.pk in live:
            problems.append(f'CL {cl.confirmation_number} ditagih di {live[cl.pk]} dan {inv.invoice_number}')
        live[cl.pk] = inv.invoice_number
        value = _cl_value(CL.objects.prefetch_related('rooms').get(pk=cl.pk))
        if value != row.total_sar:
            problems.append(
                f'{inv.invoice_number}: CL {cl.confirmation_number} ditagih {row.total_sar:,} '
                f'tapi nilai CL sekarang {value:,}'
            )
    if problems:
        _fail('Invoice berikut perlu dibereskan dulu sebelum migrasi ini', problems)
    settle_constraints(schema_editor)


# ── Rantai hash jurnal (salinan hw.finance.hashing saat migrasi ini ditulis) ──

_ENTRY_FIELDS = (
    'entry_number', 'entry_type', 'entry_date', 'seq',
    'is_reversal', 'reverses_id', 'reference_type', 'reference_id', 'description',
)
_LINE_FIELDS = (
    'line_no', 'account_id', 'debit', 'credit', 'currency',
    'client_id', 'invoice_id', 'reservation_id', 'service_item_id',
    'penalty_id', 'remittance_id', 'note',
)


def _s(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, 'isoformat') else str(v)


def _entry_hash(entry, lines, prev_hash):
    # Selama migrasi ini service_item adalah kolom bilangan, bukan foreign key.
    def line_value(line, field):
        return getattr(line, 'service_item' if field == 'service_item_id' else field, None)
    payload = {
        'entry': {f: _s(getattr(entry, f, None)) for f in _ENTRY_FIELDS},
        'lines': [
            {f: _s(line_value(line, f)) for f in _LINE_FIELDS}
            for line in sorted(lines, key=lambda l: l.line_no or 0)
        ],
        'prev_hash': prev_hash or '',
    }
    blob = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _rechain_journal(apps, from_seq):
    JournalEntry = apps.get_model('hw', 'JournalEntry')
    prev = (
        JournalEntry.objects.filter(seq__lt=from_seq).order_by('-seq')
        .values_list('entry_hash', flat=True).first() or ''
    )
    for entry in JournalEntry.objects.filter(seq__gte=from_seq).order_by('seq').prefetch_related('lines'):
        new_hash = _entry_hash(entry, list(entry.lines.all()), prev)
        JournalEntry.objects.filter(pk=entry.pk).update(prev_hash=prev, entry_hash=new_hash)
        prev = new_hash


def merge_lines(apps, schema_editor):
    Invoice = apps.get_model('hw', 'Invoice')
    Line = apps.get_model('hw', 'InvoiceLine')
    ServiceItem = apps.get_model('hw', 'ServiceItem')
    PaymentRecord = apps.get_model('hw', 'PaymentRecord')
    PaymentAllocation = apps.get_model('hw', 'PaymentAllocation')
    JournalLine = apps.get_model('hw', 'JournalLine')
    CreditNoteLine = apps.get_model('hw', 'CreditNoteLine')
    Revision = apps.get_model('hw', 'InvoiceRevision')

    invoices = {inv.pk: inv for inv in Invoice.objects.all()}
    next_no = {}

    def take_no(invoice_id):
        next_no[invoice_id] = next_no.get(invoice_id, 0) + 1
        return next_no[invoice_id]

    snapshot = {}   # invoice_id → [rows]
    for line in Line.objects.select_related('confirmation_letter__hotel').order_by('invoice_id', 'pk'):
        inv = invoices[line.invoice_id]
        line_no = take_no(line.invoice_id)
        Line.objects.filter(pk=line.pk).update(
            line_no=line_no, kind='hotel', voided_at=inv.voided_at if inv.status == 'void' else None,
        )
        cl = line.confirmation_letter
        snapshot.setdefault(line.invoice_id, []).append({
            'line_id': line.pk, 'line_no': line_no, 'kind': 'hotel',
            'label': f'{cl.confirmation_number} · {cl.hotel.name}', 'amount': int(line.total_sar or 0),
        })

    new_id = {}
    for item in ServiceItem.objects.order_by('invoice_id', 'service_number', 'pk'):
        inv = invoices[item.invoice_id]
        line_no = take_no(item.invoice_id)
        line = Line.objects.create(
            invoice_id=item.invoice_id, kind='service', line_no=line_no,
            description=item.name or f'Service {line_no}', quantity=item.qty or 1, unit_price=item.price,
            reservation_number='', total_sar=0,
            voided_at=inv.voided_at if inv.status == 'void' else None,
        )
        new_id[item.pk] = line.pk
        snapshot.setdefault(item.invoice_id, []).append({
            'line_id': line.pk, 'line_no': line_no, 'kind': 'service',
            'label': f'#{line_no} {line.description}', 'amount': int(line.quantity * line.unit_price),
        })

    for old, new in new_id.items():
        PaymentRecord.objects.filter(service_item=old).update(service_item=-new)
        PaymentAllocation.objects.filter(service_item=old).update(service_item=-new)
    # Dua langkah (lewat nilai negatif) supaya id lama dan baru yang beririsan
    # tidak saling menimpa.
    for model in (PaymentRecord, PaymentAllocation):
        for row in model.objects.filter(service_item__lt=0):
            model.objects.filter(pk=row.pk).update(service_item=-row.service_item)

    touched = JournalLine.objects.filter(service_item__isnull=False)
    if touched.exists():
        first_seq = touched.order_by('journal_entry__seq').values_list('journal_entry__seq', flat=True).first()
        with user_triggers_disabled('hw_journalline', 'hw_journalentry', using=schema_editor.connection):
            for old, new in new_id.items():
                JournalLine.objects.filter(service_item=old).update(service_item=-new)
            for row in JournalLine.objects.filter(service_item__lt=0):
                JournalLine.objects.filter(pk=row.pk).update(service_item=-row.service_item)
            if first_seq is not None:
                _rechain_journal(apps, first_seq)

    for cn_line in CreditNoteLine.objects.all():
        target = cn_line.reservation_id or new_id.get(cn_line.service_item_id)
        if target is None:
            raise RuntimeError(f'Baris nota kredit {cn_line.pk} tidak menunjuk baris invoice mana pun.')
        CreditNoteLine.objects.filter(pk=cn_line.pk).update(invoice_line_id=target)

    credited = {}
    for cn_line in CreditNoteLine.objects.filter(credit_note__status='active').select_related('credit_note'):
        inv_id = cn_line.credit_note.invoice_id
        credited[inv_id] = credited.get(inv_id, 0) + cn_line.amount_sar
    for invoice_id, rows in snapshot.items():
        inv = invoices[invoice_id]
        void = inv.status == 'void'
        Revision.objects.create(
            invoice_id=invoice_id, revision_no=1,
            total=0 if void else sum(r['amount'] for r in rows) - credited.get(invoice_id, 0),
            reason='void' if void else 'issue', lines_snapshot=rows, changed_by_id=inv.created_by_id,
        )
    settle_constraints(schema_editor)


PG_UP = """
ALTER TABLE hw_invoice
    ADD CONSTRAINT invoice_currency_fk FOREIGN KEY (currency) REFERENCES hw_currency (code)
    DEFERRABLE INITIALLY DEFERRED;

-- Baris hotel/penalty hanya di invoice hotel, baris service hanya di invoice
-- services, dan reservasi yang ditagih harus milik client invoice itu.
CREATE OR REPLACE FUNCTION hw_invoiceline_check() RETURNS trigger AS $$
DECLARE
    inv hw_invoice%ROWTYPE;
    cl_client bigint;
BEGIN
    SELECT * INTO inv FROM hw_invoice WHERE id = NEW.invoice_id;
    IF NEW.kind IN ('hotel', 'penalty') AND inv.invoice_type <> 'hotel' THEN
        RAISE EXCEPTION 'invoice line: baris % hanya boleh di invoice hotel (invoice %)', NEW.kind, inv.invoice_number;
    END IF;
    IF NEW.kind = 'service' AND inv.invoice_type = 'hotel' THEN
        RAISE EXCEPTION 'invoice line: baris service tidak boleh di invoice hotel (invoice %)', inv.invoice_number;
    END IF;
    IF NEW.kind = 'hotel' THEN
        SELECT client_id INTO cl_client FROM hw_confirmationletter WHERE id = NEW.confirmation_letter_id;
        IF cl_client <> inv.client_id THEN
            RAISE EXCEPTION 'invoice line: reservasi milik client lain dari invoice %', inv.invoice_number;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoiceline_check
    BEFORE INSERT OR UPDATE OF invoice_id, kind, confirmation_letter_id ON hw_invoiceline
    FOR EACH ROW EXECUTE FUNCTION hw_invoiceline_check();

-- Client sebuah invoice / reservasi tidak boleh diganti selagi keduanya
-- terhubung lewat baris invoice yang berlaku.
CREATE OR REPLACE FUNCTION hw_invoice_client_check() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM hw_invoiceline l JOIN hw_confirmationletter c ON c.id = l.confirmation_letter_id
        WHERE l.invoice_id = NEW.id AND l.kind = 'hotel' AND l.voided_at IS NULL AND c.client_id <> NEW.client_id
    ) THEN
        RAISE EXCEPTION 'invoice %: masih menagih reservasi milik client lain', NEW.invoice_number;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoice_client_check
    BEFORE UPDATE OF client_id ON hw_invoice
    FOR EACH ROW EXECUTE FUNCTION hw_invoice_client_check();

CREATE OR REPLACE FUNCTION hw_cl_client_check() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM hw_invoiceline l JOIN hw_invoice i ON i.id = l.invoice_id
        WHERE l.confirmation_letter_id = NEW.id AND l.kind = 'hotel' AND l.voided_at IS NULL
          AND i.client_id <> NEW.client_id
    ) THEN
        RAISE EXCEPTION 'reservasi %: sudah ditagih di invoice client lain', NEW.confirmation_number;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cl_client_check
    BEFORE UPDATE OF client_id ON hw_confirmationletter
    FOR EACH ROW EXECUTE FUNCTION hw_cl_client_check();

-- Riwayat revisi invoice hanya bertambah.
CREATE OR REPLACE FUNCTION hw_invoicerevision_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'invoice revision append-only: % ditolak', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoicerevision_append_only
    BEFORE UPDATE OR DELETE ON hw_invoicerevision
    FOR EACH ROW EXECUTE FUNCTION hw_invoicerevision_block_mutation();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_invoicerevision_append_only ON hw_invoicerevision;
DROP FUNCTION IF EXISTS hw_invoicerevision_block_mutation();
DROP TRIGGER IF EXISTS trg_cl_client_check ON hw_confirmationletter;
DROP FUNCTION IF EXISTS hw_cl_client_check();
DROP TRIGGER IF EXISTS trg_invoice_client_check ON hw_invoice;
DROP FUNCTION IF EXISTS hw_invoice_client_check();
DROP TRIGGER IF EXISTS trg_invoiceline_check ON hw_invoiceline;
DROP FUNCTION IF EXISTS hw_invoiceline_check();
ALTER TABLE hw_invoice DROP CONSTRAINT IF EXISTS invoice_currency_fk;
"""


def _line_fk(to):
    return models.ForeignKey(
        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=to,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0127_penalty_sar_attachment_parent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Keputusan data produksi (F11), lihat hw/migrations/_cutover.py.
        migrations.RunPython(_cutover.step(_cutover.fix_due_dates), migrations.RunPython.noop),
        migrations.RunPython(normalise_invoices, migrations.RunPython.noop),

        # ── hw_reservation → hw_invoiceline ───────────────────────────────
        migrations.RenameModel(old_name='Reservation', new_name='InvoiceLine'),
        migrations.AlterModelOptions(
            name='invoiceline',
            options={'ordering': ['invoice_id', 'line_no'], 'verbose_name': 'Invoice Line', 'verbose_name_plural': 'Invoice Lines'},
        ),
        migrations.AlterField(
            model_name='invoiceline', name='invoice',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lines', to='hw.invoice'),
        ),
        migrations.AddField(
            model_name='invoiceline', name='kind',
            field=models.CharField(
                choices=[('hotel', 'Hotel reservation'), ('penalty', 'Cancellation penalty'), ('service', 'Service')],
                default='hotel', max_length=8,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='invoiceline', name='line_no',
            field=models.PositiveSmallIntegerField(default=0), preserve_default=False,
        ),
        migrations.AddField(
            model_name='invoiceline', name='description',
            field=models.CharField(blank=True, default='', max_length=255), preserve_default=False,
        ),
        migrations.AddField(
            model_name='invoiceline', name='quantity',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='invoiceline', name='unit_price',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='invoiceline', name='penalty',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='invoice_lines', to='hw.cancellationpenalty',
            ),
        ),
        migrations.AddField(
            model_name='invoiceline', name='voided_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        migrations.CreateModel(
            name='InvoiceRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision_no', models.PositiveIntegerField()),
                ('total', models.BigIntegerField()),
                ('reason', models.CharField(
                    choices=[
                        ('issue', 'Issued'), ('cl_change', 'Reservation changed'), ('line_change', 'Lines changed'),
                        ('credit_note', 'Credit note'), ('void', 'Voided'),
                    ], max_length=12,
                )),
                ('lines_snapshot', models.JSONField(default=list)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name='revisions', to='hw.invoice',
                )),
            ],
            options={
                'verbose_name': 'Invoice Revision', 'verbose_name_plural': 'Invoice Revisions',
                'ordering': ['invoice_id', 'revision_no'],
                'constraints': [
                    models.UniqueConstraint(fields=('invoice', 'revision_no'), name='invoice_revision_no_uniq'),
                    models.CheckConstraint(
                        condition=models.Q(('reason__in', ['issue', 'cl_change', 'line_change', 'credit_note', 'void'])),
                        name='invoice_revision_reason_valid',
                    ),
                ],
            },
        ),

        # Lepas foreign key ke hw_serviceitem supaya id-nya bisa dipetakan.
        migrations.AlterField(
            model_name='paymentrecord', name='service_item',
            field=models.IntegerField(blank=True, null=True, db_column='service_item_id'),
        ),
        migrations.AlterField(
            model_name='paymentallocation', name='service_item',
            field=models.IntegerField(blank=True, null=True, db_column='service_item_id'),
        ),
        migrations.AlterField(
            model_name='journalline', name='service_item',
            field=models.IntegerField(blank=True, null=True, db_column='service_item_id'),
        ),
        migrations.AddField(
            model_name='creditnoteline', name='invoice_line',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='credit_note_lines', to='hw.invoiceline',
            ),
        ),

        migrations.RunPython(merge_lines, migrations.RunPython.noop),

        # ── Buang salinan dari baris invoice ──────────────────────────────
        migrations.RemoveConstraint(model_name='invoiceline', name='reservation_check_out_after_check_in'),
        migrations.RemoveField(model_name='invoiceline', name='owner_branch'),
        migrations.RemoveField(model_name='invoiceline', name='client'),
        migrations.RemoveField(model_name='invoiceline', name='reservation_number'),
        migrations.RemoveField(model_name='invoiceline', name='hotel'),
        migrations.RemoveField(model_name='invoiceline', name='check_in'),
        migrations.RemoveField(model_name='invoiceline', name='check_out'),
        migrations.RemoveField(model_name='invoiceline', name='total_sar'),
        migrations.AlterField(
            model_name='invoiceline', name='confirmation_letter',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='invoice_lines', to='hw.confirmationletter',
            ),
        ),
        migrations.AlterField(
            model_name='invoiceline', name='line_no', field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterField(
            model_name='invoiceline', name='description', field=models.CharField(blank=True, max_length=255),
        ),

        migrations.RemoveConstraint(model_name='creditnoteline', name='cn_line_one_target'),
        migrations.RemoveField(model_name='creditnoteline', name='reservation'),
        migrations.RemoveField(model_name='creditnoteline', name='service_item'),
        migrations.AlterField(
            model_name='creditnoteline', name='invoice_line',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='credit_note_lines', to='hw.invoiceline',
            ),
        ),

        migrations.DeleteModel(name='ServiceItem'),
        migrations.CreateModel(
            name='Reservation', fields=[],
            options={'verbose_name': 'Hotel Line', 'verbose_name_plural': 'Hotel Lines', 'proxy': True, 'indexes': [], 'constraints': []},
            bases=('hw.invoiceline',),
        ),
        migrations.CreateModel(
            name='ServiceItem', fields=[],
            options={'verbose_name': 'Service Line', 'verbose_name_plural': 'Service Lines', 'proxy': True, 'indexes': [], 'constraints': []},
            bases=('hw.invoiceline',),
        ),
        migrations.AlterField(model_name='paymentrecord', name='service_item', field=_line_fk('hw.serviceitem')),
        migrations.AlterField(model_name='paymentallocation', name='service_item', field=_line_fk('hw.serviceitem')),
        migrations.AlterField(model_name='journalline', name='service_item', field=_line_fk('hw.serviceitem')),
        migrations.AlterField(model_name='paymentrecord', name='reservation', field=_line_fk('hw.reservation')),
        migrations.AlterField(model_name='paymentallocation', name='reservation', field=_line_fk('hw.reservation')),
        migrations.AlterField(model_name='journalline', name='reservation', field=_line_fk('hw.reservation')),

        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.UniqueConstraint(fields=('invoice', 'line_no'), name='invoice_line_no_uniq'),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.CheckConstraint(
                condition=models.Q(('kind__in', ['hotel', 'penalty', 'service'])), name='invoice_line_kind_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        kind='hotel', confirmation_letter__isnull=False, penalty__isnull=True,
                        description='', quantity__isnull=True, unit_price__isnull=True,
                    )
                    | models.Q(
                        kind='penalty', penalty__isnull=False, confirmation_letter__isnull=True,
                        description='', quantity__isnull=True, unit_price__isnull=True,
                    )
                    | (
                        models.Q(
                            kind='service', confirmation_letter__isnull=True, penalty__isnull=True,
                            quantity__isnull=False, unit_price__isnull=False,
                        )
                        & ~models.Q(description='')
                    )
                ),
                name='invoice_line_shape_per_kind',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.CheckConstraint(
                condition=models.Q(('quantity__isnull', True), ('quantity__gt', 0), _connector='OR'),
                name='invoice_line_quantity_positive',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.UniqueConstraint(
                condition=models.Q(voided_at__isnull=True, kind='hotel'), fields=('confirmation_letter',),
                name='invoice_line_one_live_per_reservation',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.UniqueConstraint(
                condition=models.Q(voided_at__isnull=True, kind='penalty'), fields=('penalty',),
                name='invoice_line_one_live_per_penalty',
            ),
        ),

        # ── Reservasi tidak lagi menyimpan invoice-nya ────────────────────
        migrations.RemoveField(model_name='confirmationletter', name='invoice'),

        # ── Invoice ───────────────────────────────────────────────────────
        migrations.RemoveConstraint(model_name='invoice', name='uniq_invoice_number_per_type'),
        migrations.RemoveField(model_name='invoice', name='customer_name'),
        migrations.AlterField(
            model_name='invoice', name='invoice_number', field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name='invoice', name='client',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='hw.client'),
        ),
        migrations.AlterField(
            model_name='invoice', name='branch',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='hw.branch'),
        ),
        migrations.AlterField(
            model_name='invoice', name='currency', field=models.CharField(default='SAR', max_length=3),
        ),
        migrations.AlterField(
            model_name='invoice', name='status',
            field=models.CharField(
                choices=[('draft', 'Draft'), ('issued', 'Issued'), ('void', 'Void')], default='issued', max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(('invoice_type__in', INVOICE_TYPES)), name='invoice_type_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(('status__in', ['draft', 'issued', 'void'])), name='invoice_status_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(('currency__in', CURRENCIES)), name='invoice_currency_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=~models.Q(invoice_type='hotel') | models.Q(currency='SAR'), name='invoice_hotel_is_sar',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(issued_date__isnull=True) | models.Q(due_date__isnull=True)
                    | models.Q(due_date__gte=models.F('issued_date'))
                ),
                name='invoice_due_not_before_issued',
            ),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=~models.Q(status='void') | models.Q(voided_at__isnull=False),
                name='invoice_void_has_timestamp',
            ),
        ),
        pg_sql(PG_UP, PG_DOWN),
    ]
