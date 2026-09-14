"""FASE G (partial) — Reservation.client / Reservation.confirmation_letter FKs."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, Invoice, Reservation, Room
from hw.models.period import FinancialPeriod


class InvoiceFromClsLinksReservationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('resadmin', 'a@a.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT Reservasi')

    def test_invoice_from_cls_links_confirmation_letter_and_client(self):
        cl = ConfirmationLetter.objects.create(
 confirmation_number='CL-RES-1', guest_name='Ahmad',
            client=self.client_obj, check_in=date(2026, 6, 1), check_out=date(2026, 6, 3),
        )
        Room.objects.create(cl=cl, room_type='Double', quantity=1, price=500)

        self.client.post('/cl/invoice-from-cls/', {'cl_ids': [str(cl.pk)]})

        reservation = Reservation.objects.get(reservation_number='CL-RES-1')
        self.assertEqual(reservation.confirmation_letter_id, cl.pk)
        self.assertEqual(reservation.client_id, self.client_obj.pk)


class BackfillMatchesLiveSyncRuleTest(TestCase):
    """The 0095 backfill must reproduce exactly what _sync_invoice_reservation_
    from_cl already assumes: same invoice, reservation_number == confirmation_number."""

    def test_backfill_logic_matches_by_invoice_and_number(self):
        import importlib.util
        from pathlib import Path
        from django.apps import apps as django_apps

        invoice = Invoice.objects.create(invoice_number='INV-BF-1', customer_name='X')
        client_obj = Client.objects.create( name='PT Backfill')
        cl = ConfirmationLetter.objects.create(
 confirmation_number='CL-BF-1', guest_name='Ahmad',
            client=client_obj, invoice=invoice,
        )
        # Simulate a pre-FASE-G row: created without the new FKs.
        reservation = Reservation.objects.create(
            invoice=invoice, reservation_number='CL-BF-1', total_sar=1000,
        )
        Reservation.objects.filter(pk=reservation.pk).update(confirmation_letter=None, client=None)

        # Module name starts with a digit -- not import_module-able by dotted
        # path, so load it straight from its file.
        path = Path(__file__).resolve().parents[1] / 'migrations' / '0095_backfill_reservation_client_cl.py'
        spec = importlib.util.spec_from_file_location('_backfill_0095', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # apps.get_model on the *live* app registry returns the real models
        # here (fine for this test: we only exercise field assignment logic,
        # not a historical-state migration).
        mod.backfill(django_apps, None)

        reservation.refresh_from_db()
        self.assertEqual(reservation.confirmation_letter_id, cl.pk)
        self.assertEqual(reservation.client_id, client_obj.pk)
