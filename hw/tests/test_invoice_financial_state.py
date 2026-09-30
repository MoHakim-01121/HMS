"""FASE G — Invoice.financial_state, a derived property additive to `status`."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice
from hw.models.period import FinancialPeriod
from hw.finance_helpers import create_payment_record, confirm_payment
from hw.tests.factories import make_hotel_line, make_invoice


class InvoiceFinancialStateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fs', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT FinState')

    def _invoice(self, **kw):
        inv = make_invoice(invoice_number=f'INV-FS-{Invoice.objects.count()}', customer_name='PT FinState',
                                     client=self.client_obj, **kw)
        make_hotel_line(invoice=inv, reservation_number='R1', total_sar=1000)
        return inv

    def test_unpaid_with_no_due_date(self):
        inv = self._invoice()
        self.assertEqual(inv.financial_state, Invoice.FINANCIAL_STATE_UNPAID)

    def test_overdue_when_past_due_and_unpaid(self):
        inv = self._invoice(due_date=date.today() - timedelta(days=1))
        self.assertEqual(inv.financial_state, Invoice.FINANCIAL_STATE_OVERDUE)

    def test_partial_after_partial_payment(self):
        inv = self._invoice()
        pr = create_payment_record(inv, self.client_obj, date.today(), 400, method='Cash', created_by=self.user)
        confirm_payment(pr, self.user)
        self.assertEqual(inv.financial_state, Invoice.FINANCIAL_STATE_PARTIAL)

    def test_paid_after_full_payment_even_if_past_due(self):
        inv = self._invoice(due_date=date.today() - timedelta(days=1))
        pr = create_payment_record(inv, self.client_obj, date.today(), 1000, method='Cash', created_by=self.user)
        confirm_payment(pr, self.user)
        self.assertEqual(inv.financial_state, Invoice.FINANCIAL_STATE_PAID)

    def test_financial_state_does_not_touch_persisted_status(self):
        inv = self._invoice()
        inv.status = Invoice.STATUS_DRAFT
        inv.save(update_fields=['status'])
        _ = inv.financial_state
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.STATUS_DRAFT)
