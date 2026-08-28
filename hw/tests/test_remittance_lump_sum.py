"""Alur lump-sum remittance: uang keluar bank dulu (IDR, kurs), diterima
pusat sejumlah SAR, baru dibagikan ke reservasi -- dan pelacakan per
reservasi menjawab "ikut RMT apa, sisa berapa".

Sejak Fase 7 view tidak lagi menulis shadow CashMovement; jurnal
(posting.resync_remittance) adalah satu-satunya sumber perpindahan kas.
Asersi di sini membaca jurnal + Remittance.unallocated_sar."""
from datetime import date

from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from hw.finance import accounts as coa
from hw.models import Client, Invoice, Reservation, Remittance
from hw.models.choices import Company
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.views.remittance_views import _remittance_send_segments


def _net(**f):
    agg = JournalLine.objects.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or 0) - (agg["c"] or 0)


def _live_remittance_entries(rem):
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)
    return JournalEntry.objects.filter(
        reference_type="Remittance", reference_id=rem.pk,
        entry_type=JournalEntry.TYPE_REMITTANCE, is_reversal=False,
    ).exclude(pk__in=reversed_ids)


class LumpSumRemittanceTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        FinancialPeriod.objects.create(
            name="2026", company=Company.KONOZ,
            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )

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

    def _login(self):
        self.client.force_login(self.user)

    def test_lump_sum_then_allocate(self):
        self._login()

        # ── 1. Kirim lump-sum: 480.000.000 IDR @ 4800 → 100.000 SAR ──
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

        # Lump-sum tanpa label → aggregate kirim Kas SBY → Transit.
        self.assertEqual(rem.unallocated_sar, 100000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 100000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), -100000)

        # ── 2. Alokasikan ke dua reservasi terdekat ──
        response = self.client.post(reverse('remittance_edit', args=[rem.pk]), {
            'date': '2026-02-10',
            'lines': f'[{{"linked_number": "R-LS-1", "invoice_id": {self.invoice.pk}, "amount_sar": 60000}},'
                     f'{{"linked_number": "R-LS-2", "invoice_id": {self.invoice.pk}, "amount_sar": 40000}}]',
        })
        self.assertEqual(response.status_code, 302)

        # Aggregate ter-reverse, send di-re-post per reservasi; total tetap.
        rem.refresh_from_db()
        self.assertEqual(rem.unallocated_sar, 0)
        self.assertEqual(_net(account_id=coa.TRANSIT), 100000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), -100000)

    def test_tracking_page_renders(self):
        self._login()
        response = self.client.get(reverse('remittance_tracking'))
        self.assertEqual(response.status_code, 200)

    def test_mark_received_posts_receive_leg(self):
        """Kaki terima (Kas Pusat masuk, Transit bersih) masuk jurnal saat HQ
        menandai remittance diterima -- bukan hanya ganti status."""
        from ..finance import posting

        self._login()

        # kirim lump-sum lalu alokasikan, seperti alur normal
        self.client.post(reverse('remittance_new'), {
            'date': '2026-02-10',
            'amount_idr': '480000000',
            'exchange_rate': '4800',
            'received_amount_sar': '100000',
            'lines': '[]',
        })
        rem = Remittance.objects.get(remittance_number__startswith='RMT-')
        self.client.post(reverse('remittance_edit', args=[rem.pk]), {
            'date': '2026-02-10',
            'lines': f'[{{"linked_number": "R-LS-1", "invoice_id": {self.invoice.pk}, "amount_sar": 60000}},'
                     f'{{"linked_number": "R-LS-2", "invoice_id": {self.invoice.pk}, "amount_sar": 40000}}]',
        })

        # belum diterima: sisi kirim tercatat, pusat belum menerima apa pun
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)
        self.assertEqual(_net(account_id=coa.TRANSIT), 100000)

        resp = self.client.post(reverse('remittance_mark_received', args=[rem.pk]))
        self.assertEqual(resp.status_code, 302)
        rem.refresh_from_db()
        self.assertEqual(rem.status, Remittance.STATUS_RECEIVED)

        # journal: Kas Pusat +100000, Transit bersih (send 100000 ter-reverse
        # lalu re-post + receive 100000), tanpa selisih kurs/bank fee
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 100000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.EXP_BANKFEE), 0)
        # entry hidup utk rmt ini: 2 kirim (per baris) + 1 terima
        self.assertEqual(_live_remittance_entries(rem).count(), 3)
        # resync ulang idempotent-by-content: tidak dobel-posting, tidak
        # menambah entry apa pun
        before = _live_remittance_entries(rem).count()
        total_entries_before = JournalEntry.objects.count()
        posting.resync_remittance(
            rem, created_by=self.user,
            send_segments=_remittance_send_segments(rem),
            received_sar=100000, touch_receive=True,
        )
        self.assertEqual(_live_remittance_entries(rem).count(), before)
        self.assertEqual(JournalEntry.objects.count(), total_entries_before)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 100000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)