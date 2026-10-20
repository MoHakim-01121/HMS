"""Halaman daftar utama dan dashboard tidak boleh N+1: jumlah query harus tetap
sama walau jumlah client, hotel, CL, invoice, dan payment bertambah."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from hw.tests.factories import (
    ensure_current_period, make_client, make_hotel_line, make_invoice, make_payment,
)

# Halaman → apakah nomor data terakhir harus tampil di halaman itu.
PAGES = {
    '/cl/': 'cl',
    '/invoice/': 'invoice',
    '/finance/payments/?year=all': 'payment',
    '/clients/': 'client',
    '/hotels/': 'hotel',
    '/dashboard/': None,
}


class ListQueryCountTest(TestCase):
    def setUp(self):
        ensure_current_period()
        admin = User.objects.create_superuser('lqc', password='pw12345')
        self.client.force_login(admin)
        self.admin = admin
        self._seq = 0
        self.last = {}

    def _add_rows(self, n):
        today = date.today()
        for _ in range(n):
            self._seq += 1
            s = self._seq
            client = make_client(f'PT Query Count {s}')
            invoice = make_invoice(
                client=client, invoice_number=f'INV-LQC-{s}', issued_date=today, due_date=today,
            )
            make_hotel_line(
                invoice, reservation_number=f'CL-LQC-{s}', hotel=f'Hotel LQC {s}',
                total_sar=1000, check_in=today, check_out=today + timedelta(days=2),
            )
            make_payment(
                payment_number=f'PAY-LQC-{s}', payment_date=today, amount=500, amount_sar=500,
                exchange_rate=1, method='Transfer', client=client, invoice=invoice,
                created_by=self.admin,
            )
            self.last = {
                'cl': f'CL-LQC-{s}', 'invoice': f'INV-LQC-{s}', 'payment': f'PAY-LQC-{s}',
                'client': f'PT Query Count {s}', 'hotel': f'Hotel LQC {s}',
            }

    def _counts(self):
        out = {}
        for url, kind in PAGES.items():
            self.client.get(url)  # warm-up: cache-miss queries would mask growth
            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            if kind:
                self.assertIn(self.last[kind], resp.content.decode(), url)
            out[url] = len(ctx.captured_queries)
        return out

    def test_query_count_does_not_grow_with_rows(self):
        self._add_rows(2)
        few = self._counts()
        self._add_rows(6)
        many = self._counts()
        self.assertEqual(few, many)

    def test_payment_detail_does_not_grow_with_open_invoices(self):
        """Lembar alokasi payment memuat semua invoice terbuka client-nya."""
        today = date.today()
        client = make_client('PT Query Count Detail')
        payment = make_payment(
            payment_number='PAY-LQC-DETAIL', payment_date=today, amount=500, amount_sar=500,
            exchange_rate=1, method='Transfer', client=client, created_by=self.admin,
        )
        url = f'/finance/payments/{payment.pk}/'

        def add_invoices(n):
            for _ in range(n):
                self._seq += 1
                invoice = make_invoice(client=client, invoice_number=f'INV-LQCD-{self._seq}')
                make_hotel_line(invoice, reservation_number=f'CL-LQCD-{self._seq}', total_sar=1000)

        def count():
            self.client.get(url)
            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(f'INV-LQCD-{self._seq}', resp.content.decode())
            return len(ctx.captured_queries)

        add_invoices(2)
        few = count()
        add_invoices(6)
        self.assertEqual(few, count())
