"""Aturan baris invoice yang dijaga trigger PostgreSQL (migrasi 0128).

Aturan-aturan ini melibatkan lebih dari satu tabel, jadi tidak bisa berupa
CHECK constraint. Aplikasi menolaknya lebih dulu dengan pesan yang ramah;
trigger memastikan jalur lain (shell, skrip, bug) tidak bisa melanggarnya.
"""
from datetime import date

from django.db import connection, transaction
from django.db.utils import DatabaseError, IntegrityError
from django.test import TestCase

from hw.db_pg import pg_only
from hw.models import ConfirmationLetter, Invoice, InvoiceLine, InvoiceRevision
from hw.tests.factories import make_cl, make_client, make_invoice


@pg_only
class InvoiceLineTriggerTest(TestCase):
    def setUp(self):
        self.client_obj = make_client('PT Pemilik')
        self.other = make_client('PT Lain')
        self.hotel_inv = make_invoice(client=self.client_obj)
        self.svc_inv = make_invoice(client=self.client_obj, invoice_type='visa', currency='USD')
        self.cl = make_cl(client=self.client_obj, check_in=date(2026, 3, 1), check_out=date(2026, 3, 3))

    def _refused(self, fn, text):
        with self.assertRaises(DatabaseError) as ctx, transaction.atomic():
            fn()
        self.assertIn(text, str(ctx.exception))

    def test_service_line_on_a_hotel_invoice_is_refused(self):
        self._refused(lambda: InvoiceLine.objects.create(
            invoice=self.hotel_inv, line_no=1, kind='service', description='Visa', quantity=1, unit_price=10,
        ), 'baris service tidak boleh di invoice hotel')

    def test_hotel_line_on_a_services_invoice_is_refused(self):
        self._refused(lambda: InvoiceLine.objects.create(
            invoice=self.svc_inv, line_no=1, kind='hotel', confirmation_letter=self.cl,
        ), 'hanya boleh di invoice hotel')

    def test_reservation_of_another_client_is_refused(self):
        foreign = make_cl(client=self.other, check_in=date(2026, 3, 1), check_out=date(2026, 3, 3))
        self._refused(lambda: InvoiceLine.objects.create(
            invoice=self.hotel_inv, line_no=1, kind='hotel', confirmation_letter=foreign,
        ), 'reservasi milik client lain')

    def test_client_cannot_change_under_a_live_line(self):
        InvoiceLine.objects.create(invoice=self.hotel_inv, line_no=1, kind='hotel', confirmation_letter=self.cl)
        self._refused(
            lambda: ConfirmationLetter.objects.filter(pk=self.cl.pk).update(client=self.other),
            'sudah ditagih di invoice client lain',
        )
        self._refused(
            lambda: Invoice.objects.filter(pk=self.hotel_inv.pk).update(client=self.other),
            'masih menagih reservasi milik client lain',
        )

    def test_client_may_change_once_the_line_is_voided(self):
        line = InvoiceLine.objects.create(invoice=self.hotel_inv, line_no=1, kind='hotel', confirmation_letter=self.cl)
        line.void()
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(client=self.other)
        self.assertEqual(ConfirmationLetter.objects.get(pk=self.cl.pk).client_id, self.other.pk)

    def test_revisions_are_append_only(self):
        rev = InvoiceRevision.objects.create(invoice=self.hotel_inv, revision_no=1, total=0, reason='issue')
        self._refused(lambda: InvoiceRevision.objects.filter(pk=rev.pk).update(total=5), 'append-only')
        self._refused(lambda: InvoiceRevision.objects.filter(pk=rev.pk).delete(), 'append-only')

    def test_invoice_currency_must_exist_in_the_currency_table(self):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT condeferrable FROM pg_constraint WHERE conname = 'invoice_currency_fk'"
            )
            self.assertEqual(cur.fetchone(), (True,))
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_invoice(client=self.client_obj, invoice_type='visa', currency='EUR')
