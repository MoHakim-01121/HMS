from datetime import date, timedelta
from django.test import TestCase
from hw.models import Client, ConfirmationLetter, Invoice


class ClientDisplayNameSyncTest(TestCase):
    """hw/signals.py::_sync_client_display_name keeps CL.guest_name and
    Invoice.customer_name mirroring the client's brand (falling back to the
    registered name) so every CL/invoice for a client reads identically
    instead of drifting apart the moment a brand gets added or edited."""

    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Sync Test')
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-NSYNC-001', guest_name='PT Sync Test',
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

    def test_syncs_customer_name_on_unambiguous_linked_invoice(self):
        invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-NSYNC-001',
            customer_name='PT Sync Test',
        )
        self.cl.invoice = invoice
        self.cl.save(update_fields=['invoice'])

        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()

        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, 'Sync Travel')

    def test_leaves_ambiguous_invoice_untouched(self):
        other_client = Client.objects.create(company='konoz', name='PT Other Sync')
        invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-NSYNC-002',
            customer_name='Mixed',
        )
        self.cl.invoice = invoice
        self.cl.save(update_fields=['invoice'])
        ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-NSYNC-002', guest_name='PT Other Sync',
            client=other_client, invoice=invoice,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )

        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()

        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, 'Mixed')

    def test_unlinked_cl_is_left_alone(self):
        unlinked = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-NSYNC-003', guest_name='Free Text Guest',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
        self.client_obj.brand = 'Sync Travel'
        self.client_obj.save()
        unlinked.refresh_from_db()
        self.assertEqual(unlinked.guest_name, 'Free Text Guest')
