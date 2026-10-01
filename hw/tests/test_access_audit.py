"""Schema v2 F9 — akses cabang dan jejak audit pengelolaan user."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from unittest import skipUnless

from hw.models import ActivityLog, UserBranchAccess, UserProfile, log_activity
from hw.models.period import FinancialPeriod
from hw.models.user import Role
from hw.tests.factories import make_invoice


def make_admin(username='boss'):
    user = User.objects.create_user(username, password='pw12345', is_staff=True)
    UserProfile.objects.filter(user=user).update(role=Role.ADMIN.value)
    user.refresh_from_db()
    return user


class BranchAccessTest(TestCase):
    def test_a_profile_can_hold_several_branches(self):
        u = User.objects.create_user('multi', password='pw12345')
        u.profile.all_branches = False
        u.profile.save(update_fields=['all_branches'])
        UserBranchAccess.objects.create(profile=u.profile, branch_id='sby')
        UserBranchAccess.objects.create(profile=u.profile, branch_id='pusat')
        self.assertCountEqual(u.profile.branches, ['sby', 'pusat'])

    def test_one_branch_once_per_profile(self):
        u = User.objects.create_user('dup', password='pw12345')
        UserBranchAccess.objects.create(profile=u.profile, branch_id='sby')
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserBranchAccess.objects.create(profile=u.profile, branch_id='sby')


class ActivityLogTest(TestCase):
    def test_log_survives_its_user(self):
        u = User.objects.create_user('gone', password='pw12345')
        log_activity(u, ActivityLog.ACTION_LOGIN)
        u.delete()
        log = ActivityLog.objects.get()
        self.assertIsNone(log.user)
        self.assertEqual((log.actor_username, log.actor_display), ('gone', 'gone'))

    def test_unknown_action_is_refused(self):
        u = User.objects.create_user('act', password='pw12345')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ActivityLog.objects.create(user=u, actor_username='act', action='hack')


class UserManagementAuditTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_create_role_change_and_delete_are_logged(self):
        self.client.post('/users/new/', {
            'username': 'newbie', 'full_name': 'New Bie', 'password': 'pw12345!x',
            'password_confirm': 'pw12345!x', 'role': Role.STAFF.value,
        })
        target = User.objects.get(username='newbie')
        self.client.post(f'/users/{target.pk}/edit/', {'action': 'set_access', 'role': Role.VIEWER.value})
        self.client.post(f'/users/{target.pk}/delete/')
        logs = list(ActivityLog.objects.filter(model_name='User').order_by('pk').values_list('action', 'object_ref'))
        self.assertEqual(logs, [('create', 'newbie'), ('edit', 'newbie'), ('delete', 'newbie')])

    def test_user_with_finance_documents_cannot_be_deleted(self):
        FinancialPeriod.objects.create(name='2040', date_from=date(2040, 1, 1), date_to=date(2040, 12, 31))
        clerk = User.objects.create_user('clerk', password='pw12345')
        from hw.finance.posting import post_entry
        from hw.finance import accounts as coa
        from hw.models.journal import JournalEntry
        post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT, description='x', entry_date=date(2040, 1, 2),
            lines=[{'account': coa.CASH_SBY, 'debit': 1}, {'account': coa.OPENING_EQUITY, 'credit': 1}],
            created_by=clerk,
        )
        make_invoice()
        self.client.post(f'/users/{clerk.pk}/delete/')
        self.assertTrue(User.objects.filter(pk=clerk.pk).exists())


@skipUnless(connection.vendor == 'postgresql', 'FOREIGN KEY peran hanya di PostgreSQL')
class RoleForeignKeyTest(TestCase):
    def test_profile_role_must_exist(self):
        u = User.objects.create_user('ghost', password='pw12345')
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.filter(user=u).update(role='no_such_role')
            with connection.cursor() as cur:
                cur.execute('SET CONSTRAINTS ALL IMMEDIATE')
