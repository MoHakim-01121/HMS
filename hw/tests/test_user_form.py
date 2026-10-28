"""The user form (canvas "User Form"): edit saves name, role and branch, a
password reset and the active flag together."""
from django.contrib.auth.models import User
from django.test import TestCase

from hw.tests.test_branch_scope import make_user


class UserFormTest(TestCase):
    def setUp(self):
        self.admin = make_user('chief', 'admin')
        self.client.force_login(self.admin)
        self.siti = make_user('siti', 'staff', branch='sby')

    def save(self, user, **over):
        data = {'action': 'save', 'full_name': 'Siti Aminah', 'role': 'staff', 'branch': 'sby', 'is_active': 'on'}
        data.update(over)
        return self.client.post(f'/users/{user.pk}/edit/', data, HTTP_X_INERTIA='true')

    def test_edit_page_opens_with_the_users_data(self):
        props = self.client.get(f'/users/{self.siti.pk}/edit/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual((props['edit']['username'], props['form_data']['branch'], props['form_data']['is_active']),
                         ('siti', 'sby', True))
        # An Admin-role account (not a Django superuser) may rename accounts.
        self.assertTrue(props['edit']['can_edit_username'])

    def test_admin_role_renames_another_user(self):
        resp = self.save(self.siti, username='siti.baru')
        self.assertRedirects(resp, '/users/', fetch_redirect_response=False)
        self.assertEqual(User.objects.get(pk=self.siti.pk).username, 'siti.baru')
        from hw.models import ActivityLog
        entry = ActivityLog.objects.filter(model_name='User').latest('id')
        self.assertIn({'field': 'username', 'old': 'siti', 'new': 'siti.baru'}, entry.changes)

    def test_admin_role_renames_their_own_account(self):
        resp = self.save(self.admin, full_name='Chief', role='admin', branch='all', username='chief.baru')
        self.assertRedirects(resp, '/users/', fetch_redirect_response=False)
        self.assertEqual(User.objects.get(pk=self.admin.pk).username, 'chief.baru')

    def test_superuser_renames_an_account(self):
        root = User.objects.create_superuser('root', password='rootpw123')
        self.client.force_login(root)
        resp = self.save(self.siti, username='siti.super')
        self.assertRedirects(resp, '/users/', fetch_redirect_response=False)
        self.assertEqual(User.objects.get(pk=self.siti.pk).username, 'siti.super')

    def test_duplicate_username_saves_nothing(self):
        User.objects.create_user('taken', password='pw12345')
        resp = self.save(self.siti, full_name='Siti Baru', username='TAKEN')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username', resp.json()['props']['errors'])
        siti = User.objects.get(pk=self.siti.pk)
        self.assertEqual((siti.username, siti.get_full_name()), ('siti', ''))

    def test_invalid_username_saves_nothing(self):
        resp = self.save(self.siti, username='bad name!')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username', resp.json()['props']['errors'])
        self.assertEqual(User.objects.get(pk=self.siti.pk).username, 'siti')

    def test_saves_name_role_password_and_active_together(self):
        resp = self.save(self.siti, role='manager', password='baru12345', password_confirm='baru12345', is_active='')
        self.assertRedirects(resp, '/users/', fetch_redirect_response=False)
        siti = User.objects.get(pk=self.siti.pk)
        self.assertEqual((siti.get_full_name(), siti.profile.role, siti.is_active), ('Siti Aminah', 'manager', False))
        self.assertTrue(siti.check_password('baru12345'))

    def test_weak_password_is_rejected_on_edit(self):
        resp = self.save(self.siti, password='password', password_confirm='password')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('password', resp.json()['props']['errors'])
        self.assertTrue(User.objects.get(pk=self.siti.pk).check_password('pw12345'))

    def test_weak_password_is_rejected_on_reset(self):
        resp = self.client.post(f'/users/{self.siti.pk}/edit/', {
            'action': 'reset_password', 'password': 'password', 'password_confirm': 'password',
        })
        self.assertRedirects(resp, '/users/', fetch_redirect_response=False)
        self.siti.refresh_from_db()
        self.assertTrue(self.siti.check_password('pw12345'))

    def test_blank_password_keeps_the_current_one(self):
        self.save(self.siti)
        self.assertTrue(User.objects.get(pk=self.siti.pk).check_password('pw12345'))

    def test_no_one_changes_their_own_role_or_deactivates_themselves(self):
        self.save(self.admin, full_name='Chief', role='staff', branch='all')
        self.save(self.admin, full_name='Chief', role='admin', branch='all', is_active='')
        chief = User.objects.get(pk=self.admin.pk)
        self.assertEqual((chief.profile.role, chief.is_active), ('admin', True))

    def test_mismatched_passwords_save_nothing(self):
        resp = self.save(self.siti, full_name='Siti Baru', password='a1234567', password_confirm='b1234567')
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(User.objects.get(pk=self.siti.pk).get_full_name(), 'Siti Baru')

    def test_only_a_superuser_changes_a_superusers_password(self):
        root = User.objects.create_superuser('root', password='rootpw123')
        self.save(root, full_name='Root', role='admin', branch='all', password='hijack123', password_confirm='hijack123')
        self.client.post(f'/users/{root.pk}/edit/', {'action': 'reset_password', 'password': 'hijack123', 'password_confirm': 'hijack123'})
        self.assertTrue(User.objects.get(pk=root.pk).check_password('rootpw123'))
