"""Roles as editable data rather than a hardcoded matrix.

Three things have to hold once the matrix lives in the database:

  * an edit made through the UI changes what ``can()`` answers, immediately —
    including invalidating the cache that makes ``can()`` cheap,
  * the guards that keep an administrator from locking themselves out survive
    the move (the admin role, your own role, built-in roles, orphaned users),
  * a role row can never grant a module or action this build does not guard.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hw.models import RoleDefinition, UserProfile
from hw.models.user import CompanyAccess, Role
from hw.permissions import ACTIONS, MODULES, can, perms_payload, role_matrix

# Inertia only serialises props to JSON when the client announces itself;
# without this header the same view renders the HTML bootstrap page.
INERTIA = {'HTTP_X_INERTIA': 'true'}


def make_user(username, role=Role.STAFF.value, superuser=False):
    user = User.objects.create_user(username, password="pw12345")
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save()
    UserProfile.objects.update_or_create(
        user=user,
        defaults={'role': role, 'company_access': CompanyAccess.ALL.value},
    )
    user.refresh_from_db()
    return user


class SeedTests(TestCase):
    def test_migration_seeded_the_four_builtin_roles(self):
        slugs = set(RoleDefinition.objects.values_list('slug', flat=True))
        self.assertEqual(slugs, {'admin', 'manager', 'staff', 'viewer'})
        self.assertTrue(all(RoleDefinition.objects.values_list('is_system', flat=True)))

    def test_seeded_matrix_matches_the_behaviour_it_replaced(self):
        matrix = role_matrix()
        self.assertEqual(matrix['admin'], {m: set(ACTIONS) for m in MODULES})
        self.assertNotIn('users', matrix['manager'])
        self.assertNotIn('dev', matrix['manager'])
        self.assertEqual(matrix['staff']['remittance'], {'view', 'export'})
        self.assertNotIn('delete', matrix['staff']['cl'])
        self.assertEqual(matrix['viewer']['cl'], {'view', 'export'})


class LiveMatrixTests(TestCase):
    def test_editing_a_row_changes_what_can_answers(self):
        user = make_user("s1", Role.STAFF.value)
        self.assertFalse(can(user, 'cl', 'delete'))

        role = RoleDefinition.objects.get(slug='staff')
        role.permissions = {**role.permissions, 'cl': ['view', 'create', 'edit', 'delete', 'export']}
        role.save()

        self.assertTrue(can(user, 'cl', 'delete'))

    def test_saving_a_role_invalidates_the_cached_matrix(self):
        role_matrix()  # prime the cache
        role = RoleDefinition.objects.get(slug='viewer')
        role.permissions = {'cl': ['view']}
        role.save()
        self.assertEqual(role_matrix()['viewer'], {'cl': {'view'}})

    def test_admin_is_full_access_even_if_the_row_is_emptied(self):
        role = RoleDefinition.objects.get(slug='admin')
        role.permissions = {}
        role.save()

        admin = make_user("a1", 'admin')
        self.assertTrue(can(admin, 'users', 'delete'))
        self.assertEqual(role_matrix()['admin'], {m: set(ACTIONS) for m in MODULES})

    def test_unknown_modules_and_actions_are_ignored(self):
        role = RoleDefinition.objects.get(slug='viewer')
        role.permissions = {'cl': ['view', 'teleport'], 'nonexistent': ['view']}
        role.save()

        user = make_user("v1", 'viewer')
        self.assertTrue(can(user, 'cl', 'view'))
        self.assertFalse(can(user, 'cl', 'teleport'))
        self.assertNotIn('nonexistent', perms_payload(user))

    def test_a_custom_role_works_end_to_end(self):
        RoleDefinition.objects.create(
            slug='auditor', label='Auditor',
            permissions={'invoice': ['view', 'export'], 'remittance': ['view']},
        )
        user = make_user("aud", 'auditor')
        self.assertTrue(can(user, 'invoice', 'export'))
        self.assertFalse(can(user, 'invoice', 'edit'))
        self.assertFalse(can(user, 'cl', 'view'))
        self.assertEqual(
            perms_payload(user),
            {'invoice': ['export', 'view'], 'remittance': ['view']},
        )


class RoleViewAccessTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", 'admin')

    def test_manager_cannot_reach_the_role_screens(self):
        make_user("mgr", Role.MANAGER.value)
        self.client.force_login(User.objects.get(username="mgr"))
        response = self.client.get(reverse('role_list'))
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_admin_sees_the_matrix_shape(self):
        self.client.force_login(User.objects.get(username="boss"))
        response = self.client.get(reverse('role_list'), **INERTIA)
        self.assertEqual(response.status_code, 200)
        props = response.json()['props']
        self.assertEqual(len(props['roles']), 4)
        self.assertEqual([m['key'] for m in props['modules']], list(MODULES))
        self.assertEqual([a['key'] for a in props['actions']], list(ACTIONS))

    def test_creating_a_role_through_the_form(self):
        self.client.force_login(User.objects.get(username="boss"))
        response = self.client.post(reverse('role_new'), {
            'label': 'Front Desk',
            'description': 'Handles walk-ins.',
            'permissions': ['cl:view', 'cl:create', 'hotels:view'],
        })
        self.assertRedirects(response, reverse('role_list'), fetch_redirect_response=False)

        role = RoleDefinition.objects.get(slug='front-desk')
        self.assertEqual(role.permissions, {'cl': ['create', 'view'], 'hotels': ['view']})
        self.assertFalse(role.is_system)
        self.assertFalse(role.grants_django_staff)

    def test_a_role_with_no_permissions_is_rejected(self):
        self.client.force_login(User.objects.get(username="boss"))
        response = self.client.post(reverse('role_new'), {'label': 'Ghost'}, **INERTIA)
        self.assertEqual(response.status_code, 200)
        self.assertIn('permissions', response.json()['props']['errors'])
        self.assertFalse(RoleDefinition.objects.filter(label='Ghost').exists())

    def test_posted_permissions_outside_the_matrix_are_dropped(self):
        self.client.force_login(User.objects.get(username="boss"))
        self.client.post(reverse('role_new'), {
            'label': 'Sneaky',
            'permissions': ['cl:view', 'billing:delete', 'cl:teleport'],
        })
        role = RoleDefinition.objects.get(slug='sneaky')
        self.assertEqual(role.permissions, {'cl': ['view']})

    def test_editing_a_role_syncs_django_staff_for_its_members(self):
        member = make_user("v2", 'viewer')
        self.assertFalse(member.is_staff)

        self.client.force_login(User.objects.get(username="boss"))
        self.client.post(reverse('role_edit', args=['viewer']), {
            'label': 'Viewer',
            'permissions': ['cl:view'],
            'grants_django_staff': '1',
        })
        member.refresh_from_db()
        self.assertTrue(member.is_staff)


class LockoutGuardTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", 'admin')
        self.client.force_login(User.objects.get(username="boss"))

    def test_the_admin_role_cannot_be_edited(self):
        before = RoleDefinition.objects.get(slug='admin').permissions
        response = self.client.post(reverse('role_edit', args=['admin']), {
            'label': 'Administrator', 'permissions': ['cl:view'],
        })
        self.assertRedirects(response, reverse('role_list'), fetch_redirect_response=False)
        self.assertEqual(RoleDefinition.objects.get(slug='admin').permissions, before)

    def test_the_admin_role_cannot_be_deleted(self):
        self.client.post(reverse('role_delete', args=['admin']))
        self.assertTrue(RoleDefinition.objects.filter(slug='admin').exists())

    def test_builtin_roles_cannot_be_deleted(self):
        self.client.post(reverse('role_delete', args=['viewer']))
        self.assertTrue(RoleDefinition.objects.filter(slug='viewer').exists())

    def test_you_cannot_edit_your_own_role(self):
        # A non-superuser standing on a custom role that grants user management.
        RoleDefinition.objects.create(
            slug='ops-lead', label='Ops Lead',
            permissions={m: list(ACTIONS) for m in MODULES},
        )
        make_user("lead", 'ops-lead')
        self.client.logout()
        self.client.force_login(User.objects.get(username="lead"))

        response = self.client.post(reverse('role_edit', args=['ops-lead']), {
            'label': 'Ops Lead', 'permissions': ['cl:view'],
        })
        self.assertRedirects(response, reverse('role_list'), fetch_redirect_response=False)
        self.assertEqual(
            RoleDefinition.objects.get(slug='ops-lead').permissions,
            {m: list(ACTIONS) for m in MODULES},
        )

    def test_deleting_a_role_moves_its_members_to_the_chosen_role(self):
        RoleDefinition.objects.create(
            slug='temp', label='Temp', permissions={'cl': ['view']},
        )
        member = make_user("tmp1", 'temp')

        self.client.post(reverse('role_delete', args=['temp']), {'reassign_to': 'viewer'})

        self.assertFalse(RoleDefinition.objects.filter(slug='temp').exists())
        member.refresh_from_db()
        self.assertEqual(member.profile.role, 'viewer')
        self.assertTrue(can(member, 'cl', 'view'))

    def test_deleting_with_an_unknown_target_falls_back_to_staff(self):
        RoleDefinition.objects.create(
            slug='temp2', label='Temp 2', permissions={'cl': ['view']},
        )
        member = make_user("tmp2", 'temp2')

        self.client.post(reverse('role_delete', args=['temp2']), {'reassign_to': 'made-up'})

        member.refresh_from_db()
        self.assertEqual(member.profile.role, Role.STAFF.value)


class UserAssignmentTests(TestCase):
    def setUp(self):
        make_user("boss", 'admin')
        self.client.force_login(User.objects.get(username="boss"))

    def test_a_custom_role_can_be_assigned_to_an_account(self):
        RoleDefinition.objects.create(
            slug='auditor', label='Auditor', permissions={'invoice': ['view']},
        )
        target = make_user("aud2", Role.STAFF.value)

        self.client.post(reverse('user_edit', args=[target.pk]), {
            'action': 'set_access', 'role': 'auditor', 'company_access': 'all',
        })
        target.refresh_from_db()
        self.assertEqual(target.profile.role, 'auditor')
        self.assertTrue(can(target, 'invoice', 'view'))

    def test_an_unknown_role_falls_back_instead_of_being_stored(self):
        target = make_user("u3", Role.VIEWER.value)
        self.client.post(reverse('user_edit', args=[target.pk]), {
            'action': 'set_access', 'role': 'wizard', 'company_access': 'all',
        })
        target.refresh_from_db()
        self.assertNotEqual(target.profile.role, 'wizard')

    def test_the_role_picker_offers_custom_roles(self):
        RoleDefinition.objects.create(
            slug='auditor', label='Auditor', description='Reads the books.',
            permissions={'invoice': ['view']},
        )
        response = self.client.get(reverse('user_list'), **INERTIA)
        choices = response.json()['props']['role_choices']
        self.assertIn(
            {'value': 'auditor', 'label': 'Auditor', 'description': 'Reads the books.'},
            choices,
        )
