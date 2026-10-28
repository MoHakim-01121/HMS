"""Migrasi 0133: alokasi setoran yang belum diterima Pusat.

Alokasinya dipindah ke catatan dan barisnya dihapus, jadi harus lolos
pemeriksaan yang sama dengan alokasi lain lebih dulu.
"""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('hw', '0132_client_refund_transfer')]
AFTER = [('hw', '0133_remittance_single_path')]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


class PendingRemittanceMigrationTest(TransactionTestCase):
    # TransactionTestCase mengosongkan tabel; pulihkan data seed migrasi.
    serialized_rollback = True

    def setUp(self):
        self.apps = _migrate(BEFORE)
        self.addCleanup(self._forward)
        get =lambda name: self.apps.get_model('hw', name)  # noqa: E731
        Branch, Ledger, Account = get('Branch'), get('LedgerAccount'), get('MoneyAccount')
        for code in ('pusat', 'sby'):
            Branch.objects.get_or_create(code=code, defaults={'name': code})
        ledger = Ledger.objects.order_by('pk').first()
        Account.objects.create(name='Kas SAR Pusat', branch_id='pusat', currency='SAR', kind='cash', ledger_account=ledger)
        idr = Account.objects.create(name='Kas IDR Sby', branch_id='sby', currency='IDR', kind='cash', ledger_account=ledger)

        client = get('Client').objects.create(name='Labaik', name_key='labaik')
        hotel = get('Hotel').objects.create(name='Hilton')
        cl = get('ConfirmationLetter').objects.create(
            confirmation_number='CL-001', client=client, hotel=hotel,
            check_in=date(2026, 11, 1), check_out=date(2026, 11, 3),
        )
        invoice = get('Invoice').objects.create(invoice_number='INV-001', client=client, branch_id='sby')
        get('InvoiceLine').objects.create(invoice=invoice, kind='hotel', line_no=1, confirmation_letter=cl)

        self.Remittance, self.Line = get('Remittance'), get('RemittanceLine')
        self.rem = self.Remittance.objects.create(
            remittance_number='RMT-001', date=date(2026, 10, 20), status='pending', note='Transfer BCA',
            from_account=idr, amount_idr=6_000_000, exchange_rate=Decimal('4000'),
        )

    def _forward(self):
        # Hapus data uji dulu supaya migrasi maju ke ujung tidak tertahan.
        get = lambda name: self.apps.get_model('hw', name)  # noqa: E731
        get('RemittanceLine').objects.all().delete()
        get('Remittance').objects.all().delete()
        _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_valid_allocation_moves_to_note(self):
        self.Line.objects.create(remittance=self.rem, linked_number='CL-001', amount_sar=1_500)
        apps = self.apps = _migrate(AFTER)
        rem = apps.get_model('hw', 'Remittance').objects.get(pk=self.rem.pk)
        self.assertEqual(rem.note, 'Transfer BCA\nAlokasi saat diterima: CL-001 1.500 SAR')
        self.assertFalse(apps.get_model('hw', 'RemittanceLine').objects.exists())

    def test_unknown_cl_stops_migration_once_and_keeps_line(self):
        self.Line.objects.create(remittance=self.rem, linked_number='CL-999', amount_sar=1_500)
        with self.assertRaises(RuntimeError) as ctx:
            _migrate(AFTER)
        self.assertEqual(str(ctx.exception).count('CL-999'), 1)
        self.assertEqual(self.Remittance.objects.get(pk=self.rem.pk).note, 'Transfer BCA')
        self.assertTrue(self.Line.objects.filter(linked_number='CL-999').exists())

    def test_zero_amount_stops_migration(self):
        self.Line.objects.create(remittance=self.rem, linked_number='CL-001', amount_sar=0)
        with self.assertRaisesRegex(RuntimeError, r'CL-001\): nominal 0'):
            _migrate(AFTER)
        self.assertTrue(self.Line.objects.exists())
