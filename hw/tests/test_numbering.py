"""hw.numbering — counter satu baris per jenis dokumen (DocumentSequence)."""
from datetime import date

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from hw.models import CancellationPenalty, Client, ConfirmationLetter, DocumentSequence, Invoice, Receipt, Season
from hw.models.choices import InvoiceType
from hw.numbering import NumberingError, advance_number, generate_sequential_number, peek_number
from hw.tests.factories import make_cl, make_invoice


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

    def test_invoice_prefix(self):
        client = Client.objects.create(name='PT A')
        make_invoice(invoice_type=InvoiceType.HOTEL, invoice_number='INV-004', client=client, customer_name='PT A')
        with transaction.atomic():
            # Existing invoice numbers seed the single global counter.
            self.assertEqual(
                Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2041, 5, 1)),
                'INV-005',
            )

    def test_invoice_suggestion_uses_the_allocation_key(self):
        with transaction.atomic():
            suggested = Invoice.suggest_number(InvoiceType.HOTEL, issued_date=date(2041, 5, 1))
            self.assertEqual(suggested, 'INV-001')
            self.assertEqual(
                Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2041, 5, 1)),
                suggested,
            )

    def test_invoice_continues_count_within_the_season_across_months(self):
        client = Client.objects.create(name='PT A')
        Season.objects.create(
            name='Musim 1448H', date_from=date(2026, 5, 31), date_to=date(2027, 5, 19),
        )
        make_invoice(
            invoice_type=InvoiceType.HOTEL, invoice_number='INV-106',
            client=client, issued_date=date(2026, 10, 30),
        )
        make_invoice(
            invoice_type=InvoiceType.HOTEL, invoice_number='INV-2026-11-001',
            client=client, issued_date=date(2026, 11, 2),
        )

        with transaction.atomic():
            self.assertEqual(
                Invoice.suggest_number(InvoiceType.HOTEL, issued_date=date(2026, 11, 4)),
                'INV-107',
            )
            self.assertEqual(
                Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2026, 11, 4)),
                'INV-107',
            )

    def test_invoice_counter_resets_for_a_new_season(self):
        Season.objects.create(name='Musim A', date_from=date(2026, 6, 1), date_to=date(2026, 12, 31))
        Season.objects.create(name='Musim B', date_from=date(2027, 1, 1), date_to=date(2027, 5, 31))
        with transaction.atomic():
            june = Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2026, 6, 1))
            november = Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2026, 11, 30))
            january = Invoice.generate_number(InvoiceType.HOTEL, issued_date=date(2027, 1, 1))
        self.assertEqual((june, november, january), ('INV-001', 'INV-002', 'INV-001'))

    def test_receipt_counter_resets_for_a_new_season(self):
        Season.objects.create(name='Musim A', date_from=date(2026, 6, 1), date_to=date(2026, 12, 31))
        Season.objects.create(name='Musim B', date_from=date(2027, 1, 1), date_to=date(2027, 5, 31))
        with transaction.atomic():
            first = Receipt.generate_number(date(2026, 6, 1))
            later = Receipt.generate_number(date(2026, 11, 1))
            next_season = Receipt.generate_number(date(2027, 1, 1))
        self.assertEqual((first, later, next_season), ('RCP-0001', 'RCP-0002', 'RCP-0001'))

    def test_same_invoice_number_can_be_reused_in_another_season(self):
        client = Client.objects.create(name='PT A')
        Season.objects.create(name='Musim A', date_from=date(2026, 6, 1), date_to=date(2026, 12, 31))
        Season.objects.create(name='Musim B', date_from=date(2027, 1, 1), date_to=date(2027, 5, 31))
        first = make_invoice(
            invoice_type=InvoiceType.HOTEL, invoice_number='INV-001', client=client,
            issued_date=date(2026, 6, 1),
        )
        self.assertTrue(Invoice.number_exists_in_season('INV-001', date(2026, 6, 2)))
        self.assertFalse(Invoice.number_exists_in_season('INV-001', date(2027, 1, 1)))
        second = make_invoice(
            invoice_type=InvoiceType.HOTEL, invoice_number='INV-001', client=client,
            issued_date=date(2027, 1, 1),
        )
        self.assertNotEqual(first.season_id, second.season_id)

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
