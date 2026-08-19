import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, Room, Invoice, Reservation, Charge
from hw import ledger


class InvoiceFromClsChargeTest(TestCase):
    """invoice_from_cls creates the reservation cache directly (bypassing
    _save_reservations), so it needs its own Charge write to keep the ledger
    in sync from day one."""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.client_obj = Client.objects.create(company='konoz', name='PT From CLs')
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-FROMCLS-001', guest_name='Budi',
            client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=1000)

    def test_converting_cl_to_invoice_writes_initial_charge(self):
        resp = self.client.post("/cl/invoice-from-cls/", {"cl_ids": [self.cl.pk]})
        self.assertEqual(resp.status_code, 302)

        reservation = Reservation.objects.get(reservation_number='CL-FROMCLS-001')
        self.assertEqual(reservation.total_sar, 2000)  # 1000 * 1 room * 2 nights
        self.assertEqual(ledger.tagihan(reservation), 2000)
        charge = Charge.objects.get(reservation=reservation)
        self.assertEqual(charge.client, self.client_obj)
        self.assertEqual(charge.reason, 'initial')


class ClEditReservationSyncChargeTest(TestCase):
    """cl_edit -> _sync_invoice_reservation_from_cl must record the total_sar
    delta as a revision Charge, not just move the cache field."""

    def setUp(self):
        self.user = User.objects.create_user("tester2", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-CLEDIT-001', customer_name='Test',
        )
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-EDIT-001', guest_name='Ahmad',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
            invoice=self.invoice,
        )
        self.reservation = Reservation.objects.create(
            invoice=self.invoice, reservation_number='CL-EDIT-001', total_sar=0,
        )
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=800)
        self.reservation.refresh_from_db()

    def test_editing_cl_dates_extends_nights_and_writes_revision_charge(self):
        # 1 night -> 3 nights should raise the total and record the +1600 delta
        resp = self.client.post(f"/cl/{self.cl.pk}/edit/", {
            "hotel_name": self.cl.hotel_name or "Hotel",
            "guest_name": self.cl.guest_name,
            "check_in": self.cl.check_in.isoformat(),
            "check_out": (self.cl.check_in + timedelta(days=3)).isoformat(),
            "confirmation_number": self.cl.confirmation_number,
            "reservation_status": "DEFINITE",
            "rooms": json.dumps([{"room_type": "Deluxe", "quantity": 1, "price": 800}]),
        })
        self.assertEqual(resp.status_code, 302)

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 2400)  # 800 * 1 * 3 nights
        self.assertEqual(ledger.tagihan(self.reservation), 2400)
