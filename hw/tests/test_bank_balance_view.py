"""§78 UI — bank/cash balance overview page."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models.period import FinancialPeriod


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


class BankAccountListViewTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.manager = make_user('bank_mgr', 'manager')

    def test_manager_can_view(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/finance/bank-accounts/')
        self.assertEqual(resp.status_code, 200)

    def test_branch_filter_scopes_accounts(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/finance/bank-accounts/?branch=sby', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        accounts = resp.json()['props']['accounts']
        self.assertTrue(all(a['branch'] == 'sby' for a in accounts))
        self.assertTrue(len(accounts) >= 1)

    def test_anonymous_redirected(self):
        resp = self.client.get('/finance/bank-accounts/')
        self.assertEqual(resp.status_code, 302)
