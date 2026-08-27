"""Alur lump-sum remittance: uang keluar bank dulu (IDR, kurs), diterima
pusat sejumlah SAR, baru dibagikan ke reservasi -- dan pelacakan per
reservasi menjawab "ikut RMT apa, sisa berapa"."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from hw import ledger
from hw.models import Client, Invoice, CashMovement, Reservation, Remittance, RemittanceLine


class LumpSumRemittanceTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        # Superuser bypass role matrix (lihat hw/permissions.py)
        self.user = User.objects.create_user('fin', password='x', is_superuser=True)

        self.client_user = Client.objects.create(name='PT Maju', company='konoz')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-LS-001', customer_name='PT Maju',
            client=self.client_user,
        )
        self.res1 = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R-LS-1', total_sar=60000,
        )
        self.res2 = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R-LS-2', total_sar=40000,
        )
        # client bayar di Surabaya: mengendap masing-masing
        for res, amt in ((self.res1, 60000), (self.res2, 40000)):
            CashMovement.objects.create(
                company='konoz', invoice=self.invoice, client=self.client_user,
                reservation_label=res, from_account='client', to_account='sby',
                amount=amt, currency='SAR', exchange_rate=1, date=date(2026, 2, 1),
            )

    def _login(self):
        self.client.force_login(self.user)

    def test_lump_sum_then_allocate(self):
        self._login()

        # ── 1. Kirim lump-sum: 480.000.000 IDR @ 4800 → 100.000 SAR ──
        sby_before = ledger.kas_surabaya('konoz')
        response = self.client.post(reverse('remittance_new'), {
            'date': '2026-02-10',
            'amount_idr': '480000000',
            'exchange_rate': '4800',
            'received_amount_sar': '100000',
            'lines': '[]',
        })
        self.assertEqual(response.status_code, 302)
        rem = Remittance.objects.get(remittance_number__startswith='RMT-')
        self.assertEqual(rem.received_amount_sar, 100000)
        self.assertEqual(rem.expected_sar, 100000)

        # Kas Surabaya langsung turun walau belum ada alokasi
        self.assertEqual(ledger.kas_surabaya('konoz'), sby_before - 100000)
        # Satu movement tanpa label reservasi
        movs = CashMovement.objects.filter(remittance=rem)
        self.assertEqual(movs.count(), 1)
        self.assertIsNone(movs.first().reservation_label)
        self.assertEqual(rem.unallocated_sar, 100000)

        # ── 2. Alokasikan ke dua reservasi terdekat ──
        response = self.client.post(reverse('remittance_edit', args=[rem.pk]), {
            'date': '2026-02-10',
            'lines': f'[{{"linked_number": "R-LS-1", "invoice_id": {self.invoice.pk}, "amount_sar": 60000}},'
                     f'{{"linked_number": "R-LS-2", "invoice_id": {self.invoice.pk}, "amount_sar": 40000}}]',
        })
        self.assertEqual(response.status_code, 302)

        movs = list(CashMovement.objects.filter(remittance=rem).order_by('id'))
        self.assertEqual(len(movs), 2)  # unlabeled tergantik baris-per-baris
        self.assertEqual({m.reservation_label_id for m in movs}, {self.res1.pk, self.res2.pk})
        self.assertEqual(sum(m.amount for m in movs), 100000)
        self.assertEqual(rem.unallocated_sar, 0)
        self.assertEqual(ledger.kas_surabaya('konoz'), sby_before - 100000)

        # ── 3. Pelacakan: tiap reservasi tahu ikut RMT apa & sisanya nol ──
        rmt_map = ledger.reservation_remittance_map('konoz')
        self.assertEqual(rmt_map['R-LS-1'][0]['rmt_number'], rem.remittance_number)
        self.assertEqual(rmt_map['R-LS-1'][0]['amount_sar'], 60000)
        breakdown = ledger.reservation_cash_breakdown('konoz')
        self.assertEqual(breakdown[self.res1.pk]['mengendap'], 0)
        self.assertEqual(breakdown[self.res2.pk]['sudah_dikirim'], 40000)

    def test_tracking_page_renders(self):
        self._login()
        response = self.client.get(reverse('remittance_tracking'))
        self.assertEqual(response.status_code, 200)
