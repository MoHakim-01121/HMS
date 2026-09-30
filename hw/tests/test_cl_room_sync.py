from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_room
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from hw.models import Client, Hotel, RoomType
from hw.models.period import FinancialPeriod
from hw.finance import queries as fq


class CLTotalPriceTest(TestCase):
    def setUp(self):
        self.cl = make_cl(
 confirmation_number='CL-CALC-001', guest_name='Ahmad',
            check_in=date.today(), check_out=date.today() + timedelta(days=2),
        )

    def test_total_price_is_price_times_quantity_times_nights(self):
        make_room(cl=self.cl, room_type='Deluxe', quantity=2, price=500)
        # 2 nights (check_out - check_in) * 2 rooms * 500 = 2000
        self.assertEqual(self.cl.total_price, 2000)

    def test_total_price_sums_multiple_room_types(self):
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=500)
        make_room(cl=self.cl, room_type='Suite', quantity=1, price=1000)
        self.assertEqual(self.cl.total_price, 2 * (500 + 1000))


class CLNumGuestsTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        self.cl = make_cl(
 confirmation_number='CL-GUESTS-001', guest_name='Ahmad',
            hotel=self.hotel, check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )

    def test_num_guests_uses_linked_room_type_capacity(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Double View Kaaba', capacity=2)
        make_room(cl=self.cl, room_type='Double View Kaaba', room_type_ref=rt, quantity=3, price=500)
        self.assertEqual(self.cl.num_guests, 6)

    def test_num_guests_sums_capacity_across_room_types(self):
        # Schema v2: setiap kamar menunjuk tipe kamar di katalog, jadi jumlah
        # tamu selalu dari capacity (tidak ada lagi tebakan dari teks).
        quad = RoomType.objects.create(hotel=self.hotel, name='Quad', capacity=4)
        single = RoomType.objects.create(hotel=self.hotel, name='Single', capacity=1)
        make_room(cl=self.cl, room_type_ref=quad, quantity=2, price=500)
        make_room(cl=self.cl, room_type_ref=single, quantity=2, price=500)
        self.assertEqual(self.cl.num_guests, 10)

    def test_num_guests_still_uses_capacity_of_deactivated_room_type(self):
        # A hotel admin retiring a room type (is_active=False) must not corrupt
        # the guest count of bookings made while it was still active.
        rt = RoomType.objects.create(hotel=self.hotel, name='Double View Kaaba', capacity=2)
        make_room(cl=self.cl, room_type='Double View Kaaba', room_type_ref=rt, quantity=2, price=500)
        rt.is_active = False
        rt.save()
        self.assertEqual(self.cl.num_guests, 4)


class RoomTotalChangedSignalTest(TestCase):
    """hw/signals.py::_room_total_changed makes the invoice follow whenever a
    billed CL's rooms change: the line reads its value from the CL, and the
    invoice charge in the journal is re-posted to match."""

    def setUp(self):
        User.objects.create_user('sync', password='x')
        FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Sync Client')
        self.invoice = make_invoice(
            invoice_type='hotel', invoice_number='INV-SYNC-001', client=self.client_obj,
        )
        self.cl = make_cl(
            confirmation_number='CL-SYNC-001', client=self.client_obj,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
            invoice=self.invoice,
        )
        self.reservation = make_hotel_line(invoice=self.invoice, reservation_number='CL-SYNC-001')

    def test_creating_a_room_syncs_reservation_total(self):
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 750)  # 1 night * 1 room * 750

    def test_deleting_a_room_resyncs_reservation_total(self):
        room = make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        room.delete()
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 0)

    def test_sync_is_noop_without_linked_invoice(self):
        cl_no_invoice = make_cl(
 confirmation_number='CL-SYNC-002', guest_name='Cici',
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
        # Should not raise even though there's no invoice/reservation to sync
        make_room(cl=cl_no_invoice, room_type='Deluxe', quantity=1, price=500)

    def _wire_client_and_period(self):
        return self.client_obj

    def test_room_change_reposts_invoice_charge_in_journal(self):
        self._wire_client_and_period()
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        self.reservation.refresh_from_db()
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), self.reservation.total_sar)

    def test_price_change_reposts_to_new_total_not_sum(self):
        self._wire_client_and_period()
        room = make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        room.price = 1000
        room.save()
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.total_sar, 1000)
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 1000)

    def test_charge_client_matches_invoice_client(self):
        c = self._wire_client_and_period()
        make_room(cl=self.cl, room_type='Deluxe', quantity=1, price=750)
        self.assertEqual(fq.client_receivable(c.id), 750)
