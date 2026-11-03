"""Invoice PDF: payment history splits by allocation, and every status renders."""
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from hw.finance import posting
from hw.finance.queries import payment_history_rows
from hw.models import Client
from hw.models.payment import PaymentAllocation, PaymentRecord
from hw.models.period import FinancialPeriod
from hw.models.invoice import InvoiceLine
from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_payment, make_room
from hw.views.pdf import _payment_history_context, _render_invoice_pdf, _reservation_room_rows


def _row(amount, amount_sar, allocations, currency='IDR'):
    return {
        'payment_id': 'PAY-1', 'payment_date': date(2026, 11, 2), 'method': 'Transfer',
        'received_in_display': 'Surabaya', 'amount': amount, 'currency': currency,
        'exchange_rate': 4800.0, 'amount_sar': amount_sar, 'allocations': allocations,
        'unallocated_sar': amount_sar - sum(a['amount_sar'] for a in allocations),
    }


class PaymentHistorySplitTest(TestCase):
    def test_one_row_per_allocation(self):
        rows = _payment_history_context(_row(48_000_000, 10_000, [
            {'rsv': '4353', 'amount_sar': 5_000}, {'rsv': '4455', 'amount_sar': 5_000},
        ]))
        self.assertEqual([r['rsv'] for r in rows], ['4353', '4455'])
        self.assertEqual([r['amount'] for r in rows], ['24,000,000', '24,000,000'])
        self.assertEqual([r['amount_sar'] for r in rows], ['5,000', '5,000'])
        self.assertEqual(rows[0]['received_in'], 'Surabaya')
        self.assertEqual([r['first'] for r in rows], [True, False])

    def test_unallocated_money_is_a_row_without_a_reservation(self):
        rows = _payment_history_context(_row(48_000_000, 10_000, [{'rsv': '4353', 'amount_sar': 8_000}]))
        self.assertEqual([r['rsv'] for r in rows], ['4353', '—'])
        self.assertEqual([r['amount_sar'] for r in rows], ['8,000', '2,000'])

    def test_unallocated_payment_has_one_row(self):
        rows = _payment_history_context(_row(48_000_000, 10_000, []))
        self.assertEqual([r['rsv'] for r in rows], ['—'])
        self.assertEqual(rows[0]['amount'], '48,000,000')

    def test_last_row_takes_the_rounding(self):
        rows = _payment_history_context(_row(100, 3, [
            {'rsv': 'A', 'amount_sar': 1}, {'rsv': 'B', 'amount_sar': 1}, {'rsv': 'C', 'amount_sar': 1},
        ]))
        self.assertEqual([r['amount'] for r in rows], ['33', '33', '34'])


class InvoicePdfRenderTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('invoicepdf', password='pw12345')
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        client = Client.objects.create(name='PT Invoice')
        self.client_obj = client
        self.invoice = make_invoice(
            invoice_type='hotel', client=client, invoice_number='INV-PDF-1', customer_name='PT Invoice',
        )
        self.line = make_hotel_line(
            invoice=self.invoice, reservation_number='R1', hotel='Dar Al Eiman',
            check_in=date(2026, 12, 1), check_out=date(2026, 12, 6), total_sar=30_000,
        )
        self.payment = make_payment(
            payment_number='PAY-PDF-1', invoice=self.invoice, client=client,
            payment_date=date(2026, 11, 2), amount=10_000, currency='SAR', exchange_rate=1,
            amount_sar=10_000, method='Transfer', status=PaymentRecord.STATUS_CONFIRMED, created_by=self.user,
        )
        PaymentAllocation.objects.create(payment=self.payment, invoice_line=self.line, amount_sar=10_000)

    def _assert_pdf(self):
        response = _render_invoice_pdf(self.invoice)
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_history_row_names_the_reservation(self):
        rows = payment_history_rows(self.invoice)
        self.assertEqual(rows[0]['allocations'], [{'rsv': 'R1', 'amount_sar': 10_000}])

    def test_unpaid_and_partly_paid_render(self):
        self._assert_pdf()
        posting.post_payment(self.payment, created_by=self.user)
        self._assert_pdf()

    def test_detailed_lists_the_rooms_of_the_cl_and_adds_up(self):
        cl = make_cl(client=self.client_obj, confirmation_number='CL-DETAIL', hotel_name='Hotel Detail',
                     check_in=date(2026, 12, 1), check_out=date(2026, 12, 6))
        make_room(cl=cl, room_type='Quad', quantity=3, price=1000)
        make_room(cl=cl, room_type='Triple', quantity=2, price=900)
        invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj, invoice_number='INV-PDF-2', customer_name='PT Invoice',
        )
        line = InvoiceLine.objects.create(
            invoice=invoice, kind=InvoiceLine.KIND_HOTEL, confirmation_letter=cl, line_no=1,
        )
        row = {'penalty_int': 0}
        rows = _reservation_room_rows(row, line)
        self.assertEqual([r['type'] for r in rows], ['Quad', 'Triple'])
        self.assertEqual([r['amount'] for r in rows], ['15,000', '9,000'])

        row = {'penalty_int': 500}
        self.assertEqual(_reservation_room_rows(row, line)[-1]['amount'], '500')

        self.assertTrue(_render_invoice_pdf(invoice, detailed=True).content.startswith(b'%PDF'))

    def test_detailed_and_plain_do_not_share_a_cached_file(self):
        plain = _render_invoice_pdf(self.invoice)
        detailed = _render_invoice_pdf(self.invoice, detailed=True)
        self.assertIn('INV-PDF-1.pdf', plain['Content-Disposition'])
        self.assertIn('INV-PDF-1-detailed.pdf', detailed['Content-Disposition'])

    def test_reallocation_invalidates_the_cached_pdf(self):
        cache.clear()
        other_line = make_hotel_line(
            invoice=self.invoice, reservation_number='R2', hotel='Another Hotel',
            check_in=date(2026, 12, 1), check_out=date(2026, 12, 6), total_sar=20_000,
        )
        with patch('hw.views.pdf.HTML.write_pdf', side_effect=[b'pdf-before', b'pdf-after']) as write_pdf:
            self.assertEqual(_render_invoice_pdf(self.invoice).content, b'pdf-before')
            PaymentAllocation.objects.filter(payment=self.payment).update(invoice_line=other_line)
            self.assertEqual(_render_invoice_pdf(self.invoice).content, b'pdf-after')
        self.assertEqual(write_pdf.call_count, 2)

    def test_void_renders(self):
        self.invoice.status = self.invoice.STATUS_VOID
        self.invoice.void_reason = 'Duplicate'
        self.invoice.voided_at = timezone.now()
        self.invoice.save(update_fields=['status', 'void_reason', 'voided_at'])
        self._assert_pdf()
