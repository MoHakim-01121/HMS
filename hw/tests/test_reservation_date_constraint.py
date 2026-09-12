"""FASE G — Reservation CHECK check_out > check_in.

Added only after confirming against production data (2026-09-12): 0 of 84
existing reservations violate it, including 0 same-day bookings.
"""
from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.models import Invoice, Reservation


class ReservationDateConstraintTest(TestCase):
    def setUp(self):
        self.inv = Invoice.objects.create(invoice_number='INV-DC-1', customer_name='X')

    def test_check_out_after_check_in_is_allowed(self):
        Reservation.objects.create(
            invoice=self.inv, reservation_number='R1', total_sar=0,
            check_in=date(2026, 6, 1), check_out=date(2026, 6, 3),
        )

    def test_null_dates_are_allowed(self):
        Reservation.objects.create(invoice=self.inv, reservation_number='R2', total_sar=0)

    def test_same_day_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    invoice=self.inv, reservation_number='R3', total_sar=0,
                    check_in=date(2026, 6, 1), check_out=date(2026, 6, 1),
                )

    def test_check_out_before_check_in_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    invoice=self.inv, reservation_number='R4', total_sar=0,
                    check_in=date(2026, 6, 3), check_out=date(2026, 6, 1),
                )
