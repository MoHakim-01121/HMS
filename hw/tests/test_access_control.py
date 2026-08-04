"""Role-based access control and company-access enforcement.

Covers the three things RBAC has to get right:
  * the matrix itself (hw/permissions.py) resolves the role correctly,
  * guarded views actually refuse the actions a role lacks,
  * a user restricted to one company cannot reach the other one, even by
    hand-crafting the session or POSTing the switcher directly.
"""
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from hw.models import ConfirmationLetter, Invoice, UserProfile
from hw.models.user import CompanyAccess, Role
from hw.permissions import (
    allowed_companies, can, can_use_company, default_company,
    get_role, perms_payload, role_matrix,
)
from hw.views.helpers import get_active_company


def make_user(username, role=Role.STAFF.value, company_access=CompanyAccess.ALL.value,
              superuser=False):
    user = User.objects.create_user(username, password="pw12345")
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save()
    UserProfile.objects.update_or_create(
        user=user, defaults={'role': role, 'company_access': company_access},
    )
    # hw/signals.py creates the profile on User post_save and, via get_or_create,
    # leaves it cached on this instance — so the update above is invisible to
    # `user.profile` until the cached relation is dropped.
    user.refresh_from_db()
    return user


class RoleResolutionTests(TestCase):
    def test_profile_role_is_used(self):
        user = make_user("mgr", Role.MANAGER.value)
        self.assertEqual(get_role(user), Role.MANAGER.value)

    def test_superuser_is_always_admin_regardless_of_profile(self):
        user = make_user("root", Role.VIEWER.value, superuser=True)
        self.assertEqual(get_role(user), Role.ADMIN.value)
        self.assertTrue(can(user, 'users', 'delete'))

    def test_user_without_profile_falls_back_to_staff(self):
        user = User.objects.create_user("noprofile", password="pw12345")
        self.assertEqual(get_role(user), Role.STAFF.value)

    def test_anonymous_has_no_role_and_no_permissions(self):
        from django.contrib.auth.models import AnonymousUser
        anon = AnonymousUser()
        self.assertIsNone(get_role(anon))
        self.assertFalse(can(anon, 'cl', 'view'))


class MatrixTests(TestCase):
    def test_admin_has_every_action_on_every_module(self):
        user = make_user("admin1", Role.ADMIN.value)
        for module, actions in role_matrix()[Role.ADMIN.value].items():
            for action in actions:
                self.assertTrue(can(user, module, action), f"{module}.{action}")

    def test_manager_cannot_touch_user_management(self):
        user = make_user("mgr2", Role.MANAGER.value)
        self.assertTrue(can(user, 'invoice', 'delete'))
        self.assertFalse(can(user, 'users', 'view'))
        self.assertFalse(can(user, 'dev', 'view'))

    def test_staff_can_edit_but_not_delete(self):
        user = make_user("staff1", Role.STAFF.value)
        self.assertTrue(can(user, 'cl', 'edit'))
        self.assertTrue(can(user, 'cl', 'create'))
        self.assertFalse(can(user, 'cl', 'delete'))

    def test_staff_sees_remittance_read_only(self):
        user = make_user("staff2", Role.STAFF.value)
        self.assertTrue(can(user, 'remittance', 'view'))
        self.assertFalse(can(user, 'remittance', 'create'))
        self.assertFalse(can(user, 'remittance', 'edit'))

    def test_viewer_can_only_read_and_export(self):
        user = make_user("view1", Role.VIEWER.value)
        self.assertTrue(can(user, 'invoice', 'view'))
        self.assertTrue(can(user, 'invoice', 'export'))
        for action in ('create', 'edit', 'delete'):
            self.assertFalse(can(user, 'invoice', action), action)

    def test_perms_payload_shape_matches_matrix(self):
        user = make_user("view2", Role.VIEWER.value)
        payload = perms_payload(user)
        self.assertEqual(sorted(payload['cl']), ['export', 'view'])
        self.assertNotIn('users', payload)


