"""Remove the Services (visa) feature: its invoice type, the service line
kind and its columns, the expense line's link to a service line, the
"Biaya vendor Services" category and the two accounts only Services used,
and the 'services' module from every role.

Financial records are never deleted here. If the database still holds any
Services invoice, service line, vendor-cost link or journal line on those
accounts, the migration stops and names what it found.
"""
from django.conf import settings
from django.db import migrations, models

from hw.db_pg import pg_sql

INC_SERVICE = '4200-INC-SVC'
EXP_SVC_VENDOR = '5500-EXP-SVC-VENDOR'
SVC_VENDOR_CATEGORY = 'SVC-VENDOR'


# The two line checks lose their Services branches; the old bodies are the
# reverse.
INVOICELINE_CHECK = """
CREATE OR REPLACE FUNCTION hw_invoiceline_check() RETURNS trigger AS $$
DECLARE
    inv hw_invoice%ROWTYPE;
    cl_client bigint;
BEGIN
    SELECT * INTO inv FROM hw_invoice WHERE id = NEW.invoice_id;
    IF inv.invoice_type <> 'hotel' THEN
        RAISE EXCEPTION 'invoice line: baris % hanya boleh di invoice hotel (invoice %)', NEW.kind, inv.invoice_number;
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
"""

INVOICELINE_CHECK_OLD = """
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
"""

ALLOCATION_CHECK = """
CREATE OR REPLACE FUNCTION hw_paymentallocation_line_check() RETURNS trigger AS $$
DECLARE
    line_kind text;
    line_client bigint;
    pay_client bigint;
BEGIN
    SELECT l.kind, i.client_id INTO line_kind, line_client
        FROM hw_invoiceline l JOIN hw_invoice i ON i.id = l.invoice_id WHERE l.id = NEW.invoice_line_id;
    SELECT client_id INTO pay_client FROM hw_paymentrecord WHERE id = NEW.payment_id;
    IF line_kind = 'penalty' THEN
        RAISE EXCEPTION 'payment allocation: denda dibayar lewat baris hotel reservasinya, bukan baris denda';
    END IF;
    IF line_client <> pay_client THEN
        RAISE EXCEPTION 'payment allocation: baris invoice milik client lain dari pembayaran ini';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

ALLOCATION_CHECK_OLD = """
CREATE OR REPLACE FUNCTION hw_paymentallocation_line_check() RETURNS trigger AS $$
DECLARE
    line_kind text;
    line_client bigint;
    line_branch text;
    pay_client bigint;
    pay_branch text;
