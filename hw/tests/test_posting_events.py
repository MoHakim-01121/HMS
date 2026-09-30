"""Fase 3 — posting per-event di hw/finance/posting.py."""
from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_service_line, set_line_total
from datetime import date

from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import posting
from hw.finance.hashing import verify_chain
from hw.models import (
    CancellationPenalty, Client, PaymentAllocation,
)
from hw.finance_helpers import create_payment_record, FinanceError
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


def _net(**f):
    agg = JournalLine.objects.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or 0) - (agg["c"] or 0)


class PostingTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fin", password="x")
        FinancialPeriod.objects.create(
            name="2045",            date_from=date(2045, 1, 1), date_to=date(2045, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Uji")
        self.invoice = make_invoice(
 invoice_type="hotel", invoice_number="INV-P1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2045, 1, 5),
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number="R-P1", total_sar=100000,
        )


class InvoiceChargeTests(PostingTestBase):
    def test_charge_posts_ar_and_income(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.assertEqual(_net(account_id=coa.AR, invoice=self.invoice), 100000)
        self.assertEqual(_net(account_id=coa.INC_HOTEL, invoice=self.invoice), -100000)
        self.assertEqual(verify_chain(), [])

    def test_charge_is_idempotent_by_content(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.assertEqual(
            JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_CHARGE).count(), 1
        )

    def test_revision_reverses_and_reposts(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.res = set_line_total(self.res, 120000)
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        # net AR for invoice reflects the new total, old charge reversed
        self.assertEqual(_net(account_id=coa.AR, invoice=self.invoice), 120000)
        self.assertEqual(verify_chain(), [])

    def test_void_reverses_all(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        posting.void_invoice_charge(
            self.invoice, created_by=self.user, entry_date=date(2045, 6, 1),
        )
        self.assertEqual(_net(account_id=coa.AR, invoice=self.invoice), 0)

    def test_service_invoice_uses_service_income(self):
        inv = make_invoice(
 invoice_type="visa", invoice_number="SVC-P1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2045, 2, 1),
        )
        make_service_line(invoice=inv, name="Visa", qty=2, price=15000)
        posting.post_invoice_charge(inv, created_by=self.user)
        self.assertEqual(_net(account_id=coa.INC_SERVICE, invoice=inv), -30000)


class PaymentPostingTests(PostingTestBase):
    def _payment(self, amount=100000, received_in="sby"):
        return create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2045, 2, 1),
            amount=amount, method="transfer", created_by=self.user, received_in=received_in,
        )

    def test_post_payment_debits_cash_credits_ar(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        p = self._payment()
        posting.post_payment(p, created_by=self.user)
        self.assertEqual(_net(account_id=coa.CASH_SBY, invoice=self.invoice), 100000)
        self.assertEqual(_net(account_id=coa.AR, invoice=self.invoice), 0)  # 100k charge - 100k paid
        self.assertEqual(verify_chain(), [])

    def test_post_payment_idempotent(self):
        p = self._payment()
        a = posting.post_payment(p, created_by=self.user)
        b = posting.post_payment(p, created_by=self.user)
        self.assertEqual(a.pk, b.pk)

    def test_jakarta_payment_hits_kas_jakarta(self):
        p = self._payment(received_in="jkt")
        posting.post_payment(p, created_by=self.user)
        self.assertEqual(_net(account_id=coa.CASH_JKT), 100000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), 0)

    def test_payment_from_credit_requires_balance(self):
        p = self._payment()
        with self.assertRaises(posting.InsufficientCreditError):
            posting.post_payment_from_credit(p, created_by=self.user)

    def test_allocate_payment_writes_rows_no_journal(self):
        p = self._payment()
        before = JournalEntry.objects.count()
        posting.allocate_payment(p, [(self.res, 100000)], created_by=self.user)
        self.assertEqual(PaymentAllocation.objects.filter(payment=p).count(), 1)
        self.assertEqual(JournalEntry.objects.count(), before)

    def test_allocate_over_amount_rejected(self):
        p = self._payment(amount=50000)
        with self.assertRaises(FinanceError):
            posting.allocate_payment(p, [(self.res, 60000)], created_by=self.user)


class KasMovementTests(PostingTestBase):
    def test_refund_from_credit(self):
        # give the client a credit balance first via an adjustment
        posting.post_adjustment(
            lines=[
                {"account": coa.CASH_PUSAT, "debit": 20000},
                {"account": coa.CUST_CREDIT, "credit": 20000, "client": self.client_obj.pk},
            ],
            description="setoran titipan", entry_date=date(2045, 1, 3), created_by=self.user,
        )
        posting.post_refund(
            self.client_obj, from_location="pusat", amount_sar=20000,
            created_by=self.user, entry_date=date(2045, 1, 10),
        )
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)

    def test_fund_transfer_keeps_client_receivable_total(self):
        r2 = make_hotel_line(
            invoice=self.invoice, reservation_number="R-P2", total_sar=0,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        before = _net(account_id=coa.AR, client_id=self.client_obj.pk)
        posting.post_fund_transfer(
            self.client_obj, from_reservation=self.res, to_reservation=r2,
            amount_sar=30000, created_by=self.user, entry_date=date(2045, 4, 1),
        )
        self.assertEqual(_net(account_id=coa.AR, client_id=self.client_obj.pk), before)
        self.assertEqual(_net(account_id=coa.AR, reservation=r2), 30000)

    def test_remittance_send_then_receive_with_fee(self):
        from hw.models import Remittance
        rmt = Remittance.objects.create(
 date=date(2045, 5, 1), remittance_number="RMT-P1",
        )
        posting.post_remittance_send(
            rmt, from_location="sby", amount_sar=50000, created_by=self.user,
        )
        self.assertEqual(_net(account_id=coa.CASH_SBY), -50000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 50000)
        posting.post_remittance_receive(
            rmt, expected_sar=50000, received_sar=49000, created_by=self.user,
        )
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 49000)
        self.assertEqual(_net(account_id=coa.EXP_BANKFEE), 1000)
        self.assertEqual(verify_chain(), [])


class PenaltyChargeTests(PostingTestBase):
    def test_penalty_charge_posts(self):
        cl = make_cl(
 client=self.client_obj, hotel_name="H", guest_name="G",
            confirmation_number="CL-P1",
        )
        pen = CancellationPenalty.objects.create(
            cl=cl, penalty_number="PNL-P1",
            cancellation_date=date(2045, 3, 1), penalty_amount=5000,
        )
        from hw.finance.penalty_billing import bill_penalty
        invoice, created = bill_penalty(pen, user=self.user)   # reservation not invoiced yet
        self.assertTrue(created)
        self.assertEqual(invoice.total_sar, 5000)
        self.assertEqual(_net(account_id=coa.AR, penalty=pen), 5000)
        self.assertEqual(_net(account_id=coa.INC_PENALTY, penalty=pen), -5000)


class RemittanceResyncTests(PostingTestBase):
    def _remittance(self):
        from hw.models import Remittance
        return Remittance.objects.create(
 date=date(2045, 5, 1), remittance_number="RMT-R",
        )

    def test_send_per_reservation_then_receive(self):
        rmt = self._remittance()
        segments = [
            {"reservation": self.res, "invoice": self.invoice.pk,
             "client": self.client_obj.pk, "amount_sar": 30000},
            {"reservation": None, "invoice": None, "client": None, "amount_sar": 20000},
        ]
        posting.resync_remittance(rmt, created_by=self.user, send_segments=segments)
        self.assertEqual(_net(account_id=coa.CASH_SBY), -50000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 50000)
        # dimensi reservasi tercatat supaya mengendap_per_reservation turun
        self.assertEqual(_net(account_id=coa.CASH_SBY, reservation=self.res), -30000)

        # mark_received: resync ulang dengan segmen kirim yg sama + sisi terima
        posting.resync_remittance(
            rmt, created_by=self.user, send_segments=segments,
            received_sar=49000, touch_receive=True,
        )
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 49000)
        self.assertEqual(_net(account_id=coa.EXP_BANKFEE), 1000)
        self.assertEqual(verify_chain(), [])

    def test_resync_is_idempotent_by_content(self):
        rmt = self._remittance()
        segments = [{"amount_sar": 30000}]
        posting.resync_remittance(rmt, created_by=self.user, send_segments=segments)
        total_after_first = JournalEntry.objects.filter(reference_id=rmt.pk).count()
        posting.resync_remittance(rmt, created_by=self.user, send_segments=segments)
        # hanya 1 entry kirim "hidup" (belum di-reverse) tersisa
        reversed_ids = JournalEntry.objects.filter(
            reverses__isnull=False,
        ).values_list("reverses_id", flat=True)
        self.assertEqual(
            JournalEntry.objects.filter(
                reference_type="Remittance", reference_id=rmt.pk,
                entry_type=JournalEntry.TYPE_REMITTANCE, is_reversal=False,
            ).exclude(pk__in=reversed_ids).count(), 1
        )
        # idempotent-by-content sesungguhnya: resync kedua tidak menambah
        # entry apa pun (tidak ada reversal+repost churn)
        self.assertEqual(
            JournalEntry.objects.filter(reference_id=rmt.pk).count(),
            total_after_first,
        )

    def test_edit_resync_keeps_send_and_receive_consistent(self):
        rmt = self._remittance()
        posting.resync_remittance(rmt, created_by=self.user, send_segments=[{"amount_sar": 40000}])
        posting.resync_remittance(
            rmt, created_by=self.user, send_segments=[{"amount_sar": 40000}],
            received_sar=38000, touch_receive=True,
        )
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 38000)

        # edit: nominal kirim berubah, terima tetap; resync dengan kedua sisi
        posting.resync_remittance(
            rmt, created_by=self.user, send_segments=[{"amount_sar": 45000}],
            received_sar=38000, touch_receive=True,
        )
        self.assertEqual(_net(account_id=coa.CASH_SBY), -45000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 38000)
        self.assertEqual(_net(account_id=coa.EXP_BANKFEE), 7000)
        self.assertEqual(verify_chain(), [])

    def test_unreceived_revert_reverses_receive_without_repost(self):
        rmt = self._remittance()
        posting.resync_remittance(rmt, created_by=self.user, send_segments=[{"amount_sar": 40000}])
        posting.resync_remittance(
            rmt, created_by=self.user, send_segments=[{"amount_sar": 40000}],
            received_sar=39000, touch_receive=True,
        )
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 39000)

        # boleh dibuka/diedit lagi; sisi terima dibalik tanpa re-post
        posting.resync_remittance(
            rmt, created_by=self.user, send_segments=[{"amount_sar": 40000}],
            received_sar=None, touch_receive=True,
        )
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)
        self.assertEqual(_net(account_id=coa.TRANSIT), 40000)
        self.assertEqual(verify_chain(), [])
