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
from hw.models import Client, Invoice, Reservation, Remittance, RemittanceLine
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
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )

        # Superuser bypass role matrix (lihat hw/permissions.py)
        self.user = User.objects.create_user('fin', password='x', is_superuser=True)

        self.client_user = Client.objects.create(name='PT Maju',)
        self.invoice = Invoice.objects.create(
 invoice_type='hotel',
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
        # received_amount_sar TIDAK dikirim (2026-09-14: form pembuatan tak
        # lagi punya field itu -- penerimaan HQ dicatat lewat Settlement,
        # bukan di sini).
        response = self.client.post(reverse('remittance_new'), {
            'date': '2026-02-10',
            'amount_idr': '480000000',
            'exchange_rate': '4800',
            'lines': '[]',
        })
        self.assertEqual(response.status_code, 302)
        rem = Remittance.objects.get(remittance_number__startswith='RMT-')
        self.assertIsNone(rem.received_amount_sar)
        self.assertEqual(rem.expected_sar, 100000)

        # Lump-sum tanpa label → aggregate kirim Kas SBY → Transit. Basis
        # unallocated_sar jatuh ke expected_sar (bukan received_amount_sar,
        # yang sekarang None) -- progres alokasi tetap terlacak sebelum ada
        # settlement sama sekali.
        self.assertEqual(rem.unallocated_sar, 100000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 100000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), -100000)

        # ── 2. Edit tidak lagi membagi transfer lump-sum ke reservasi ──
        lines = (f'[{{"linked_number": "R-LS-1", "invoice_id": {self.invoice.pk}, "amount_sar": 60000}},'
                 f'{{"linked_number": "R-LS-2", "invoice_id": {self.invoice.pk}, "amount_sar": 40000}}]')
        response = self.client.post(reverse('remittance_edit', args=[rem.pk]), {
            'date': '2026-02-10', 'lines': lines,
        })
        self.assertEqual(response.status_code, 302)
        rem.refresh_from_db()
        self.assertEqual(rem.unallocated_sar, 100000)

        # ── 3. Alokasi terjadi saat Pusat mencatat penerimaan ──
        from hw.finance import posting
        from hw.finance_helpers import create_payment_record
        for res, amount in ((self.res1, 60000), (self.res2, 40000)):
            p = create_payment_record(
                invoice=self.invoice, client=self.client_user, payment_date=date(2026, 2, 1),
                amount=amount, method='transfer', created_by=self.user, received_in='sby', reservation=res,
            )
            posting.post_payment(p, created_by=self.user)
        response = self.client.post(reverse('remittance_record_receipt', args=[rem.pk]), {
            'received_amount_sar': '100000', 'received_date': '2026-02-12', 'allocations': lines,
        })
        self.assertEqual(response.status_code, 302)

        # Jurnal kirim tetap lump-sum; alokasi = reklasifikasi Kas SBY per reservasi.
        rem.refresh_from_db()
        self.assertEqual(rem.unallocated_sar, 0)
        self.assertEqual(rem.status, Remittance.STATUS_RECEIVED)
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.CASH_SBY), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 100000)

    def test_old_tracking_and_recap_urls_open_their_tab(self):
        self._login()
        self.assertRedirects(self.client.get(reverse('remittance_tracking')), '/remittance/?tab=tracking',
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('remittance_recap')), '/remittance/?tab=recap',
                             fetch_redirect_response=False)

    def test_list_computes_only_the_active_tab(self):
        self._login()
        props = self.client.get('/remittance/?tab=tracking', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['tab'], 'tracking')
        self.assertIsNotNone(props['tracking'])
        self.assertIsNone(props['monthly'])
        self.assertEqual(props['remittances'], [])

    def test_new_ignores_received_amount_sar_even_if_posted(self):
        """Defense-in-depth: form pembuatan tak lagi mengirim field ini, tapi
        kalaupun ada yang POST manual, backend harus tetap mengabaikannya --
        satu-satunya jalur mencatat penerimaan sekarang Settlement."""
        self._login()
        response = self.client.post(reverse('remittance_new'), {
            'date': '2026-02-10',
            'amount_idr': '480000000',
            'exchange_rate': '4800',
            'received_amount_sar': '999999',
            'lines': '[]',
        })
        self.assertEqual(response.status_code, 302)
        rem = Remittance.objects.get(remittance_number__startswith='RMT-')
        self.assertIsNone(rem.received_amount_sar)

    def test_list_exposes_can_mark_received_only_for_legacy_remittances(self):
        self._login()
        legacy = Remittance.objects.create(
            remittance_number='RMT-LEGACY', date=date(2026, 2, 1), received_amount_sar=50000,
        )
        new_style = Remittance.objects.create(
            remittance_number='RMT-NEW', date=date(2026, 2, 2),
        )
        resp = self.client.get(reverse('remittance_list'), HTTP_X_INERTIA='true')
        rows = {r['id']: r['can_mark_received'] for r in resp.json()['props']['remittances']}
        self.assertTrue(rows[legacy.pk])
        self.assertFalse(rows[new_style.pk])

    def test_mark_received_posts_receive_leg(self):
        """Kaki terima (Kas Pusat masuk, Transit bersih) masuk jurnal saat HQ
        menandai remittance diterima -- bukan hanya ganti status.

        `remittance_mark_received` (jalur lama) sekarang cuma bisa dicapai
        lewat remittance yang SUDAH punya received_amount_sar -- form
        pembuatan/edit tak lagi bisa mengisinya untuk remittance baru
        (2026-09-14, lihat test_lump_sum_then_allocate). Fixture di sini
        mensimulasikan data lama itu langsung lewat ORM + resync manual,
        supaya jalur legacy post_remittance_receive/resync_remittance masih
        tertes tanpa memakai view yang sekarang sengaja menolaknya."""
        from ..finance import posting

        self._login()

        rem = Remittance.objects.create(
            remittance_number=Remittance.generate_number(),
            date=date(2026, 2, 10),
            amount_idr=480000000, exchange_rate=4800,
            received_amount_sar=100000,
        )
        RemittanceLine.objects.create(
            remittance=rem, invoice=self.invoice, linked_number='R-LS-1', amount_sar=60000,
        )
        RemittanceLine.objects.create(
            remittance=rem, invoice=self.invoice, linked_number='R-LS-2', amount_sar=40000,
        )
        posting.resync_remittance(
            rem, created_by=self.user, send_segments=_remittance_send_segments(rem),
        )

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