BEGIN
    SELECT l.kind, i.client_id, i.branch_id INTO line_kind, line_client, line_branch
        FROM hw_invoiceline l JOIN hw_invoice i ON i.id = l.invoice_id WHERE l.id = NEW.invoice_line_id;
    SELECT p.client_id, a.branch_id INTO pay_client, pay_branch
        FROM hw_paymentrecord p JOIN hw_moneyaccount a ON a.id = p.receiving_account_id WHERE p.id = NEW.payment_id;
    IF line_kind = 'penalty' THEN
        RAISE EXCEPTION 'payment allocation: denda dibayar lewat baris hotel reservasinya, bukan baris denda';
    END IF;
    IF line_client <> pay_client THEN
        RAISE EXCEPTION 'payment allocation: baris invoice milik client lain dari pembayaran ini';
    END IF;
    IF line_kind = 'service' AND line_branch <> pay_branch THEN
        RAISE EXCEPTION 'payment allocation: Services hanya dibayar ke rekening cabang penerbit invoice-nya';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def remove_services_data(apps, schema_editor):
    Invoice = apps.get_model('hw', 'Invoice')
    InvoiceLine = apps.get_model('hw', 'InvoiceLine')
    ExpenseLine = apps.get_model('hw', 'ExpenseLine')
    ExpenseCategory = apps.get_model('hw', 'ExpenseCategory')
    LedgerAccount = apps.get_model('hw', 'LedgerAccount')
    JournalLine = apps.get_model('hw', 'JournalLine')
    BankAccount = apps.get_model('hw', 'BankAccount')
    RoleDefinition = apps.get_model('hw', 'RoleDefinition')

    accounts = [INC_SERVICE, EXP_SVC_VENDOR]
    found = {
        'Services invoices': Invoice.objects.filter(invoice_type='visa').count(),
        'service lines': InvoiceLine.objects.filter(kind='service').count(),
        'expense lines linked to a service line': ExpenseLine.objects.filter(service_line__isnull=False).count(),
        f'expense lines in category {SVC_VENDOR_CATEGORY}': ExpenseLine.objects.filter(category_id=SVC_VENDOR_CATEGORY).count(),
        'expense lines on the Services accounts': ExpenseLine.objects.filter(ledger_account_id__in=accounts).count(),
        'journal lines on the Services accounts': JournalLine.objects.filter(account_id__in=accounts).count(),
        'bank accounts on the Services accounts': BankAccount.objects.filter(ledger_account_id__in=accounts).count(),
        'other expense categories on the Services accounts': ExpenseCategory.objects.filter(
            ledger_account_id__in=accounts).exclude(code=SVC_VENDOR_CATEGORY).count(),
    }
    blocking = {k: n for k, n in found.items() if n}
    if blocking:
        raise RuntimeError(
            'Services cannot be removed while the database still holds its records: '
            + ', '.join(f'{n} {k}' for k, n in blocking.items())
            + '. Void or move them first; this migration never deletes financial records.'
        )

    ExpenseCategory.objects.filter(code=SVC_VENDOR_CATEGORY).delete()
    LedgerAccount.objects.filter(code__in=accounts).delete()
    for role in RoleDefinition.objects.all():
        if 'services' in (role.permissions or {}):
            perms = dict(role.permissions)
            perms.pop('services')
            role.permissions = perms
            role.save(update_fields=['permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0149_hotel_has_allotment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(remove_services_data, migrations.RunPython.noop),
        pg_sql(INVOICELINE_CHECK, INVOICELINE_CHECK_OLD),
        pg_sql(ALLOCATION_CHECK, ALLOCATION_CHECK_OLD),
        migrations.DeleteModel(
            name='ServiceItem',
        ),
        migrations.RemoveConstraint(
            model_name='invoice',
            name='invoice_type_valid',
        ),
        migrations.RemoveConstraint(
            model_name='invoiceline',
            name='invoice_line_kind_valid',
        ),
        migrations.RemoveConstraint(
            model_name='invoiceline',
            name='invoice_line_shape_per_kind',
        ),
        migrations.RemoveConstraint(
            model_name='invoiceline',
            name='invoice_line_quantity_positive',
        ),
        migrations.RemoveField(
            model_name='expenseline',
            name='service_line',
        ),
        migrations.RemoveField(
            model_name='invoiceline',
            name='description',
        ),
        migrations.RemoveField(
            model_name='invoiceline',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='invoiceline',
            name='unit_price',
        ),
        migrations.AlterField(
            model_name='invoice',
            name='invoice_type',
            field=models.CharField(choices=[('hotel', 'Hotel')], db_index=True, default='hotel', max_length=20),
        ),
        migrations.AlterField(
            model_name='invoiceline',
            name='kind',
            field=models.CharField(choices=[('hotel', 'Hotel reservation'), ('penalty', 'Cancellation penalty')], max_length=8),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(condition=models.Q(('invoice_type__in', ['hotel'])), name='invoice_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.CheckConstraint(condition=models.Q(('kind__in', ['hotel', 'penalty'])), name='invoice_line_kind_valid'),
        ),
        migrations.AddConstraint(
            model_name='invoiceline',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('confirmation_letter__isnull', False), ('kind', 'hotel'), ('penalty__isnull', True)), models.Q(('confirmation_letter__isnull', True), ('kind', 'penalty'), ('penalty__isnull', False)), _connector='OR'), name='invoice_line_shape_per_kind'),
        ),
    ]
