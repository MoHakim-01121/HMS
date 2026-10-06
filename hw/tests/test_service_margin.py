"""Schema v2 F10 — laporan margin Services dan utang per vendor."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import expense_service, posting
from hw.finance import queries as fq
from hw.models import Branch, CashAccount, ExpenseCategory, InvoiceLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_cash, make_invoice, make_service_line


class ServiceMarginTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sm', password='pw12345', is_superuser=True)
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.sby = Branch.objects.get(code='sby')
        self.cat = ExpenseCategory.objects.get(code='SVC-VENDOR')
        self.invoice = make_invoice(branch=self.sby, invoice_type='visa', currency='SAR', issued_date=date(2026, 3, 1))
        self.visa = InvoiceLine.objects.get(pk=make_service_line(self.invoice, 'Visa', qty=10, price=500).pk)
        self.bus = InvoiceLine.objects.get(pk=make_service_line(self.invoice, 'Bus', qty=1, price=800).pk)
        posting.post_invoice_charge(self.invoice, created_by=self.user, entry_date=date(2026, 3, 1))
        fund_cash(CashAccount.objects.get(branch_id='sby'), 1_000_000)

    def _cost(self, line, amount, vendor='Muassasah', pay=False):
        return expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 2), created_by=self.user, vendor=vendor,
            lines=[{'category': self.cat, 'amount': amount, 'service_line': line}],
            pay_now={'account': CashAccount.objects.get(branch_id='sby')} if pay else None,
        )

    def test_margin_per_line_from_billed_sar_and_vendor_cost(self):
        self._cost(self.visa, 3000)
        m = fq.service_margins()
        visa = next(r for r in m['rows'] if r['line_id'] == self.visa.pk)
        self.assertEqual((visa['revenue_sar'], visa['cost_sar'], visa['margin_sar'], visa['margin_pct']),
                         (5000, 3000, 2000, 40.0))
        self.assertEqual((m['revenue_sar'], m['cost_sar'], m['without_cost']), (5800, 3000, 1))

    def test_voided_expense_is_not_a_cost(self):
        exp = self._cost(self.visa, 3000)
        expense_service.void_expense(exp, created_by=self.user)
        self.assertEqual(fq.service_margins()['cost_sar'], 0)

    def test_filters_by_selling_branch(self):
        self.assertEqual(fq.service_margins(branch='jkt')['rows'], [])
        self.assertEqual(len(fq.service_margins(branch='sby')['rows']), 2)

    def test_vendor_payables(self):
        self._cost(self.visa, 3000, vendor='Muassasah')
        self._cost(self.bus, 600, vendor='Bus Co', pay=True)
        rows = {r['vendor']: r for r in fq.vendor_payables()}
        self.assertEqual(rows['Muassasah']['outstanding_sar'], 3000)
        self.assertEqual((rows['Bus Co']['paid_sar'], rows['Bus Co']['outstanding_sar']), (600, 0))

    def test_page_renders(self):
        self._cost(self.visa, 3000)
        self.client.force_login(self.user)
        props = self.client.get('/finance/service-margin/?branch=sby', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['margins']['margin_sar'], 5800 - 3000)
        self.assertEqual(props['payables'][0]['vendor'], 'Muassasah')
