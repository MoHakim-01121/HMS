"""Alur refund deposit lewat HTTP view: journal only.

"Move Funds" (pindah dana antar reservasi lewat jurnal tanpa dokumen) sudah
dipensiunkan -- uang dipindah antar reservasi lewat realokasi pembayaran
(test_payment_reallocate_controls). Asersi di sini memvalidasi jurnal refund."""
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q, Sum
from django.test import TestCase
from django.urls import reverse

from hw.finance import accounts as coa
from hw.finance import posting
from hw.models import Client
from hw.finance.accounts import cash_ledger_for
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_cash, make_hotel_line, make_invoice


def _net(**f):
    qs = JournalLine.objects.all()
    if "account_id" in f:  # kas cabang = akun induk + akun anak per mata uang
        code = f.pop("account_id")
        qs = qs.filter(Q(account_id=code) | Q(account__parent_id=code))
    agg = qs.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
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

    def _approve_refund(self):
        """The refund form records a pending document; approving it posts the
        journal (this superuser is an admin, who may approve their own)."""
        from hw.models import ClientRefund
        refund = ClientRefund.objects.get(status='pending')
        self.assertFalse(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).exists())
        self.client.post(reverse("client_refund_confirm", args=[refund.pk]))

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
        from hw.models import CashAccount
        fund_cash(CashAccount.objects.get(branch_id='pusat'), amount)

    def _idr_account(self):
        from hw.models import BankAccount
        acc = BankAccount.objects.create(
            branch_id="sby", name="IDR", currency="IDR", bank_name="Mandiri", account_identifier="555",
            ledger_account_id=cash_ledger_for('sby', 'IDR'),
        )
        fund_cash(acc, 100_000_000)
        return acc

    def test_idr_refund_records_rupiah_in_cash_book(self):
        from hw.models import BankTransaction
        self._fund()
        acc = self._idr_account()
        resp = self.client.post(reverse("client_refund", args=[self.client_obj.pk]), {
            "from_account": f"bank:{acc.pk}", "amount_sar": "10000", "amount_paid": "47500000", "note": "refund idr",
        })
        self.assertEqual(resp.status_code, 302)
        self._approve_refund()
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
        self._fund()

        resp = self.client.post(
            reverse("client_refund", args=[self.client_obj.pk]),
            {"from_account": self._pusat_cash(), "amount_sar": "20000", "note": "refund uji"},
        )
        self.assertEqual(resp.status_code, 302)
        self._approve_refund()

        # Journal refund: DR Titipan / CR Kas Pusat.
        entry = JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).first()
        self.assertIsNotNone(entry)
        self.assertEqual(_net(account_id=coa.CUST_CREDIT, client=self.client_obj.pk), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 0)

    def test_refund_keeps_uploaded_proof_on_journal_entry(self):
        # Fase 7: proof refund dibawa JournalEntry (bukan shadow CashMovement
        # yang sudah dipensiunkan dari alur penulisan).
        self._fund()
        proof = SimpleUploadedFile("refund.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        resp = self.client.post(
            reverse("client_refund", args=[self.client_obj.pk]),
            {"from_account": self._pusat_cash(), "amount_sar": "20000", "note": "refund uji", "proof": proof},
        )
        self.assertEqual(resp.status_code, 302)
        self._approve_refund()
        entry = JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND).first()
        self.assertIsNotNone(entry)
        self.assertTrue(entry.proof)
