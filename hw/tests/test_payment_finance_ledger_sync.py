"""Finance-page payment → general ledger. Payment lewat create_payment_record
+ confirm_payment + allocate_payment harus terlihat di Invoice.total_paid_sar,
breakdown per-reservasi, dan bisa di-reverse."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, ServiceItem
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance_helpers import create_payment_record, confirm_payment, allocate_payment
from hw.views.context import _build_reservation_context


class FinancePagePaymentTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ledger_sync', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(company='konoz', name='PT Ledger Sync')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-LS-001',
            customer_name='PT Ledger Sync', client=self.client_obj, issued_date=date(2026, 1, 1),
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R1', total_sar=1000,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _pay(self, amount=400, method='transfer', reservation=None):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=amount, method=method, created_by=self.user, reservation=reservation,
            received_in='pusat' if method == 'direct' else 'sby',
        )
        confirm_payment(p, confirmed_by=self.user)
        allocate_payment(p, allocation_date=p.payment_date, created_by=self.user)
        return p

    def test_payment_updates_invoice_totals_and_status(self):
        self._pay(400)
        self.assertEqual(self.invoice.total_paid_sar, 400)
        self.assertEqual(self.invoice.remaining_sar, 600)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_PARTIAL)

    def test_two_payments_accumulate_to_paid(self):
        self._pay(400)
        self._pay(600)
        self.assertEqual(self.invoice.total_paid_sar, 1000)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_PAID)

    def test_direct_method_hits_kas_pusat(self):
        from hw.finance import queries as fq
        self._pay(1000, method='direct')
        self.assertEqual(fq.kas_pusat('konoz'), 1000)
        self.assertEqual(fq.kas_surabaya('konoz'), 0)

    def test_payment_tied_to_reservation_shows_in_breakdown(self):
        self._pay(400, reservation=self.res)
        row = next(r for r in _build_reservation_context(self.invoice) if r['id'] == self.res.id)
        self.assertEqual(row['paid_int'], 400)
        self.assertEqual(row['remaining_int'], 600)


class PaymentReverseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ledger_reverse', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        self.client_obj = Client.objects.create(company='konoz', name='PT Reverse')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-REV-001',
            customer_name='PT Reverse', client=self.client_obj, issued_date=date(2026, 1, 1),
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=400, method='transfer', created_by=self.user,
        )
        confirm_payment(self.payment, confirmed_by=self.user)
        allocate_payment(self.payment, allocation_date=self.payment.payment_date, created_by=self.user)

    def test_reverse_undoes_payment_and_sets_status(self):
        self.assertEqual(self.invoice.total_paid_sar, 400)
        resp = self.client.post(f'/finance/payments/{self.payment.pk}/reverse/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.invoice.total_paid_sar, 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_DRAFT)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentRecord.STATUS_REVERSED)

    def test_reverse_leaves_other_payment_intact(self):
        other = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 2),
            amount=300, method='transfer', created_by=self.user,
        )
        confirm_payment(other, confirmed_by=self.user)
        allocate_payment(other, allocation_date=other.payment_date, created_by=self.user)
        self.assertEqual(self.invoice.total_paid_sar, 700)

        self.client.post(f'/finance/payments/{self.payment.pk}/reverse/')

        self.assertEqual(self.invoice.total_paid_sar, 300)
