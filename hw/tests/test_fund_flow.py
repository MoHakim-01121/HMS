"""Branch fund flow + realized FX profit, on the worked example agreed with
the user: client A pays USD (exchanged to IDR), client B pays IDR, both
bookings (20,000 SAR) sent to HQ in one IDR transfer at 4,750."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import exchange_service, fund_flow
from hw.finance.accounts import cash_ledger_for
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import BankAccount, BankTransaction, Client, LedgerAccount, Remittance
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_invoice

SEP = dict(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))


class FundFlowScenario(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('ff', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        LedgerAccount.objects.get(code='1000-KAS-SBY')
        self.idr = BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', ledger_account_id=cash_ledger_for('sby', 'IDR'),
                                              bank_name='Mandiri', account_identifier='1', opening_balance=1_000_000,
                                              opening_date=date(2026, 9, 1))
        from hw.finance.bank_ledger import sync_opening_balance
        sync_opening_balance(self.idr)
        self.usd = BankAccount.objects.create(branch_id='sby', name='USD', currency='USD', ledger_account_id=cash_ledger_for('sby', 'USD'),
                                              bank_name='Mandiri', account_identifier='2')
        client = Client.objects.create(name='PT Scenario')
        inv = make_invoice(invoice_number='INV-FF', customer_name='PT Scenario', client=client)
        # A: USD 2,500 × 4 SAR/USD = 10,000 SAR · B: IDR 49,000,000 ÷ 4,900 = 10,000 SAR
        for day, amount, currency, rate, acc in (
            (5, 2_500, 'USD', 4, self.usd),
            (6, 49_000_000, 'IDR', 4900, self.idr),
        ):
            p = create_payment_record(inv, client, date(2026, 9, day), amount, currency=currency, exchange_rate=rate,
                                      method='Transfer', receiving_account=acc, created_by=self.user)
            confirm_payment(p, self.user)
        exchange_service.record_exchange(from_account=self.usd, amount_out=2_500, to_account=self.idr,
                                         amount_in=48_125_000, exchange_date=date(2026, 9, 8), created_by=self.user)
        self.client.force_login(self.user)

    def _send(self, idr, sar_rate='4750', day='2026-09-10'):
        resp = self.client.post('/remittance/new/', {'from_bank_account': str(self.idr.pk), 'date': day,
                                                     'amount_idr': str(idr), 'exchange_rate': sar_rate})
        self.assertEqual(resp.status_code, 302)

    def _spend(self, idr):
        from hw.tests.factories import paid_expense
        return paid_expense(self.idr.branch, self.idr, idr, date(2026, 9, 12), self.user)

    def _line(self, flow, key, cur):
        return next(l for l in flow['lines'] if l['key'] == key)['values'].get(cur, 0)

    def test_fund_flow_per_currency(self):
        self._send(95_000_000)
        self._spend(500_000)
        flow = fund_flow.fund_flow(branch='sby', **SEP)
        idr = {k: self._line(flow, k, 'IDR') for k in ('opening', 'client_in', 'exchange_in', 'sent_hq', 'operational', 'closing')}
        self.assertEqual(idr, {'opening': 1_000_000, 'client_in': 49_000_000, 'exchange_in': 48_125_000,
                               'sent_hq': -95_000_000, 'operational': -500_000, 'closing': 2_625_000})
        usd = {k: self._line(flow, k, 'USD') for k in ('client_in', 'exchange_out', 'closing')}
        self.assertEqual(usd, {'client_in': 2_500, 'exchange_out': -2_500, 'closing': 0})
        self.assertEqual(flow['currencies'][:2], ['IDR', 'USD'])

    def test_full_transfer_profit_matches_worked_example(self):
        self._send(95_000_000)
        fx = fund_flow.fx_profit(branch='sby', **SEP)
        (t,) = fx['transfers']
        self.assertEqual((t['sar'], t['idr_sent'], t['avg_rate'], t['profit_idr'], t['fully_covered']),
                         (20_000, 95_000_000, 4856.25, 2_125_000, True))
        self.assertEqual(fx['total_profit_idr'], 2_125_000)
        self.assertEqual(fx['client_money_held'].get('IDR', {'amount': 0, 'sar': 0}), {'amount': 0, 'sar': 0})

    def test_partial_transfer_keeps_the_rest_at_average_cost(self):
        self._send(47_500_000)                      # 10,000 SAR @4,750
        fx = fund_flow.fx_profit(branch='sby', **SEP)
        self.assertEqual(fx['total_profit_idr'], 1_062_500)
        self.assertEqual(fx['client_money_held']['IDR'], {'amount': 48_562_500, 'sar': 10_000})

    def test_report_page_and_csv(self):
        self._send(95_000_000)
        props = self.client.get('/finance/fund-flow/?branch=sby&from=2026-09-01&to=2026-09-30',
                                HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['fx']['total_profit_idr'], 2_125_000)
        closing = next(l for l in props['flow']['lines'] if l['key'] == 'closing')
        self.assertEqual(closing['values']['IDR'], 3_125_000)
        resp = self.client.get('/finance/fund-flow/export/csv/?branch=sby&from=2026-09-01&to=2026-09-30')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('2125000', resp.content.decode('utf-8-sig'))

    def test_remittance_kpis_show_realized_profit(self):
        self._send(95_000_000)
        props = self.client.get('/remittance/?month=2026-09', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['kpis']['fx_gain'], 2_125_000)
        self.assertEqual(props['remittances'][0]['fx_gain_idr'], 2_125_000)


class RemittanceFormFxTest(FundFlowScenario):
    """Laba kurs di form setoran: posisi uang client + setoran lama yang diisi user."""

    def test_new_form_shows_client_money_and_original_rate(self):
        props = self.client.get('/remittance/new/', HTTP_X_INERTIA='true').json()['props']
        # 49,000,000 IDR + USD exchanged to 48,125,000 IDR, owing 20,000 SAR.
        self.assertEqual(props['fx_pool'], {'amount': 97_125_000, 'sar': 20_000, 'rate': 4856.25})

    def test_edit_form_uses_position_before_the_transfer(self):
        self._send(95_000_000)
        rem = Remittance.objects.get()
        props = self.client.get(f'/remittance/{rem.pk}/edit/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['fx_pool']['sar'], 20_000)
        self.assertEqual(props['rem']['amount_idr'], 95_000_000)

    def test_legacy_transfer_profit_comes_from_the_original_amount(self):
        self._send(95_000_000)
        rem = Remittance.objects.get()
        Remittance.objects.filter(pk=rem.pk).update(is_legacy=True)
        self.assertIsNone(fund_flow.fx_profit(branch='sby')['transfers'][0]['profit_idr'])
        self.assertEqual(fund_flow.fx_profit(branch='sby')['unpriced'], 1)
        self.client.post(f'/remittance/{rem.pk}/edit/', {
            'date': '2026-09-10', 'amount_idr': '94000000', 'original_amount': '97000000',
        })
        rem.refresh_from_db()
        self.assertEqual((rem.amount_sent, rem.original_amount, rem.expected_sar), (94_000_000, 97_000_000, 20_000))
        row = fund_flow.fx_profit(branch='sby')['transfers'][0]
        self.assertEqual((row['profit_idr'], row['avg_rate']), (3_000_000, 4850.0))
        # The cash book follows the corrected rupiah.
        tx = BankTransaction.objects.get(source_type='Remittance', source_id=rem.pk)
        self.assertEqual(tx.amount, 94_000_000)
