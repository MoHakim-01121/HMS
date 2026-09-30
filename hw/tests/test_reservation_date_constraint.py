"""FASE G — Reservation CHECK check_out > check_in.

Added only after confirming against production data (2026-09-12): 0 of 84
existing reservations violate it, including 0 same-day bookings.
"""
from hw.tests.factories import make_cl
from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.models import ConfirmationLetter, Invoice, Reservation


class ConfirmationLetterDateConstraintTest(TestCase):
    """v2.0 §11. Verified against production before adding (2026-09-14):
    97 existing CLs, 0 violations, 0 same-day rows."""

    def test_check_out_after_check_in_is_allowed(self):
        make_cl(
 confirmation_number='CL-DC-1', guest_name='Ahmad',
            check_in=date(2026, 6, 1), check_out=date(2026, 6, 3),
        )

    def test_null_dates_are_allowed(self):
        make_cl(
 confirmation_number='CL-DC-2', guest_name='Ahmad',
        )

    def test_same_day_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_cl(
 confirmation_number='CL-DC-3', guest_name='Ahmad',
                    check_in=date(2026, 6, 1), check_out=date(2026, 6, 1),
                )

    def test_check_out_before_check_in_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_cl(
 confirmation_number='CL-DC-4', guest_name='Ahmad',
                    check_in=date(2026, 6, 3), check_out=date(2026, 6, 1),
                )


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
