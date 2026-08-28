import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, Room, Invoice, Reservation
from hw.models.period import FinancialPeriod
from hw.finance import queries as fq


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()
        FinancialPeriod.objects.create(
            name="2020-2030", company="konoz",
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(company='konoz', name='PT CL Ledger')


class InvoiceFromClsChargeTest(_Base):
    def setUp(self):
        super().setUp()
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-FROMCLS-001', guest_name='Budi',
            client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=1000)

    def test_converting_cl_to_invoice_posts_initial_charge(self):
        resp = self.client.post("/cl/invoice-from-cls/", {"cl_ids": [self.cl.pk]})
        self.assertEqual(resp.status_code, 302)
        reservation = Reservation.objects.get(reservation_number='CL-FROMCLS-001')
        self.assertEqual(reservation.total_sar, 2000)  # 1000 * 1 room * 2 nights
        self.assertEqual(fq.invoice_charged_sar(reservation.invoice_id), 2000)
        self.assertEqual(fq.client_receivable(self.client_obj.id), 2000)


class ClEditReservationSyncChargeTest(_Base):
    def setUp(self):
        super().setUp()
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-CLEDIT-001', customer_name='PT CL Ledger',
            client=self.client_obj, issued_date=date(2026, 1, 1),
        )
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-EDIT-001', guest_name='Ahmad',
            client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
            invoice=self.invoice,
        )
        self.reservation = Reservation.objects.create(
            invoice=self.invoice, reservation_number='CL-EDIT-001', total_sar=0,
        )
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=800)
        self.reservation.refresh_from_db()

    def test_editing_cl_dates_reposts_charge_to_new_total(self):
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
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 2400)
