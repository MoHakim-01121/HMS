from datetime import date, timedelta
from django.test import TestCase
from hw.models import ConfirmationLetter, Room, Invoice, Reservation


class CLTotalPriceTest(TestCase):
    def setUp(self):
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-CALC-001', guest_name='Ahmad',
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )

    def test_total_price_is_price_times_quantity_times_nights(self):
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=2, price=500)
        # 2 nights (check_out - check_in) * 2 rooms * 500 = 2000
        self.assertEqual(self.cl.total_price, 2000)

    def test_total_price_sums_multiple_room_types(self):
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=500)
        Room.objects.create(cl=self.cl, room_type='Suite', quantity=1, price=1000)
        self.assertEqual(self.cl.total_price, 2 * (500 + 1000))


class RoomTotalChangedSignalTest(TestCase):
    """hw/signals.py::_room_total_changed keeps the linked Reservation.total_sar
    in sync whenever a CL's rooms change, so the invoice total stays correct."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-SYNC-001', customer_name='Test Customer',
        )
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-SYNC-001', guest_name='Budi',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
            invoice=self.invoice,
        )
        self.reservation = Reservation.objects.create(
            invoice=self.invoice, reservation_number='CL-SYNC-001', total_sar=0,
        )

    def test_creating_a_room_syncs_reservation_total(self):
        Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 750)  # 1 night * 1 room * 750

    def test_deleting_a_room_resyncs_reservation_total(self):
        room = Room.objects.create(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        room.delete()
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 0)

    def test_sync_is_noop_without_linked_invoice(self):
        cl_no_invoice = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-SYNC-002', guest_name='Cici',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
        # Should not raise even though there's no invoice/reservation to sync
        Room.objects.create(cl=cl_no_invoice, room_type='Deluxe', quantity=1, price=500)
