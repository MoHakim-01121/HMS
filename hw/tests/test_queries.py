"""Fase 4 — hw/finance/queries.py derivasi dari JournalLine."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance import queries as q
from hw.models import Client, Invoice, Reservation
from hw.models.choices import Company
from hw.finance_helpers import create_payment_record
from hw.models.period import FinancialPeriod


class QueriesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fin", password="x")
        FinancialPeriod.objects.create(
            name="2046", company=Company.KONOZ,
            date_from=date(2046, 1, 1), date_to=date(2046, 12, 31),
        )
        self.client_obj = Client.objects.create(company="konoz", name="PT Uji")
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel", invoice_number="INV-Q1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 5),
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number="R-Q1", total_sar=100000,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _pay(self, amount, received_in="sby"):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2046, 2, 1),
            amount=amount, method="transfer", created_by=self.user, received_in=received_in,
            reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)
        return p

    def test_invoice_charged_and_paid(self):
        self.assertEqual(q.invoice_charged_sar(self.invoice.id), 100000)
        self.assertEqual(q.invoice_paid_sar(self.invoice.id), 0)
        self._pay(60000)
        self.assertEqual(q.invoice_paid_sar(self.invoice.id), 60000)
        self.assertEqual(q.invoice_outstanding_sar(self.invoice.id), 40000)

    def test_invoice_paid_map(self):
        self._pay(30000)
        self.assertEqual(q.invoice_paid_map([self.invoice.id]), {self.invoice.id: 30000})

    def test_client_receivable_and_credit(self):
        self.assertEqual(q.client_receivable(self.client_obj.id), 100000)
        self._pay(100000)
        self.assertEqual(q.client_receivable(self.client_obj.id), 0)
        self.assertEqual(q.client_credit_balance(self.client_obj.id), 0)

    def test_kas_and_mengendap(self):
        self._pay(70000, received_in="sby")
        self.assertEqual(q.kas_surabaya(Company.KONOZ), 70000)
        self.assertEqual(q.mengendap_per_reservation(self.res.id), 70000)
        self.assertEqual(q.kewajiban_kirim_sby(Company.KONOZ), 70000)

    def test_client_statement_running_balance(self):
        self._pay(40000)
        st = q.client_statement(self.client_obj.id)
        self.assertEqual(st["closing_balance"], 60000)  # 100k charge - 40k paid
        self.assertEqual(st["rows"][0]["balance"], 100000)

    def test_trial_balance_zero(self):
        self._pay(55000)
        tb = q.trial_balance(company=Company.KONOZ)
        self.assertTrue(tb["balanced"])
        self.assertEqual(tb["total_debit"], tb["total_credit"])