class ViewGuardTests(TestCase):
    def setUp(self):
        self.cl = ConfirmationLetter.objects.create(
            company="konoz", confirmation_number="KU-CL-9001", guest_name="Guest",
        )

    def login(self, **kwargs):
        user = make_user(f"u{User.objects.count()}", **kwargs)
        self.client.force_login(user)
        return user

    def test_viewer_can_open_list_but_not_the_create_form(self):
        self.login(role=Role.VIEWER.value)
        self.assertEqual(self.client.get("/cl/").status_code, 200)
        resp = self.client.get("/cl/new/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")

    def test_viewer_post_to_delete_is_refused(self):
        self.login(role=Role.VIEWER.value)
        resp = self.client.post(f"/cl/{self.cl.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")
        self.assertTrue(ConfirmationLetter.objects.filter(pk=self.cl.pk).exists())

    def test_staff_delete_is_refused_but_edit_is_allowed(self):
        self.login(role=Role.STAFF.value)
        resp = self.client.post(f"/cl/{self.cl.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")
        self.assertTrue(ConfirmationLetter.objects.filter(pk=self.cl.pk).exists())
        self.assertEqual(self.client.get(f"/cl/{self.cl.pk}/edit/").status_code, 200)

    def test_manager_delete_is_allowed(self):
        self.login(role=Role.MANAGER.value)
        self.client.post(f"/cl/{self.cl.pk}/delete/")
        self.assertFalse(ConfirmationLetter.objects.filter(pk=self.cl.pk).exists())

    def test_user_management_is_admin_only(self):
        self.login(role=Role.MANAGER.value)
        resp = self.client.get("/users/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")

        self.client.logout()
        self.login(role=Role.ADMIN.value)
        self.assertEqual(self.client.get("/users/").status_code, 200)

    def test_style_guide_is_404_for_non_admin(self):
        self.login(role=Role.MANAGER.value)
        self.assertEqual(self.client.get("/dev/style-guide/").status_code, 404)

    def test_cl_new_requires_authentication(self):
        """Regression: cl_new used to carry no auth decorator at all."""
        resp = self.client.get("/cl/new/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_remittance_is_read_only_for_staff(self):
        self.login(role=Role.STAFF.value)
        self.assertEqual(self.client.get("/remittance/").status_code, 200)
        resp = self.client.get("/remittance/new/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")


class CompanyAccessTests(TestCase):
    def setUp(self):
        self.ijabah_only = make_user(
            "ijonly", Role.MANAGER.value, CompanyAccess.IJABAH.value,
        )
        self.both = make_user("bothco", Role.MANAGER.value, CompanyAccess.ALL.value)

    def test_allowed_companies_reflects_profile(self):
        self.assertEqual(allowed_companies(self.ijabah_only), ["ijabah"])
        self.assertEqual(allowed_companies(self.both), ["konoz", "ijabah"])
        self.assertEqual(default_company(self.ijabah_only), "ijabah")

    def test_superuser_may_use_every_company(self):
        root = make_user("root2", Role.VIEWER.value, CompanyAccess.KONOZ.value, superuser=True)
        self.assertEqual(allowed_companies(root), ["konoz", "ijabah"])

    def test_session_company_outside_access_is_clamped(self):
        request = RequestFactory().get("/")
        request.user = self.ijabah_only
        request.session = self.client.session
        request.session["active_company"] = "konoz"  # no longer permitted
        self.assertEqual(get_active_company(request), "ijabah")

    def test_quick_set_ignores_a_company_the_user_cannot_use(self):
        self.client.force_login(self.ijabah_only)
        self.client.get("/")  # seeds the session with the permitted company
        self.client.post("/company/set/", {"company": "konoz"})
        self.assertEqual(self.client.session["active_company"], "ijabah")

    def test_quick_set_accepts_a_permitted_company(self):
        self.client.force_login(self.both)
        self.client.post("/company/set/", {"company": "ijabah"})
        self.assertEqual(self.client.session["active_company"], "ijabah")

    def test_restricted_user_cannot_read_the_other_companys_records(self):
        Invoice.objects.create(
            company="konoz", invoice_type="visa",
            invoice_number="KU-VISA-777", customer_name="Konoz Cust",
        )
        konoz_invoice = Invoice.objects.get(invoice_number="KU-VISA-777")
        self.client.force_login(self.ijabah_only)
        self.client.get("/")
        resp = self.client.get(f"/services/{konoz_invoice.pk}/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 404)

    def test_can_use_company_helper(self):
        self.assertFalse(can_use_company(self.ijabah_only, "konoz"))
        self.assertTrue(can_use_company(self.ijabah_only, "ijabah"))


class SharedPropsTests(TestCase):
    def test_inertia_props_carry_role_and_perms(self):
        user = make_user("propuser", Role.STAFF.value, CompanyAccess.KONOZ.value)
        self.client.force_login(user)
        resp = self.client.get("/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        auth_user = resp.json()["props"]["auth"]["user"]
        self.assertEqual(auth_user["role"], Role.STAFF.value)
        self.assertEqual(auth_user["role_label"], "Staff")
        self.assertEqual(auth_user["companies"], ["konoz"])
        self.assertNotIn("users", auth_user["perms"])
        self.assertIn("edit", auth_user["perms"]["cl"])


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin_mgmt", Role.ADMIN.value)
        self.client.force_login(self.admin)
        self.target = make_user("target", Role.STAFF.value)

    def test_set_access_updates_role_and_company(self):
        self.client.post(f"/users/{self.target.pk}/edit/", {
            "action": "set_access", "role": Role.VIEWER.value,
            "company_access": CompanyAccess.IJABAH.value,
        })
        profile = UserProfile.objects.get(user=self.target)
        self.assertEqual(profile.role, Role.VIEWER.value)
        self.assertEqual(profile.company_access, CompanyAccess.IJABAH.value)

    def test_is_staff_follows_the_role(self):
        self.client.post(f"/users/{self.target.pk}/edit/", {
            "action": "set_access", "role": Role.MANAGER.value, "company_access": "all",
        })
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)

        self.client.post(f"/users/{self.target.pk}/edit/", {
            "action": "set_access", "role": Role.VIEWER.value, "company_access": "all",
        })
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)

    def test_cannot_change_own_role(self):
        self.client.post(f"/users/{self.admin.pk}/edit/", {
            "action": "set_access", "role": Role.VIEWER.value, "company_access": "all",
        })
        self.assertEqual(UserProfile.objects.get(user=self.admin).role, Role.ADMIN.value)

    def test_invalid_role_value_falls_back_instead_of_saving_garbage(self):
        self.client.post(f"/users/{self.target.pk}/edit/", {
            "action": "set_access", "role": "superadmin", "company_access": "mars",
        })
        profile = UserProfile.objects.get(user=self.target)
        self.assertEqual(profile.role, Role.STAFF.value)
        self.assertEqual(profile.company_access, CompanyAccess.ALL.value)

    def test_new_user_gets_the_requested_role(self):
        self.client.post("/users/new/", {
            "username": "freshuser", "password": "pw12345", "password_confirm": "pw12345",
            "role": Role.VIEWER.value, "company_access": CompanyAccess.KONOZ.value,
        })
        created = User.objects.get(username="freshuser")
        self.assertEqual(created.profile.role, Role.VIEWER.value)
        self.assertEqual(created.profile.company_access, CompanyAccess.KONOZ.value)
        self.assertFalse(created.is_staff)

    def test_toggle_active(self):
        self.assertTrue(self.target.is_active)
        self.client.post(f"/users/{self.target.pk}/edit/", {"action": "toggle_active"})
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.client.post(f"/users/{self.target.pk}/edit/", {"action": "toggle_active"})
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
