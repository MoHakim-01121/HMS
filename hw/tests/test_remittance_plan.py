"""Rencana saat kirim (RemittancePlanLine): reservasi yang dipilih di tab
Tracking ikut transfer sebagai rencana, tampil sebagai uang di jalan per
reservasi, dan menjadi isian awal form penerimaan.

Skenario memakai AllocationBase: A 32.000, B 9.000, C 9.000 SAR menunggu,
RMT-ALC-1 50.000 SAR di jalan.
"""
import json
from datetime import date

from hw.finance import remittance_allocation as ra
from hw.finance.bank_ledger import record_bank_transaction
from hw.finance.errors import FinanceError
from hw.models import Remittance, RemittancePlanLine
from hw.tests.factories import fund_ledger
from hw.tests.test_remittance_allocation import AllocationBase
from hw.views.remittance_views import _compute_tracking_data


class PlanBase(AllocationBase):
    def _plan(self, rem, **amounts):
        res = {'A': self.a, 'B': self.b, 'C': self.c}
        for number, amount in amounts.items():
            RemittancePlanLine.objects.create(remittance=rem, invoice_line=res[number], amount_sar=amount)

    def _tracking(self):
        return {r['linked_number']: r for r in _compute_tracking_data()['reservations']}


class TrackingPlanTest(PlanBase):
    def test_planned_money_is_not_still_to_send(self):
        self._plan(self.rem, A=32000, C=5000)
        rows = self._tracking()
        self.assertEqual({k: r['to_send'] for k, r in rows.items()}, {'A': 0, 'B': 9000, 'C': 4000})
        self.assertEqual(rows['A']['planned'], [{'rmt_id': self.rem.pk, 'rmt_number': 'RMT-ALC-1', 'amount_sar': 32000}])
        self.assertEqual(rows['B']['invoice_line_id'], self.b.pk)

    def test_allocation_uses_up_the_plan(self):
        self._plan(self.rem, A=32000, C=9000)
        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self.assertEqual(ra.open_plans(), {self.c.pk: [{
            'remittance_id': self.rem.pk, 'remittance_number': 'RMT-ALC-1', 'amount_sar': 1000,
        }]})
        self.assertEqual(self._tracking()['C']['to_send'], 0)

    def test_plan_ends_with_its_transfer(self):
        self._plan(self.rem, B=9000)
        self._receive(50000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 9000},
            {'linked_number': 'B', 'amount_sar': 9000},
        ])
        self.assertEqual(ra.open_plans(), {})


class ValidatePlanTest(PlanBase):
    def test_rejects_more_than_waiting(self):
        with self.assertRaisesMessage(FinanceError, 'melebihi'):
            ra.validate_plan([{'invoice_line_id': self.b.pk, 'amount_sar': 9001}])

    def test_rejects_money_already_planned(self):
        self._plan(self.rem, A=32000)
        with self.assertRaisesMessage(FinanceError, 'sudah tidak menunggu'):
            ra.validate_plan([{'invoice_line_id': self.a.pk, 'amount_sar': 1}])

    def test_merges_and_skips_zero(self):
        rows = ra.validate_plan([
            {'invoice_line_id': self.b.pk, 'amount_sar': 4000},
            {'invoice_line_id': self.b.pk, 'amount_sar': 5000},
            {'invoice_line_id': self.c.pk, 'amount_sar': 0},
        ])
        self.assertEqual([(r['reservation_id'], amount) for r, amount in rows], [(self.b.pk, 9000)])


class PlanFillTest(PlanBase):
    def test_receipt_starts_from_the_plan_up_to_the_amount(self):
        self._plan(self.rem, C=9000, A=32000)
        fill = ra.plan_fill(self.rem, ra.candidates(self.rem), 40000)
        self.assertEqual([(f['linked_number'], f['amount_sar']) for f in fill], [('C', 9000), ('A', 31000)])

    def test_no_plan_means_auto_fill(self):
        self.assertIsNone(ra.plan_fill(self.rem, ra.candidates(self.rem), 40000))


class PlanViewTest(PlanBase):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        self.account = self.rem.from_account

    def _fund(self):
        # Buku kas (cek saldo form) dan buku besar, senilai 9.000 SAR pada kurs kirim.
        record_bank_transaction(
            account=self.account, direction='in', amount_sar=9000, currency='IDR', amount=43_200_000,
            source_type='Test', source_id=1, transaction_date=date(2026, 9, 11),
        )
        fund_ledger(self.account, 43_200_000, 9000, date(2026, 9, 11))

    def _page(self, url):
        return self.client.get(url, HTTP_X_INERTIA='true').json()['props']

    def test_form_reads_the_plan_from_tracking_and_trims_it(self):
        props = self._page(f'/remittance/new/?plan={self.b.pk}:9500,{self.c.pk}:2000,999999:5')
        self.assertEqual([(p['linked_number'], p['amount_sar']) for p in props['plan']], [('B', 9000), ('C', 2000)])

    def test_save_stores_the_plan_with_the_transfer(self):
        self._fund()
        resp = self.client.post('/remittance/new/', {
            'date': '2026-09-12', 'amount_idr': '43200000', 'exchange_rate': '4800',
            'from_bank_account': str(self.account.pk),
            'plan': json.dumps([{'invoice_line_id': self.b.pk, 'amount_sar': 9000}]),
        })
        rem = Remittance.objects.exclude(pk=self.rem.pk).get()
        self.assertRedirects(resp, f'/remittance/{rem.pk}/', fetch_redirect_response=False)
        self.assertEqual(list(rem.plan_lines.values_list('invoice_line_id', 'amount_sar')), [(self.b.pk, 9000)])

    def test_bad_plan_saves_nothing_and_keeps_the_rows(self):
        self._fund()
        resp = self.client.post('/remittance/new/', {
            'date': '2026-09-12', 'amount_idr': '43200000', 'exchange_rate': '4800',
            'from_bank_account': str(self.account.pk),
            'plan': json.dumps([{'invoice_line_id': self.b.pk, 'amount_sar': 9500}]),
        }, HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertIn('melebihi', props['error'])
        self.assertEqual([(p['linked_number'], p['amount_sar']) for p in props['plan']], [('B', 9500)])
        self.assertEqual(Remittance.objects.count(), 1)

    def test_draft_pdf_lists_the_chosen_money_and_saves_nothing(self):
        resp = self.client.get(f'/remittance/draft/pdf/?plan={self.b.pk}:9500,{self.c.pk}:2000,999999:5')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertEqual(sorted((p['linked_number'], p['amount_sar']) for p in resp.context['lines']), [('B', 9000), ('C', 2000)])
        self.assertEqual(resp.context['total_sar'], 11000)
        self.assertEqual(Remittance.objects.count(), 1)
        self.assertFalse(RemittancePlanLine.objects.exists())

    def test_receipt_form_starts_from_the_plan(self):
        self._plan(self.rem, B=9000)
        form = self._page(f'/remittance/{self.rem.pk}/receipt/')['form']
        self.assertEqual(form['allocations'], [{'linked_number': 'B', 'invoice_id': self.invoice.pk, 'amount_sar': 9000}])
