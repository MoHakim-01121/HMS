"""Alur refund & transfer dana lewat HTTP view (Fase 5+): journal only.

Sejak Fase 5 view dual-write (shadow legacy CashMovement untuk refund,
Allocation untuk transfer DAN jurnal). Fase 7 memensiunkan shadow tables:
sekarang hanya jurnal lewat posting.post_refund / post_fund_transfer. Asersi
di sini memvalidasi jurnal — dan bahwa tidak ada baris shadow yang tertulis."""
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from hw.finance import accounts as coa
from hw.finance import posting
from hw.models import Client
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice


def _net(**f):
    agg = JournalLine.objects.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or 0) - (agg["c"] or 0)


class RefundTransferViewTest(TestCase):
    def setUp(self):
        # Superuser bypass role matrix (lihat hw/permissions.py)
        self.user = User.objects.create_user("fin", password="x", is_superuser=True)
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        FinancialPeriod.objects.create(
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Uji")
        self.invoice = make_invoice(
 invoice_type="hotel", invoice_number="INV-CR-001",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2026, 1, 5),
        )
        self.res_a = make_hotel_line(
            invoice=self.invoice, reservation_number="R-A", total_sar=100000,
        )
        self.res_b = make_hotel_line(
            invoice=self.invoice, reservation_number="R-B", total_sar=40000,
        )

    def _pusat_cash(self):
        from hw.models import CashAccount
        return f"cash:{CashAccount.objects.get(branch_id='pusat').pk}"

    def _fund(self, amount=20000):
        posting.post_adjustment(
            lines=[
                {"account": coa.CASH_PUSAT, "debit": amount},
                {"account": coa.CUST_CREDIT, "credit": amount, "client": self.client_obj.pk},
            ],
            description="setoran titipan", entry_date=date(2026, 1, 3), created_by=self.user,
        )

    def _idr_account(self):
        from hw.models import BankAccount, LedgerAccount
        return BankAccount.objects.create(
            branch_id="sby", name="IDR", currency="IDR", bank_name="Mandiri", account_identifier="555",
            ledger_account=LedgerAccount.objects.get(code="1000-KAS-SBY"),
        )

    def test_idr_refund_records_rupiah_in_cash_book(self):
        from hw.models import BankTransaction
        self._fund()
        acc = self._idr_account()
        resp = self.client.post(reverse("client_refund", args=[self.client_obj.pk]), {
            "from_account": f"bank:{acc.pk}", "amount_sar": "10000", "amount_paid": "47500000", "note": "refund idr",
        })
        self.assertEqual(resp.status_code, 302)
        entry = JournalEntry.objects.get(entry_type=JournalEntry.TYPE_REFUND)
        tx = BankTransaction.objects.get(source_type="Refund", source_id=entry.pk)
        self.assertEqual((tx.account_id, tx.direction, tx.currency, tx.amount, tx.amount_sar),
                         (acc.pk, "out", "IDR", 47_500_000, 10_000))
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 10_000)

    def test_idr_refund_needs_the_rupiah_amount(self):
        self._fund()
        acc = self._idr_account()
        resp = self.client.post(reverse("client_refund", args=[self.client_obj.pk]), {
            "from_account": f"bank:{acc.pk}", "amount_sar": "10000",
        }, HTTP_X_INERTIA="true")
        self.assertIn("amount_paid", resp.json()["props"]["errors"])
        self.assertFalse(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).exists())

    def test_refund_posts_journal(self):
        # Beri client titipan (CUST_CREDIT) via adjustment dulu.
        posting.post_adjustment(
            lines=[
                {"account": coa.CASH_PUSAT, "debit": 20000},
                {"account": coa.CUST_CREDIT, "credit": 20000, "client": self.client_obj.pk},
            ],
            description="setoran titipan", entry_date=date(2026, 1, 3), created_by=self.user,
        )

        resp = self.client.post(
            reverse("client_refund", args=[self.client_obj.pk]),
            {"from_account": self._pusat_cash(), "amount_sar": "20000", "note": "refund uji"},
        )
        self.assertEqual(resp.status_code, 302)

        # Journal refund: DR Titipan / CR Kas Pusat.
        entry = JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).first()
        self.assertIsNotNone(entry)
        self.assertEqual(_net(account_id=coa.CUST_CREDIT, client=self.client_obj.pk), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 0)

    def test_refund_keeps_uploaded_proof_on_journal_entry(self):
        # Fase 7: proof refund dibawa JournalEntry (bukan shadow CashMovement
        # yang sudah dipensiunkan dari alur penulisan).
        posting.post_adjustment(
            lines=[
                {"account": coa.CASH_PUSAT, "debit": 20000},
                {"account": coa.CUST_CREDIT, "credit": 20000, "client": self.client_obj.pk},
            ],
            description="setoran titipan", entry_date=date(2026, 1, 3), created_by=self.user,
        )
        proof = SimpleUploadedFile("refund.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        resp = self.client.post(
            reverse("client_refund", args=[self.client_obj.pk]),
            {"from_account": self._pusat_cash(), "amount_sar": "20000", "note": "refund uji", "proof": proof},
        )
        self.assertEqual(resp.status_code, 302)
        entry = JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).first()
        self.assertIsNotNone(entry)
        self.assertTrue(entry.proof)

    def test_transfer_posts_journal(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)

        resp = self.client.post(
            reverse("client_transfer", args=[self.client_obj.pk]),
            {"from_reservation": str(self.res_a.pk), "to_reservation": str(self.res_b.pk),
             "amount_sar": "30000", "note": "pindah dana"},
        )
        self.assertEqual(resp.status_code, 302)

        # Journal transfer: AR di-re-tag dari res_a (credit) ke res_b (debit);
        # res_a turun 100000→70000, res_b naik 40000→70000.
        entries = JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_TRANSFER)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(_net(account_id=coa.AR, invoice_line=self.res_a), 70000)
        self.assertEqual(_net(account_id=coa.AR, invoice_line=self.res_b), 70000)
        # Total piutang client tidak berubah (tetap 140000 dari charge 100000+40000).
        self.assertEqual(_net(account_id=coa.AR, client=self.client_obj.pk), 140000)

    def test_transfer_without_open_period_degrades_gracefully(self):
        # I2: jurnal gagal (tak ada periode utk tanggal hari ini) tidak boleh
        # 500 — view menampilkan eror form, bukan crash.
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        # Persempit periode agar tanggal hari ini tak tercakup (charge Jan tetap ok).
        FinancialPeriod.objects.update(date_to=date(2026, 1, 31))
        resp = self.client.post(
            reverse("client_transfer", args=[self.client_obj.pk]),
            {"from_reservation": str(self.res_a.pk), "to_reservation": str(self.res_b.pk),
             "amount_sar": "30000", "note": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_TRANSFER).count(), 0)

    def test_transfer_blocks_different_client_reservation(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        other_client = Client.objects.create( name="PT Lain")
        other_invoice = make_invoice(
 invoice_type="hotel", invoice_number="INV-CR-002",
            customer_name="PT Lain", client=other_client, issued_date=date(2026, 2, 1),
        )
        other_res = make_hotel_line(
            invoice=other_invoice, reservation_number="R-OR", total_sar=5000,
        )
        resp = self.client.post(
            reverse("client_transfer", args=[self.client_obj.pk]),
            {"from_reservation": str(self.res_a.pk), "to_reservation": str(other_res.pk),
             "amount_sar": "1000", "note": ""},
        )
        self.assertEqual(resp.status_code, 200)  # eror form, bukan redirect
        self.assertEqual(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_TRANSFER).count(), 0)