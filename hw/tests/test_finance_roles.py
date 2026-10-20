"""Phase 3 of the access control audit (decided 2026-10-09).

Only Admin and Finance work on money; Manager reads it; Staff records client
payments only (2026-10-20) and does not see the books. 'approve' is its own action. Every role stays adjustable at /roles/.
Django admin shows money and audit records read-only.
"""
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from hw.models import ActivityLog, BankTransaction, Invoice, UserProfile
from hw.models.role import RoleDefinition
from hw.models.user import Role
from hw.permissions import can
from hw.tests.factories import make_invoice


def make_user(username, role):
    user = User.objects.create_user(username, password='pw12345')
    UserProfile.objects.filter(user=user).update(role=role)
    return User.objects.get(pk=user.pk)


class SeededRolesTest(TestCase):
    def test_finance_works_on_money_and_reads_the_rest(self):
        finance = make_user('fin', Role.FINANCE.value)
        for module in ('payments', 'expenses', 'remittance'):
            for action in ('create', 'edit', 'delete', 'approve'):
                self.assertTrue(can(finance, module, action), (module, action))
        self.assertTrue(can(finance, 'periods', 'edit'))
        self.assertTrue(can(finance, 'invoice', 'view'))
        self.assertFalse(can(finance, 'invoice', 'edit'))
        self.assertTrue(can(finance, 'bank', 'edit'))  # sets up accounts, from head office (2026-10-20)

    def test_manager_reads_money_and_staff_records_payments_only(self):
        manager = make_user('mgr', Role.MANAGER.value)
        staff = make_user('stf', Role.STAFF.value)
        for module in ('payments', 'bank', 'expenses', 'remittance'):
            self.assertTrue(can(manager, module, 'view'), module)
            for action in ('create', 'edit', 'delete'):
                self.assertFalse(can(manager, module, action), module)
        # Staff records client payments for Finance to confirm (2026-10-20).
        self.assertTrue(can(staff, 'payments', 'create'))
        for module in ('bank', 'expenses', 'remittance'):
            self.assertFalse(can(staff, module, 'view'), module)
        # Approving is a manager's for expenses only (decided 2026-10-11); staff approve nothing.
        self.assertTrue(can(manager, 'expenses', 'approve'))
        for module in ('payments', 'remittance'):
            self.assertFalse(can(manager, module, 'approve'), module)
        for module in ('payments', 'expenses', 'remittance'):
            self.assertFalse(can(staff, module, 'approve'), module)
        self.assertTrue(can(manager, 'invoice', 'delete'))
        self.assertTrue(can(manager, 'journal', 'view'))
        for module in ('journal', 'statements', 'periods'):
            self.assertFalse(can(staff, module, 'view'), module)

    def test_django_admin_is_the_administrators(self):
        self.assertFalse(RoleDefinition.objects.get(slug='manager').grants_django_staff)
        self.assertTrue(RoleDefinition.objects.get(slug='admin').grants_django_staff)


class ApproveActionTest(TestCase):
    def setUp(self):
        self.invoice = make_invoice()

    def test_voiding_an_invoice_is_a_money_decision(self):
        self.client.force_login(make_user('mgr', Role.MANAGER.value))
        self.assertEqual(self.client.get(f'/finance/invoices/{self.invoice.pk}/void/').status_code, 302)
        self.assertEqual(self.client.get(f'/finance/invoices/{self.invoice.pk}/credit-notes/new/').status_code, 302)
        self.client.force_login(make_user('fin', Role.FINANCE.value))
        self.assertEqual(self.client.get(f'/finance/invoices/{self.invoice.pk}/void/').status_code, 200)

    def test_the_role_editor_offers_approve(self):
        self.client.force_login(make_user('chief', Role.ADMIN.value))
        props = self.client.get('/roles/new/', HTTP_X_INERTIA='true').json()['props']
        self.assertIn('approve', [a['key'] for a in props['actions']])


class AdjustableRolesTest(TestCase):
    """The seed is a starting point: an administrator widens a role at /roles/."""

    def test_admin_lets_staff_see_remittances(self):
        staff = make_user('stf', Role.STAFF.value)
        self.assertFalse(can(staff, 'remittance', 'view'))
        self.client.force_login(make_user('chief', Role.ADMIN.value))
        role = RoleDefinition.objects.get(slug='staff')
        granted = [f'{m}:{a}' for m, actions in role.permissions.items() for a in actions] + ['remittance:view']
        self.client.post('/roles/staff/edit/', {'label': 'Staff', 'permissions': granted})
        self.assertTrue(can(User.objects.get(pk=staff.pk), 'remittance', 'view'))


class ReadOnlyDjangoAdminTest(TestCase):
    def test_money_and_audit_records_cannot_be_changed_there(self):
        request = RequestFactory().get('/admin/')
        request.user = User.objects.create_superuser('root', password='pw12345')
        for model in (Invoice, BankTransaction, ActivityLog):
            model_admin = django_admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(request), model)
            self.assertFalse(model_admin.has_change_permission(request), model)
            self.assertFalse(model_admin.has_delete_permission(request), model)
