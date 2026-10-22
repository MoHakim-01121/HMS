from datetime import date, timedelta

from django.test import TestCase

from hw.models import Client, Invoice
from hw.tests.factories import make_cl, make_invoice


class ClientDisplayNameSyncTest(TestCase):
    """CL.guest_name and Invoice.customer_name are not stored: both read the
    client's brand (falling back to the registered name), so every CL and
    invoice of a client reads identically the moment a brand is added or edited."""

    def setUp(self):
        self.client_obj = Client.objects.create( name='PT Sync Test')
        self.cl = make_cl(
 confirmation_number='CL-NSYNC-001', guest_name='PT Sync Test',
            client=self.client_obj, check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )

    def test_adding_a_brand_syncs_linked_cl_guest_name(self):
        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.guest_name, 'Sync Travel')

    def test_removing_the_brand_falls_back_to_company_name(self):
        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()
        self.client_obj.brand = ''
        self.client_obj.save()
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.guest_name, 'PT Sync Test')

    def test_invoice_name_follows_the_client_brand(self):
        invoice = make_invoice(invoice_type='hotel', invoice_number='INV-NSYNC-001', client=self.client_obj)
        invoice.add_hotel_line(self.cl)

        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()

        self.assertEqual(Invoice.objects.get(pk=invoice.pk).customer_name, 'Sync Travel')

    def test_an_invoice_cannot_mix_clients(self):
        other_client = Client.objects.create( name='PT Other Sync')
        invoice = make_invoice(invoice_type='hotel', invoice_number='INV-NSYNC-002', client=self.client_obj)
        invoice.add_hotel_line(self.cl)
        other_cl = make_cl(
 confirmation_number='CL-NSYNC-002', client=other_client,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValueError):
            invoice.add_hotel_line(other_cl)

    def test_unlinked_cl_is_left_alone(self):
        unlinked = make_cl(
 confirmation_number='CL-NSYNC-003', guest_name='Free Text Guest',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()
        unlinked.refresh_from_db()
        self.assertEqual(unlinked.guest_name, 'Free Text Guest')
