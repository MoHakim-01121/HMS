"""A hotel invoice line points at the reservation (CL) it bills."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Reservation
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_cl, make_room


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
        cl = make_cl(
 confirmation_number='CL-RES-1', guest_name='Ahmad',
            client=self.client_obj, check_in=date(2026, 6, 1), check_out=date(2026, 6, 3),
        )
        make_room(cl=cl, room_type='Double', quantity=1, price=500)

        self.client.post('/cl/invoice-from-cls/', {'cl_ids': [str(cl.pk)]})

        reservation = Reservation.objects.get(confirmation_letter=cl)
        self.assertEqual(reservation.reservation_number, 'CL-RES-1')
        self.assertEqual(reservation.invoice.client_id, self.client_obj.pk)
        self.assertEqual(reservation.invoice.branch_id, self.client_obj.owner_branch_id)
