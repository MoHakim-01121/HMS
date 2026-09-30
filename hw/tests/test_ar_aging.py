"""AR aging for all clients: buckets by days past the due date, as of a day."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import posting, queries
from hw.models import Client
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_invoice


def _charge(inv, amount, day):
    return posting.post_entry(
        entry_type=JournalEntry.TYPE_CHARGE, description=f'Charge {inv.invoice_number}', entry_date=day,
        source_type='Invoice', source_id=inv.pk, lines=[
            {'account': coa.AR, 'debit': amount, 'client': inv.client_id, 'invoice': inv.pk},
            {'account': coa.INC_HOTEL, 'credit': amount, 'invoice': inv.pk},
        ])


def _pay(inv, amount, day):
    posting.post_entry(
        entry_type=JournalEntry.TYPE_PAYMENT, description='Pay', entry_date=day, lines=[
            {'account': coa.CASH_SBY, 'debit': amount},
            {'account': coa.AR, 'credit': amount, 'client': inv.client_id, 'invoice': inv.pk},
        ])


class ArAgingTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.a = Client.objects.create(name='PT Alpha')
        self.b = Client.objects.create(name='PT Beta')
        # A: one invoice not yet due, one 45 days late (partly paid), one paid off.
        self.a1 = self._inv('INV-A1', self.a, due=date(2026, 9, 10))
        self.a2 = self._inv('INV-A2', self.a, due=date(2026, 7, 27))
        self.a3 = self._inv('INV-A3', self.a, due=date(2026, 6, 1))
        # B: 100 days late.
        self.b1 = self._inv('INV-B1', self.b, due=date(2026, 5, 3))
        _charge(self.a1, 5_000, date(2026, 8, 20))
        _charge(self.a2, 8_000, date(2026, 7, 1))
        _pay(self.a2, 3_000, date(2026, 8, 1))
        _charge(self.a3, 2_000, date(2026, 5, 1))
        _pay(self.a3, 2_000, date(2026, 5, 20))
        _charge(self.b1, 12_000, date(2026, 4, 1))

    def _inv(self, number, client, due):
        return make_invoice(invoice_number=number, customer_name=client.name, client=client, due_date=due)

    def test_buckets_as_of(self):
        aging = queries.ar_aging(as_of=date(2026, 9, 10))
        self.assertEqual(aging['buckets'], {'current': 5_000, '1_30': 0, '31_60': 5_000, '61_90': 0, '90_plus': 12_000})
        self.assertEqual(aging['total'], 22_000)
        self.assertEqual([c['name'] for c in aging['clients']], ['PT Beta', 'PT Alpha'])
        alpha = aging['clients'][1]
        self.assertEqual([i['invoice_number'] for i in alpha['invoices']], ['INV-A2', 'INV-A1'])
        self.assertEqual(alpha['invoices'][0]['days_overdue'], 45)

    def test_as_of_ignores_later_entries(self):
        # Before A1 was charged and before the A2 part-payment.
        aging = queries.ar_aging(as_of=date(2026, 7, 31))
        alpha = next(c for c in aging['clients'] if c['name'] == 'PT Alpha')
        self.assertEqual(alpha['total'], 8_000)
        self.assertEqual(alpha['buckets']['1_30'], 8_000)

    def test_page_and_csv(self):
        user = User.objects.create_superuser('ag', password='pw12345')
        self.client.force_login(user)
        props = self.client.get('/finance/ar-aging/?as_of=2026-09-10', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['aging']['total'], 22_000)
        resp = self.client.get('/finance/ar-aging/export/csv/?as_of=2026-09-10')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8-sig')
        self.assertIn('INV-B1', body)
        self.assertIn('22000', body)
