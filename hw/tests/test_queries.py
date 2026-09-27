"""Fase 4 — hw/finance/queries.py derivasi dari JournalLine."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance import queries as q
from hw.models import Client, Invoice, Reservation, ServiceItem
from hw.finance_helpers import create_payment_record
from hw.models.period import FinancialPeriod


class QueriesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fin", password="x")
        FinancialPeriod.objects.create(
            name="2046",            date_from=date(2046, 1, 1), date_to=date(2046, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Uji")
        self.invoice = Invoice.objects.create(
 invoice_type="hotel", invoice_number="INV-Q1",
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
        self.assertEqual(q.kas_surabaya(), 70000)
        self.assertEqual(q.mengendap_per_reservation(self.res.id), 70000)
        self.assertEqual(q.kewajiban_kirim_sby(), 70000)

    def test_client_statement_running_balance(self):
        self._pay(40000)
        st = q.client_statement(self.client_obj.id)
        self.assertEqual(st["closing_balance"], 60000)  # 100k charge - 40k paid
        self.assertEqual(st["rows"][0]["balance"], 100000)

    def test_client_statement_carries_invoice_number(self):
        st = q.client_statement(self.client_obj.id)
        charge_row = st["rows"][0]
        self.assertEqual(charge_row["invoice_number"], "INV-Q1")
        self.assertEqual(charge_row["debit"], 100000)
        self.assertEqual(charge_row["credit"], 0)

    def test_client_statement_with_opening(self):
        self._pay(20000)
        st = q.client_statement_with_opening(
            self.client_obj.id, date_from=date(2046, 1, 6),
        )
        # Charge 01/05 falls before date_from → opening. Payment 02/01 after.
        self.assertEqual(st["opening_balance"], 100000)
        self.assertEqual(st["closing_balance"], 80000)
        self.assertEqual(st["rows"][0]["balance"], 80000)

    def test_client_aging_buckets(self):
        from datetime import datetime
        from django.utils import timezone as dj_tz
        as_of = dj_tz.make_aware(datetime(2046, 6, 1))
        st = q.client_aging(self.client_obj.id, as_of=as_of)
        # Charge 100k on 01/05, due-date fallback issued (01/05) → ~150 days old
        self.assertEqual(st["total"], 100000)
        self.assertEqual(st["buckets"]["90_plus"], 100000)
        self.assertEqual(len(st["invoices"]), 1)
        self.assertEqual(st["invoices"][0]["invoice_number"], "INV-Q1")

    def test_client_aging_after_full_payment(self):
        self._pay(100000)
        st = q.client_aging(self.client_obj.id)
        self.assertEqual(st["total"], 0)
        self.assertEqual(st["invoices"], [])

    def test_open_items_partial(self):
        self._pay(40000)
        oi = q.open_items(self.client_obj.id)
        self.assertEqual(oi["total_remaining"], 60000)
        self.assertEqual(len(oi["rows"]), 1)
        row = oi["rows"][0]
        self.assertEqual(row["invoice_number"], "INV-Q1")
        self.assertEqual(row["billed"], 100000)
        self.assertEqual(row["paid"], 40000)
        self.assertEqual(row["remaining"], 60000)

    def test_open_items_full_payment_omitted(self):
        self._pay(100000)
        oi = q.open_items(self.client_obj.id)
        self.assertEqual(oi["total_remaining"], 0)
        self.assertEqual(oi["rows"], [])

    def test_open_items_overdue_flag(self):
        # due_date in the (real) past → flag overdue.
        self.invoice.due_date = date(2020, 2, 1)
        self.invoice.save()
        oi = q.open_items(self.client_obj.id)
        self.assertEqual(len(oi["rows"]), 1)
        self.assertTrue(oi["rows"][0]["overdue"])

    def test_open_items_reconciles_with_statement(self):
        self._pay(75000)
        oi = q.open_items(self.client_obj.id)
        st = q.client_statement(self.client_obj.id)
        self.assertEqual(oi["total_remaining"], 25000)
        self.assertEqual(st["closing_balance"], 25000)

    def test_statement_by_reservation_groups_and_reconciles(self):
        self._pay(40000)
        st = q.client_statement_by_reservation(self.client_obj.id)
        self.assertEqual(len(st["reservations"]), 1)
        g = st["reservations"][0]
        self.assertEqual(g["reservation_number"], "R-Q1")
        self.assertEqual(g["billed"], 100000)
        self.assertEqual(g["paid"], 40000)
        self.assertEqual(g["balance"], 60000)
        self.assertFalse(g["settled"])
        self.assertEqual(st["unallocated"], 0)
        self.assertEqual(st["closing_balance"], 60000)

    def test_statement_by_reservation_settled_flag(self):
        self._pay(100000)
        st = q.client_statement_by_reservation(self.client_obj.id)
        g = st["reservations"][0]
        self.assertEqual(g["balance"], 0)
        self.assertTrue(g["settled"])

    def test_statement_by_reservation_multi(self):
        inv2 = Invoice.objects.create(
 invoice_type="hotel", invoice_number="INV-Q2",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 8),
        )
        Reservation.objects.create(
            invoice=inv2, reservation_number="R-Q2", total_sar=30000,
        )
        posting.post_invoice_charge(inv2, created_by=self.user)
        self._pay(100000)  # fully settles R-Q1

        st = q.client_statement_by_reservation(self.client_obj.id)
        self.assertEqual(len(st["reservations"]), 2)
        # Outstanding (R-Q2) sorts before settled (R-Q1).
        self.assertEqual(st["reservations"][0]["reservation_number"], "R-Q2")
        self.assertEqual(st["reservations"][0]["balance"], 30000)
        self.assertTrue(st["reservations"][1]["settled"])
        self.assertEqual(
            st["opening_balance"]
            + sum(g["balance"] for g in st["reservations"])
            + st["unallocated"],
            st["closing_balance"],
        )

    def test_statement_by_reservation_with_opening(self):
        self._pay(20000)
        st = q.client_statement_by_reservation(
            self.client_obj.id, date_from=date(2046, 1, 6),
        )
        # Charge 01/05 → opening; payment 02/01 → in-period.
        self.assertEqual(st["opening_balance"], 100000)
        self.assertEqual(st["closing_balance"], 80000)

    def test_byres_summary_figures_walk_down_to_closing_balance(self):
        """Angka-angka yang dicetak PDF (baris tabel + Account Summary) harus
        bisa dijumlah ulang persis ke `closing_balance` versi balance-forward."""
        svc = Invoice.objects.create(
            invoice_type="service", invoice_number="INV-Q-SVC2",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 6),
        )
        ServiceItem.objects.create(invoice=svc, name="Visa", qty=1, price=16250)
        posting.post_invoice_charge(svc, created_by=self.user)
        self._pay(40000)
        dep = create_payment_record(
            None, self.client_obj, date(2046, 2, 1), 100000,
            method="transfer", created_by=self.user, received_in="sby",
        )
        posting.post_payment(dep, created_by=self.user)

        st = q.client_statement_by_reservation(self.client_obj.id)
        sub_debit = sum(g["billed"] for g in st["reservations"])
        sub_credit = sum(g["paid"] for g in st["reservations"])
        self.assertEqual(
            st["opening_balance"] + sub_debit - sub_credit
            + st["unallocated_debits"] - st["unallocated_credits"],
            st["closing_balance"],
        )
        # Total baris tabel = kolom summary, bukan total_debit mentah yang
        # ikut menyapu baris unallocated.
        self.assertNotEqual(sub_debit, st["total_debit"])

    def test_unallocated_splits_credits_from_debits(self):
        """Deposit 100rb tak teralokasi harus TIDAK dijumlah diam-diam dengan
        charge service-item 16.250 yang juga tanpa reservasi (regresi: bucket
        `unallocated` dulu melaporkan -83.750, bukan -100.000)."""
        # Charge tanpa dimensi reservasi: service item di invoice servis.
        svc = Invoice.objects.create(
            invoice_type="service", invoice_number="INV-Q-SVC",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 6),
        )
        ServiceItem.objects.create(
            invoice=svc, name="Visa", qty=1, price=16250,
        )
        posting.post_invoice_charge(svc, created_by=self.user)
        # Deposit 100rb, tanpa invoice/reservasi.
        dep = create_payment_record(
            None, self.client_obj, date(2046, 2, 1), 100000,
            method="transfer", created_by=self.user, received_in="sby",
        )
        posting.post_payment(dep, created_by=self.user)

        st = q.client_statement_by_reservation(self.client_obj.id)
        self.assertEqual(st["unallocated_credits"], 100000)
        self.assertEqual(st["unallocated_debits"], 16250)
        self.assertEqual(st["unallocated"], 16250 - 100000)
        # Rekonsiliasi tetap utuh dan reservasi tidak tersentuh.
        self.assertEqual(
            st["opening_balance"]
            + sum(g["balance"] for g in st["reservations"])
            + st["unallocated"],
            st["closing_balance"],
        )

    def test_unallocated_ignores_reversed_payment_pairs(self):
        """Payment yang dibatalkan (entry + reversal-nya) tidak boleh menambah
        deposit yg fiktif; pair-nya net nol dan harus hilang dari kedua sisi."""
        def deposit(amount):
            p = create_payment_record(
                None, self.client_obj, date(2046, 2, 1), amount,
                method="transfer", created_by=self.user, received_in="sby",
            )
            return posting.post_payment(p, created_by=self.user)

        voided = deposit(50000)
        live = deposit(100000)
        posting.reverse_entry(voided, reversal_date=date(2046, 2, 2), created_by=self.user)

        st = q.client_statement_by_reservation(self.client_obj.id)
        self.assertEqual(st["unallocated_credits"], 100000)
        self.assertEqual(st["unallocated_debits"], 0)
        self.assertEqual(st["unallocated"], -100000)
        self.assertEqual(
            st["opening_balance"]
            + sum(g["balance"] for g in st["reservations"])
            + st["unallocated"],
            st["closing_balance"],
        )

    def test_trial_balance_zero(self):
        self._pay(55000)
        tb = q.trial_balance()
        self.assertTrue(tb["balanced"])
        self.assertEqual(tb["total_debit"], tb["total_credit"])

    def test_client_billed_and_paid_reflects_journal(self):
        self.assertEqual(q.client_billed_sar(self.client_obj.id), 100000)
        self.assertEqual(q.client_paid_sar(self.client_obj.id), 0)
        self._pay(60000)
        self.assertEqual(q.client_paid_sar(self.client_obj.id), 60000)
        # properti model ter-flip ikut queries
        self.assertEqual(self.client_obj.total_billed, 100000)
        self.assertEqual(self.client_obj.total_paid, 60000)
        self.assertEqual(self.client_obj.outstanding, 40000)

    def test_remittance_sent_sar(self):
        from hw.models import Remittance
        rmt = Remittance.objects.create(
 date=date(2046, 3, 1), remittance_number="RMT-Q1",
            received_amount_sar=50000,
        )
        self.assertEqual(q.remittance_sent_sar(rmt.id), 0)
        posting.post_remittance_send(
            rmt, from_location="sby", amount_sar=50000, created_by=self.user,
        )
        self.assertEqual(q.remittance_sent_sar(rmt.id), 50000)
        self.assertEqual(rmt.total_sar, 50000)
