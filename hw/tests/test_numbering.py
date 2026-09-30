"""hw.numbering — counter satu baris per jenis dokumen (DocumentSequence)."""
from hw.tests.factories import make_cl, make_invoice
from datetime import date

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from hw.models import CancellationPenalty, Client, ConfirmationLetter, DocumentSequence, Invoice
from hw.models.choices import InvoiceType
from hw.numbering import NumberingError, advance_number, generate_sequential_number, peek_number


def _cl(number):
    return make_cl(
        confirmation_number=number, hotel_name='H', guest_name='G',
        check_in=date(2040, 1, 1), check_out=date(2040, 1, 3),
    )


class AllocateTest(TestCase):
    def test_sequential_and_seeded_from_existing(self):
        _cl('CL-007')
        with transaction.atomic():
            self.assertEqual(ConfirmationLetter.generate_number(), 'CL-008')
            self.assertEqual(ConfirmationLetter.generate_number(), 'CL-009')
        self.assertEqual(DocumentSequence.objects.get(key='CL').last_value, 9)

    def test_skips_numbers_already_taken(self):
        _cl('CL-001')
        _cl('CL-002')
        DocumentSequence.objects.create(key='CL', last_value=0)
        with transaction.atomic():
            self.assertEqual(ConfirmationLetter.generate_number(), 'CL-003')

    def test_peek_does_not_consume(self):
        _cl('CL-004')
        self.assertEqual(ConfirmationLetter.suggest_number(), 'CL-005')
        self.assertEqual(ConfirmationLetter.suggest_number(), 'CL-005')
        self.assertFalse(DocumentSequence.objects.filter(key='CL').exists())

    def test_claim_moves_counter_past_typed_number(self):
        _cl('CL-050')
        ConfirmationLetter.claim_number('CL-050')
        self.assertEqual(DocumentSequence.objects.get(key='CL').last_value, 50)
        ConfirmationLetter.claim_number('CL-010')  # lebih kecil → counter tetap
        self.assertEqual(DocumentSequence.objects.get(key='CL').last_value, 50)
        self.assertEqual(ConfirmationLetter.suggest_number(), 'CL-051')

    def test_claim_ignores_foreign_format(self):
        ConfirmationLetter.claim_number('7833')  # nomor numerik lama tanpa prefiks
        self.assertFalse(DocumentSequence.objects.filter(key='CL').exists())

    def test_invoice_prefix_per_type(self):
        client = Client.objects.create(name='PT A')
        make_invoice(invoice_type=InvoiceType.HOTEL, invoice_number='INV-004', client=client, customer_name='PT A')
        with transaction.atomic():
            self.assertEqual(Invoice.generate_number(InvoiceType.HOTEL), 'INV-005')
            self.assertEqual(Invoice.generate_number('visa'), 'SVC-001')

    def test_explicit_key_for_monthly_numbers(self):
        with transaction.atomic():
            n1 = generate_sequential_number(CancellationPenalty, 'PNL-202609', field='penalty_number', padding=3)
            n2 = generate_sequential_number(CancellationPenalty, 'PNL-202610', field='penalty_number', padding=3)
        self.assertEqual((n1, n2), ('PNL-202609-001', 'PNL-202610-001'))
        self.assertEqual(peek_number(CancellationPenalty, 'PNL-202609', field='penalty_number'), 'PNL-202609-002')

    def test_advance_creates_row_when_missing(self):
        advance_number(CancellationPenalty, 'PNL', 'PNL-020', field='penalty_number')
        self.assertEqual(DocumentSequence.objects.get(key='PNL').last_value, 20)


class OutsideTransactionTest(TransactionTestCase):
    def test_allocate_outside_atomic_is_refused(self):
        with self.assertRaises(NumberingError):
            ConfirmationLetter.generate_number()
