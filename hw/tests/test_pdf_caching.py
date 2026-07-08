from datetime import date
from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase
from hw.models import Invoice, Reservation
from hw.views.pdf import _render_invoice_pdf


class InvoicePdfCachingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-PDFCACHE-001', customer_name='Test Customer',
            issued_date=date.today(),
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)

    @patch('hw.views.pdf.HTML')
    def test_second_render_uses_cache_not_weasyprint(self, mock_html):
        mock_html.return_value.write_pdf.return_value = b'%PDF-fake-bytes'

        _render_invoice_pdf(self.invoice)
        self.assertEqual(mock_html.call_count, 1)

        _render_invoice_pdf(self.invoice)
        self.assertEqual(mock_html.call_count, 1, "second render must be served from cache")

    @patch('hw.views.pdf.HTML')
    def test_save_invalidates_cache(self, mock_html):
        mock_html.return_value.write_pdf.return_value = b'%PDF-fake-bytes'

        _render_invoice_pdf(self.invoice)
        self.invoice.customer_name = 'Changed Name'
        self.invoice.save()  # bumps updated_at
        _render_invoice_pdf(self.invoice)

        self.assertEqual(mock_html.call_count, 2, "changing the invoice must re-render, not serve stale cache")
