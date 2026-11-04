from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from hw.tests.factories import make_cl, make_hotel_line, make_invoice
from hw.views.pdf import _render_cl_pdf, _render_invoice_pdf


class InvoicePdfCachingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-PDFCACHE-001', customer_name='Test Customer',
            issued_date=date.today(),
        )
        make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=1000)

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
        self.invoice.save()  # bumps updated_at
        _render_invoice_pdf(self.invoice)

        self.assertEqual(mock_html.call_count, 2, "changing the invoice must re-render, not serve stale cache")


class ClPdfCachingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.cl = make_cl()

    @patch('hw.views.pdf.HTML')
    def test_hotel_rename_re_renders(self, mock_html):
        # Renaming the hotel changes the PDF without saving the CL row.
        mock_html.return_value.write_pdf.return_value = b'%PDF-fake-bytes'
        _render_cl_pdf(self.cl)
        _render_cl_pdf(self.cl)
        self.assertEqual(mock_html.call_count, 1)

        self.cl.hotel.name = 'Hotel Baru'
        self.cl.hotel.save()
        _render_cl_pdf(self.cl)
        self.assertEqual(mock_html.call_count, 2)


class PdfNoStoreTest(TestCase):
    def test_pdf_response_is_not_cacheable(self):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from hw.pdf_no_store_middleware import PdfNoStoreMiddleware
        mw = PdfNoStoreMiddleware(lambda r: HttpResponse(b'%PDF', content_type='application/pdf'))
        self.assertIn('no-store', mw(RequestFactory().get('/x/'))['Cache-Control'])

    def test_view_cache_control_is_kept(self):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from hw.pdf_no_store_middleware import PdfNoStoreMiddleware

        def view(r):
            response = HttpResponse(b'%PDF', content_type='application/pdf')
            response['Cache-Control'] = 'public, max-age=86400'
            return response
        self.assertEqual(PdfNoStoreMiddleware(view)(RequestFactory().get('/x/'))['Cache-Control'], 'public, max-age=86400')
