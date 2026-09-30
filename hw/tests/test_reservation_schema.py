"""Schema v2 F3: reservasi (CL), kamar, denda, dan lampiran tanpa salinan data."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from hw.models import (
    Attachment, CancellationPenalty, Client, ConfirmationLetter, Hotel, Room, RoomType,
)
from hw.tests.factories import make_cl, make_client, make_hotel, make_invoice, make_room


class ReservationNamesTest(TestCase):
    def test_names_are_read_from_the_masters_not_stored(self):
        client = Client.objects.create(name='PT Maju Jaya', brand='Amanah Tour')
        hotel = Hotel.objects.create(name='Al Safwah', city='makkah')
        cl = make_cl(client=client, hotel=hotel)
        self.assertEqual((cl.guest_name, cl.hotel_name), ('Amanah Tour', 'Al Safwah'))
        fields = {f.name for f in ConfirmationLetter._meta.get_fields()}
        self.assertFalse({'guest_name', 'hotel_name'} & fields)

    def test_renaming_the_master_is_seen_immediately(self):
        client = Client.objects.create(name='PT Maju Jaya')
        hotel = Hotel.objects.create(name='Al Safwa', city='makkah')
        cl = make_cl(client=client, hotel=hotel)
        Client.objects.filter(pk=client.pk).update(brand='Amanah Tour')
        Hotel.objects.filter(pk=hotel.pk).update(name='Al Safwah Tower')
        cl = ConfirmationLetter.objects.with_parties().get(pk=cl.pk)
        self.assertEqual((cl.guest_name, cl.hotel_name), ('Amanah Tour', 'Al Safwah Tower'))

    def test_search_matches_client_brand_and_hotel(self):
        client = Client.objects.create(name='PT Maju Jaya', brand='Amanah Tour')
        hotel = Hotel.objects.create(name='Al Safwah', city='makkah')
        cl = make_cl(client=client, hotel=hotel, confirmation_number='7833')
        for token in ('amanah', 'maju', 'safwah', '783'):
            qs = ConfirmationLetter.objects.filter(ConfirmationLetter.objects.name_matches(token))
            self.assertEqual(list(qs), [cl], token)


class ReservationConstraintTest(TestCase):
    def setUp(self):
        self.client_obj = make_client()
        self.hotel = make_hotel()

    def _create(self, **kw):
        defaults = dict(client=self.client_obj, hotel=self.hotel, confirmation_number='C1',
                        check_in=date(2026, 10, 1), check_out=date(2026, 10, 3))
        defaults.update(kw)
        return ConfirmationLetter.objects.create(**defaults)

    def test_client_hotel_and_dates_are_required(self):
        for missing in ('client', 'hotel', 'check_in', 'check_out'):
            with self.assertRaises(IntegrityError, msg=missing), transaction.atomic():
                self._create(**{missing: None})

    def test_status_is_limited_to_three_values(self):
        self._create(reservation_status='TENTATIVE')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create(confirmation_number='C2', reservation_status='Cancelled')

    def test_check_out_must_be_after_check_in(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create(check_out=date(2026, 10, 1))

    def test_client_and_hotel_with_reservations_cannot_be_deleted(self):
        self._create()
        with self.assertRaises(ProtectedError):
            self.client_obj.delete()
        with self.assertRaises(ProtectedError):
            self.hotel.delete()


class RoomSchemaTest(TestCase):
    def setUp(self):
        self.cl = make_cl()
        self.rt = RoomType.objects.create(hotel=self.cl.hotel, name='Quad Kaaba View', capacity=4)

    def test_room_type_and_meals_are_read_from_masters(self):
        room = Room.objects.create(cl=self.cl, room_type_ref=self.rt, meal_plan_id='BB', quantity=2, price=300)
        self.assertEqual((room.room_type, room.meals), ('Quad Kaaba View', 'BB'))
        fields = {f.name for f in Room._meta.get_fields()}
        self.assertFalse({'room_type', 'meals'} & fields)

    def test_free_text_board_is_a_note(self):
        room = Room.objects.create(cl=self.cl, room_type_ref=self.rt, note='BB + late checkout', price=300)
        self.assertEqual(room.meals, 'BB + late checkout')

    def test_room_type_is_required_and_protected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Room.objects.create(cl=self.cl, quantity=1, price=100)
        make_room(cl=self.cl, room_type_ref=self.rt)
        with self.assertRaises(ProtectedError):
            self.rt.delete()

    def test_quantity_and_price_are_checked(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Room.objects.create(cl=self.cl, room_type_ref=self.rt, quantity=0, price=100)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Room.objects.create(cl=self.cl, room_type_ref=self.rt, quantity=1, price=-1)

    def test_rooms_are_part_of_the_reservation(self):
        make_room(cl=self.cl, room_type_ref=self.rt)
        self.cl.delete()
        self.assertFalse(Room.objects.exists())


class PenaltySchemaTest(TestCase):
    def setUp(self):
        self.cl = make_cl(reservation_status='CANCELLED')

    def _penalty(self, cl, amount, number='PNL-1'):
        return CancellationPenalty.objects.create(
            cl=cl, penalty_number=number, cancellation_date=date(2026, 10, 1), penalty_amount=amount,
        )

    def test_penalty_is_sar_and_positive(self):
        p = self._penalty(self.cl, 500)
        self.assertEqual((p.penalty_currency, p.exchange_rate, p.amount_sar, p.penalty_amount_sar),
                         ('SAR', 1, 500, 500))
        other = make_cl(reservation_status='CANCELLED')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._penalty(other, 0, number='PNL-2')

    def test_reservation_with_a_penalty_cannot_be_deleted(self):
        self._penalty(self.cl, 500)
        with self.assertRaises(ProtectedError):
            self.cl.delete()

    def test_penalty_form_refuses_an_active_reservation(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        active = make_cl(reservation_status='DEFINITE')
        self.client.post(f'/cl/{active.pk}/penalty/new/', {
            'penalty_number': 'PNL-9', 'cancellation_date': '2026-10-01', 'penalty_amount': '500',
        })
        self.assertFalse(CancellationPenalty.objects.filter(cl=active).exists())

    def test_penalty_form_refuses_zero(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-9', 'cancellation_date': '2026-10-01', 'penalty_amount': '0',
        })
        self.assertFalse(CancellationPenalty.objects.exists())


class AttachmentParentTest(TestCase):
    def test_exactly_one_parent(self):
        cl = make_cl()
        inv = make_invoice(invoice_number='INV-A', customer_name='X', client=cl.client)
        Attachment.objects.create(cl=cl, file='a.pdf', name='a.pdf')
        Attachment.objects.create(invoice=inv, file='b.pdf', name='b.pdf')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attachment.objects.create(cl=cl, invoice=inv, file='c.pdf', name='c.pdf')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attachment.objects.create(file='d.pdf', name='d.pdf')
