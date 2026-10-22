"""Alur lump-sum remittance: uang keluar bank dulu (IDR, kurs), diterima
pusat sejumlah SAR, baru dibagikan ke reservasi -- dan pelacakan per
reservasi menjawab "ikut RMT apa, sisa berapa".

Sejak Fase 7 view tidak lagi menulis shadow CashMovement; jurnal
(posting.resync_remittance) adalah satu-satunya sumber perpindahan kas.
Asersi di sini membaca jurnal + Remittance.unallocated_sar."""
from datetime import date

from django.db.models import Q, Sum
from django.test import TestCase
from django.urls import reverse

from hw.finance import accounts as coa
from hw.finance.accounts import cash_ledger_for
from hw.models import Client, Remittance
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_cash, fund_ledger, make_hotel_line, make_invoice


def _net(**f):
    qs = JournalLine.objects.all()
    if "account_id" in f:  # kas cabang = akun induk + akun anak per mata uang
        code = f.pop("account_id")
        qs = qs.filter(Q(account_id=code) | Q(account__parent_id=code))
    agg = qs.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or 0) - (agg["c"] or 0)


def _live_remittance_entries(rem):
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list("reverses_id", flat=True)
    return JournalEntry.objects.filter(
        source_remittance=rem.pk,
        entry_type=JournalEntry.TYPE_REMITTANCE, reverses__isnull=True,
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
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-LS-001', customer_name='PT Maju',
            client=self.client_user,
        )
        self.res1 = make_hotel_line(
            invoice=self.invoice, reservation_number='R-LS-1', total_sar=60000,
        )
        self.res2 = make_hotel_line(
            invoice=self.invoice, reservation_number='R-LS-2', total_sar=40000,
        )
        from hw.models import BankAccount
        # New transfers must name the IDR account the money left from.
        self.idr_account = BankAccount.objects.create(
            branch_id='sby', name='IDR', currency='IDR', bank_name='Mandiri', account_identifier='777',
            ledger_account_id=cash_ledger_for('sby', 'IDR'),
        )
        fund_cash(self.idr_account, 1_000_000_000)
        # Rupiah di buku besar dengan kurs kirim 4.800: tanpa laba/rugi kurs.
        fund_ledger(self.idr_account, 960_000_000, 200_000, date(2026, 1, 1))

    def _login(self):
        self.client.force_login(self.user)

    def test_lump_sum_then_allocate(self):
        self._login()

        # ── 1. Kirim lump-sum: 480.000.000 IDR @ 4800 → 100.000 SAR ──
        # received_amount_sar TIDAK dikirim (2026-09-14: form pembuatan tak
        # lagi punya field itu -- penerimaan HQ dicatat lewat Settlement,
        # bukan di sini).
        response = self.client.post(reverse('remittance_new'), {
            'from_bank_account': str(self.idr_account.pk),
            'date': '2026-02-10',
            'amount_idr': '480000000',
            'exchange_rate': '4800',
            'lines': '[]',
        })
        self.assertEqual(response.status_code, 302)
        rem = Remittance.objects.get(remittance_number__startswith='RMT-')
        self.assertEqual(rem.expected_sar, 100000)

        # Lump-sum tanpa label → aggregate kirim Kas SBY → Transit. Basis
        # unallocated_sar jatuh ke expected_sar (bukan received_amount_sar,
        # yang sekarang None) -- progres alokasi tetap terlacak sebelum ada
        # settlement sama sekali.
        self.assertEqual(rem.unallocated_sar, 100000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 100000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), 200000 - 100000)   # ledger funding − sent

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
        self.assertEqual(_net(account_id=coa.CASH_SBY), 200000)   # only the ledger funding is left
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
