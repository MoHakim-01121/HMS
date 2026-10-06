"""Fase 3 — posting per-event di hw/finance/posting.py."""
from hw.tests.factories import fund_cash, make_account, make_cl, make_hotel_line, make_invoice, make_remittance, make_service_line, set_line_total
from datetime import date

from django.contrib.auth.models import User
from django.db.models import Q, Sum
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
    qs = JournalLine.objects.all()
    if "account_id" in f:  # kas cabang = akun induk + akun anak per mata uang
        code = f.pop("account_id")
        qs = qs.filter(Q(account_id=code) | Q(account__parent_id=code))
    agg = qs.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
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
        posting.post_invoice_charge(self.invoice, created_by=self.user)
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
        from hw.models import CashAccount
        from hw.tests.factories import refund_now
        pusat = CashAccount.objects.get(branch_id="pusat", currency="SAR")
        fund_cash(pusat, 20000)
        refund_now(
            self.client_obj, account=pusat,
            amount_sar=20000, amount_paid=20000, created_by=self.user, refund_date=date(2045, 1, 10),
        )
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 0)
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 0)

    def test_remittance_send_then_receive_with_fee(self):
        from hw.finance import settlement_service
        rmt = make_remittance(
            date=date(2045, 5, 1), remittance_number="RMT-P1", from_account=make_account('sby', 'SAR'),
        )
        posting.post_remittance_send(
            rmt, amount_sar=50000, created_by=self.user,
        )
        self.assertEqual(_net(account_id=coa.CASH_SBY), -50000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 50000)
        settlement_service.add_settlement(
            rmt, received_amount_sar=49000, received_date=date(2045, 5, 2), created_by=self.user,
        )
        settlement_service.close_remittance_diff(rmt, created_by=self.user, entry_date=date(2045, 5, 3))
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
    """Satu jalur: jurnal kirim (Transit / rekening asal) mengikuti transfernya,
    penerimaan Pusat lewat settlement_service, selisihnya ditutup terpisah."""

    def _remittance(self, sar=50000):
        return make_remittance(
            date=date(2045, 5, 1), remittance_number="RMT-R", amount_sent=sar * 4750,
        )

    def test_send_then_receive_then_close_difference(self):
        from hw.finance import settlement_service
        rmt = self._remittance()
        posting.resync_remittance(rmt, created_by=self.user)
        source = rmt.from_account.ledger_account_id
        self.assertEqual(_net(account_id=source), -50000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 50000)

        settlement_service.add_settlement(
            rmt, received_amount_sar=49000, received_date=date(2045, 5, 3), created_by=self.user,
        )
        self.assertEqual(_net(account_id=coa.CASH_PUSAT), 49000)
        self.assertEqual(rmt.status, "pending")
        settlement_service.close_remittance_diff(rmt, created_by=self.user, entry_date=date(2045, 5, 4))
        self.assertEqual(_net(account_id=coa.TRANSIT), 0)
        self.assertEqual(_net(account_id=coa.EXP_BANKFEE), 1000)
        self.assertEqual(rmt.status, "received")
        self.assertEqual(verify_chain(), [])

    def test_resync_is_idempotent_by_content(self):
        rmt = self._remittance()
        posting.resync_remittance(rmt, created_by=self.user)
        total_after_first = JournalEntry.objects.filter(source_remittance=rmt.pk).count()
        posting.resync_remittance(rmt, created_by=self.user)
        self.assertEqual(JournalEntry.objects.filter(source_remittance=rmt.pk).count(), total_after_first)

    def test_changing_the_amount_reposts_the_send_leg(self):
        rmt = self._remittance()
        posting.resync_remittance(rmt, created_by=self.user)
        rmt.amount_sent = 45000 * 4750
        rmt.save(update_fields=["amount_sent"])
        posting.resync_remittance(rmt, created_by=self.user)
        self.assertEqual(_net(account_id=rmt.from_account.ledger_account_id), -45000)
        self.assertEqual(_net(account_id=coa.TRANSIT), 45000)
        self.assertEqual(verify_chain(), [])

