"""FASE E UI — settlement_views wiring (list/settlement + RBAC)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_ledger_for, make_remittance


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


class SettlementViewsBase(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        # Recording what head office received is Finance's (2026-10-09).
        self.finance = make_user('stl_fin', 'finance')
        self.manager = make_user('stl_mgr', 'manager')
        self.staff = make_user('stl_staff', 'staff')
        self.sby = Branch.objects.get(code='sby')
        self.rmt = make_remittance(
 date=date(2026, 6, 1), remittance_number='RMT-UI-1',
        )


class RecordReceiptViewTest(SettlementViewsBase):
    def _url(self):
        return f'/remittance/{self.rmt.pk}/receipt/'

    def test_settlement_list_page_is_gone(self):
        self.client.force_login(self.finance)
        resp = self.client.get('/remittance/settlement/')
        self.assertEqual(resp.status_code, 404)

    def test_finance_can_record_receipt(self):
        self.client.force_login(self.finance)
        resp = self.client.post(self._url(), {
            'received_amount_sar': '10000', 'received_date': '2026-06-05',
        })
        self.assertRedirects(resp, f'/remittance/{self.rmt.pk}/', fetch_redirect_response=False)
        settlement = self.rmt.settlements.get()
        self.assertEqual(settlement.received_amount_sar, 10000)

    def test_json_next_is_honoured(self):
        # Inertia router.post mengirim JSON -- `next` harus dibaca dari body,
        # bukan request.POST (yang kosong untuk JSON).
        self.client.force_login(self.finance)
        resp = self.client.post(
            self._url(),
            data='{"received_amount_sar": "10000", "received_date": "2026-06-05", "next": "/remittance/"}',
            content_type='application/json',
        )
        self.assertRedirects(resp, '/remittance/', fetch_redirect_response=False)

    def test_staff_and_manager_cannot_record_receipt(self):
        for user in (self.staff, self.manager):
            self.client.force_login(user)
            resp = self.client.post(self._url(), {
                'received_amount_sar': '10000', 'received_date': '2026-06-05',
            })
            self.assertEqual(resp.status_code, 302)
        self.assertFalse(self.rmt.settlements.exists())

class RemittanceDetailSettlementPropsTest(SettlementViewsBase):
    """remittance_detail harus mengekspos status settlement bertahap --
    lihat frontend/pages/Remittance/Detail.jsx (kartu 'Received at HQ' salah
    kalau hanya baca received_amount_sar legacy untuk remittance yang
    memakai jalur RemittanceSettlement)."""

    def setUp(self):
        super().setUp()
        self.rmt.amount_idr = 240_000_000
        self.rmt.exchange_rate = 4800  # expected_sar = 50000
        self.rmt.save(update_fields=['amount_sent', 'exchange_rate'])

    def test_props_reflect_partial_settlement(self):
        from hw.finance import settlement_service as svc
        svc.add_settlement(self.rmt, received_amount_sar=40000, received_date=date(2026, 6, 5),
                            created_by=self.manager)

        self.client.force_login(self.finance)
        resp = self.client.get(f'/remittance/{self.rmt.pk}/', HTTP_X_INERTIA='true')
        rem_props = resp.json()['props']['rem']
        self.assertEqual(rem_props['settlement_status'], 'partially_settled')
        self.assertEqual(rem_props['settled_total_sar'], 40000)
        self.assertEqual(len(rem_props['settlements']), 1)
        self.assertIsNone(rem_props['received_amount_sar'])

class RemittanceCloseDiffViewTest(SettlementViewsBase):
    def setUp(self):
        super().setUp()
        from hw.finance import posting
        fund_ledger_for(self.rmt, 10000)
        posting.post_remittance_send(self.rmt, amount_sar=10000, created_by=self.manager)
        self.client.force_login(self.finance)
        self.client.post(f'/remittance/{self.rmt.pk}/receipt/', {
            'received_amount_sar': '9500', 'received_date': '2026-06-10',
        })

    def _props(self):
        self.client.force_login(self.finance)
        resp = self.client.get(f'/remittance/{self.rmt.pk}/', HTTP_X_INERTIA='true')
        return resp.json()['props']['rem']

    def test_detail_props_expose_open_diff(self):
        rem = self._props()
        self.assertEqual(rem['diff_sar'], 500)
        self.assertTrue(rem['can_close_diff'])
        self.assertTrue(rem['can_record_receipt'])
        self.assertEqual(rem['status'], 'pending')

    def test_finance_can_close_diff(self):
        resp = self.client.post(f'/remittance/{self.rmt.pk}/close-diff/')
        self.assertRedirects(resp, f'/remittance/{self.rmt.pk}/', fetch_redirect_response=False)
        rem = self._props()
        self.assertTrue(rem['diff_closed'])
        self.assertFalse(rem['can_close_diff'])
        self.assertFalse(rem['can_record_receipt'])
        self.assertEqual(rem['status'], 'received')

    def test_staff_cannot_close_diff(self):
        self.client.force_login(self.staff)
        resp = self.client.post(f'/remittance/{self.rmt.pk}/close-diff/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self._props()['can_close_diff'])

    def test_list_props_expose_partial_receipt(self):
        resp = self.client.get('/remittance/?month=2026-06', HTTP_X_INERTIA='true')
        row = next(r for r in resp.json()['props']['remittances'] if r['id'] == self.rmt.pk)
        self.assertEqual(row['received_sar'], 9500)
        self.assertEqual(row['state'], 'partial')
        self.assertTrue(row['can_record_receipt'])
