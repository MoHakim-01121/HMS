"""FASE E UI — settlement_views wiring (list/obligation/settlement/allocate + RBAC)."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch, HQObligation, Remittance
from hw.models.period import FinancialPeriod


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


class SettlementViewsBase(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.manager = make_user('stl_mgr', 'manager')
        self.staff = make_user('stl_staff', 'staff')
        self.sby = Branch.objects.get(code='sby')
        self.rmt = Remittance.objects.create(
            company='konoz', date=date(2026, 6, 1), remittance_number='RMT-UI-1',
        )


class SettlementListViewTest(SettlementViewsBase):
    def test_manager_can_view_list(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/remittance/settlement/')
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_redirected(self):
        resp = self.client.get('/remittance/settlement/')
        self.assertEqual(resp.status_code, 302)


class ObligationNewViewTest(SettlementViewsBase):
    def test_manager_can_create_obligation(self):
        self.client.force_login(self.manager)
        resp = self.client.post('/remittance/settlement/obligations/new/', {
            'branch': 'sby', 'amount_sar': '15000',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(HQObligation.objects.filter(branch_id='sby', amount_sar=15000).exists())

    def test_staff_cannot_create_obligation_remittance_readonly(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/remittance/settlement/obligations/new/', {
            'branch': 'sby', 'amount_sar': '5000',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(HQObligation.objects.filter(amount_sar=5000).exists())


class SettlementNewAndAllocateViewTest(SettlementViewsBase):
    def setUp(self):
        super().setUp()
        self.ob = HQObligation.objects.create(branch=self.sby, amount_sar=10000)

    def test_manager_can_add_settlement_and_allocate(self):
        self.client.force_login(self.manager)
        resp = self.client.post('/remittance/settlement/new/', {
            'remittance': str(self.rmt.pk), 'received_amount_sar': '10000',
            'received_date': '2026-06-05',
        })
        self.assertEqual(resp.status_code, 302)
        settlement = self.rmt.settlements.get()
        self.assertEqual(settlement.received_amount_sar, 10000)

        resp = self.client.post(f'/remittance/settlement/{settlement.pk}/allocate/', {
            'allocations': json.dumps([{'obligation_id': self.ob.pk, 'amount_sar': 10000}]),
        })
        self.assertEqual(resp.status_code, 302)
        self.ob.refresh_from_db()
        self.assertEqual(self.ob.status, HQObligation.STATUS_SETTLED)
