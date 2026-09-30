from hw.tests.factories import cl_form_payload, make_cl, make_hotel_line, make_invoice, make_room
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Reservation
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
            name="2020-2030",            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT CL Ledger')


class InvoiceFromClsChargeTest(_Base):
    def setUp(self):
        super().setUp()
        self.cl = make_cl(
 confirmation_number='CL-FROMCLS-001', guest_name='Budi',
            client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=1000)

    def test_converting_cl_to_invoice_posts_initial_charge(self):
        resp = self.client.post("/cl/invoice-from-cls/", {"cl_ids": [self.cl.pk]})
        self.assertEqual(resp.status_code, 302)
        reservation = Reservation.objects.get(confirmation_letter__confirmation_number='CL-FROMCLS-001')
        self.assertEqual(reservation.total_sar, 2000)  # 1000 * 1 room * 2 nights
        self.assertEqual(fq.invoice_charged_sar(reservation.invoice_id), 2000)
        self.assertEqual(fq.client_receivable(self.client_obj.id), 2000)


class ClEditReservationSyncChargeTest(_Base):
    def setUp(self):
        super().setUp()
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-CLEDIT-001', customer_name='PT CL Ledger',
            client=self.client_obj, issued_date=date(2026, 1, 1),
        )
        self.cl = make_cl(
 confirmation_number='CL-EDIT-001', guest_name='Ahmad',
            client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
            invoice=self.invoice,
        )
        self.reservation = make_hotel_line(
            invoice=self.invoice, reservation_number='CL-EDIT-001', total_sar=0,
        )
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=800)
        self.reservation.refresh_from_db()

    def test_editing_cl_dates_reposts_charge_to_new_total(self):
        resp = self.client.post(f"/cl/{self.cl.pk}/edit/", cl_form_payload(
            self.cl, rooms=[{"quantity": 1, "price": 800}],
            check_out=(self.cl.check_in + timedelta(days=3)).isoformat(),
        ))
        self.assertEqual(resp.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 2400)  # 800 * 1 * 3 nights
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 2400)


class CancelledClBillsZeroOnEveryPathTest(ClEditReservationSyncChargeTest):
    """reservation_rules: a cancelled CL bills 0 on every path that writes the
    Reservation, so no later edit can bring its full price back."""

    def _edit(self, status, price=800):
        return self.client.post(f"/cl/{self.cl.pk}/edit/", cl_form_payload(
            self.cl, rooms=[{"quantity": 1, "price": price}], reservation_status=status,
        ))

    def test_cl_edit_to_cancelled_bills_zero(self):
        self.assertEqual(self._edit("CANCELLED").status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 0)
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 0)

    def test_room_change_on_cancelled_cl_stays_zero(self):
        self._edit("CANCELLED")
        self.cl.refresh_from_db()
        room = self.cl.rooms.first()
        room.price = 1500
        room.save()  # post_save signal path (_sync_reservation_total)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 0)
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 0)


class InvoiceFromCancelledClTest(_Base):
    def test_cancelled_cl_converted_to_invoice_bills_zero(self):
        cl = make_cl(
            confirmation_number='CL-FROMCLS-CXL', guest_name='Budi',
            client=self.client_obj, reservation_status='CANCELLED',
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )
        make_room(cl=cl, room_type='Deluxe', quantity=1, price=1000)
        self.client.post("/cl/invoice-from-cls/", {"cl_ids": [cl.pk]})
        reservation = Reservation.objects.get(confirmation_letter__confirmation_number='CL-FROMCLS-CXL')
        self.assertEqual(reservation.total_sar, 0)
