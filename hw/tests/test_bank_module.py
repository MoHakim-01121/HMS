"""The 'bank' module and Staff on money (decided 2026-10-20).

Bank and cash accounts, transfers and exchanges, and reconciliation are their
own module, apart from recording client payments. Staff records client
payments for Admin or Finance to confirm, and sees nothing else of money.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hw.models import UserBranchAccess
from hw.models.role import RoleDefinition, invalidate_matrix_cache
from hw.models.user import Role
from hw.permissions import can


def make_user(username, role, branch=None):
    """`branch` None = every branch, else the one branch code the user covers."""
    user = User.objects.create_user(username, password='pw12345')
    profile = user.profile
    profile.role = role
    profile.all_branches = branch is None
    profile.save()
    if branch:
        UserBranchAccess.objects.create(profile=profile, branch_id=branch)
    return User.objects.get(pk=user.pk)


class SeededBankTest(TestCase):
    def test_staff_records_payments_and_nothing_else_of_money(self):
        staff = make_user('stf', Role.STAFF.value)
        for action in ('view', 'create', 'export'):
            self.assertTrue(can(staff, 'payments', action), action)
        for action in ('edit', 'delete', 'approve'):
            self.assertFalse(can(staff, 'payments', action), action)
        for module in ('bank', 'remittance', 'expenses', 'statements', 'journal', 'periods'):
            self.assertFalse(can(staff, module, 'view'), module)

    def test_every_role_has_on_bank_what_it_had_on_payments(self):
        finance = make_user('fin', Role.FINANCE.value)
        for action in ('view', 'create', 'edit', 'delete', 'export', 'approve'):
            self.assertTrue(can(finance, 'bank', action), action)
        for slug in (Role.MANAGER.value, Role.VIEWER.value):
            user = make_user(slug, slug)
            self.assertTrue(can(user, 'bank', 'view'), slug)
            self.assertTrue(can(user, 'bank', 'export'), slug)
            self.assertFalse(can(user, 'bank', 'create'), slug)


class BankGateTest(TestCase):
    def assertOpens(self, user, url):
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 200, url)

    def assertRefused(self, user, url):
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302, url)
        self.assertEqual(response.url, reverse('home'), url)

    def test_staff_opens_payments_but_not_the_bank_or_other_money(self):
        staff = make_user('stf', Role.STAFF.value)
        self.assertOpens(staff, reverse('payment_list'))
        for name in ('exchange_list', 'exchange_new', 'reconciliation_list', 'bank_account_list',
                     'remittance_list', 'expense_list', 'claim_list'):
            self.assertRefused(staff, reverse(name))

    def test_finance_sets_up_accounts_from_head_office_only(self):
        self.assertOpens(make_user('fin', Role.FINANCE.value), reverse('bank_account_new'))
        branch_finance = make_user('fin-sby', Role.FINANCE.value, branch='sby')
        self.assertRefused(branch_finance, reverse('bank_account_new'))
        # The rest of the bank side stays a branch's to work on.
        self.assertOpens(branch_finance, reverse('exchange_list'))
        self.assertOpens(branch_finance, reverse('reconciliation_list'))

    def test_bank_account_list_says_who_may_set_up(self):
        self.client.force_login(make_user('fin-sby', Role.FINANCE.value, branch='sby'))
        response = self.client.get(reverse('bank_account_list'), HTTP_X_INERTIA='true')
        self.assertIs(response.json()['props']['can_set_up'], False)
        self.client.force_login(make_user('fin', Role.FINANCE.value))
        response = self.client.get(reverse('bank_account_list'), HTTP_X_INERTIA='true')
        self.assertIs(response.json()['props']['can_set_up'], True)

    def test_receipt_pdf_follows_payments_not_invoices(self):
        RoleDefinition.objects.create(slug='cashier', label='Cashier', permissions={'payments': ['export', 'view']})
        RoleDefinition.objects.create(slug='billing', label='Billing', permissions={'invoice': ['export', 'view']})
        invalidate_matrix_cache()
        url = reverse('receipt_pdf', args=[999999])
        # Past the gate a missing receipt is a 404; refused at the gate, home.
        self.client.force_login(make_user('cashier', 'cashier'))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertRefused(make_user('billing', 'billing'), url)
