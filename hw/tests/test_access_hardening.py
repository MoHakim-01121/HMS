"""Access control hardening (audit 2026-10-08, phase 1).

- every URL carries a guard, or is listed here as deliberately public /
  login-only (the fence: a new view without a guard fails this file);
- account and role management belong to the admin role only;
- uploads are served only to users allowed to see what they belong to;
- search, the AI assistant, the dashboard and notifications show only modules
  the user may view;
- the public health probe does not leak error details.
"""
import os
import shutil
import tempfile
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver

from hw.models import ActivityLog, Attachment, UserProfile
from hw.models.role import RoleDefinition
from hw.models.uploads import RandomFileName
from hw.models.user import Role
from hw.permissions import can, perms_payload
from hw.tests.factories import make_cl, make_invoice, make_payment

# URLs without a module/role guard, each with the reason it is safe.
PUBLIC_URLS = {
    'login/': 'the login form',
    'logout/': 'ends the session',
    '': 'public landing page',
    'properties/': 'public hotel list of the landing page',
    'health/': 'liveness probe; status only, no details',
}
LOGIN_ONLY_URLS = {
    'dashboard/': 'each panel checks its own module (home_views.home)',
    'search/': 'each result group checks its own module',
    'ai/chat/': 'reads only modules the user may view',
    'ai/chat/reset/': 'clears only the caller\'s own session history',
    'ai/draft/': 'checks the invoice module of the invoice asked for',
    'finance/': 'hub cards filtered by can()',
    'account/profile/': 'own account',
    'account/profile/update/': 'own account',
    'account/avatar/upload/': 'own account',
    'account/avatar/delete/': 'own account',
    'account/language/': 'own account',
    'account/branch/': 'switches only among the branches the user already covers',
}
# Old addresses that only redirect to guarded finance pages.
REDIRECT_URLS = {'clients/<int:pk>/refund/', 'clients/<int:pk>/statement/pdf/'}


def _patterns(resolver=None, prefix=''):
    for p in (resolver or get_resolver()).url_patterns:
        if isinstance(p, URLResolver):
            if str(p.pattern).startswith('admin/'):
                continue  # Django admin guards itself (is_staff + model perms)
            yield from _patterns(p, prefix + str(p.pattern))
        else:
            yield prefix + str(p.pattern), p


def make_user(username, role=Role.STAFF.value):
    user = User.objects.create_user(username, password='pw12345')
    UserProfile.objects.filter(user=user).update(role=role)
    user.refresh_from_db()
    return user


def make_role(slug, permissions):
    RoleDefinition.objects.create(slug=slug, label=slug.title(), permissions=permissions, order=90)
    return make_user(f'{slug}-user', slug)


class UrlFenceTest(TestCase):
    def test_every_url_has_a_guard_or_a_reason(self):
        allowed = set(PUBLIC_URLS) | set(LOGIN_ONLY_URLS) | REDIRECT_URLS
        unguarded = [route for route, p in _patterns()
                     if getattr(p.callback, 'access_guard', None) is None and route not in allowed]
        self.assertEqual(unguarded, [], 'Add @require_perm (or list the URL here with its reason).')

    def test_the_lists_name_only_existing_urls(self):
        routes = {route for route, _ in _patterns()}
        stale = (set(PUBLIC_URLS) | set(LOGIN_ONLY_URLS) | REDIRECT_URLS) - routes
        self.assertEqual(stale, set())

    def test_login_only_urls_turn_anonymous_visitors_away(self):
        for route in LOGIN_ONLY_URLS:
            resp = self.client.post('/' + route)
            self.assertEqual(resp.status_code, 302, route)
            self.assertIn('/login/', resp['Location'], route)


class AdminOnlyUserManagementTest(TestCase):
    """Whoever manages accounts decides everyone's access, so only admins do."""

    def setUp(self):
        self.hr = make_role('hr', {'users': ['view', 'create', 'edit', 'delete'], 'cl': ['view']})

    def test_a_role_row_cannot_grant_user_management(self):
        self.assertFalse(can(self.hr, 'users', 'view'))
        self.assertNotIn('users', perms_payload(self.hr))
        self.assertTrue(can(self.hr, 'cl', 'view'))

    def test_non_admin_cannot_create_an_admin_account(self):
        self.client.force_login(self.hr)
        self.client.post('/users/new/', {
            'username': 'shadow', 'full_name': 'Shadow', 'role': Role.ADMIN.value,
            'password': 'pw12345!x', 'password_confirm': 'pw12345!x',
        })
        self.assertFalse(User.objects.filter(username='shadow').exists())
        self.assertEqual(self.client.get('/roles/').status_code, 302)

    def test_role_editor_drops_user_management_and_logs_the_change(self):
        admin = make_user('chief', Role.ADMIN.value)
        self.client.force_login(admin)
        self.client.post('/roles/new/', {'label': 'Desk', 'permissions': ['users:view', 'cl:view']})
        role = RoleDefinition.objects.get(label='Desk')
        self.assertEqual(role.permissions, {'cl': ['view']})
        self.assertTrue(ActivityLog.objects.filter(model_name='Role', object_ref=role.slug).exists())
        form = self.client.get('/roles/new/', HTTP_X_INERTIA='true').json()['props']
        self.assertNotIn('users', [m['key'] for m in form['modules']])

    def test_admin_keeps_user_management(self):
        admin = make_user('chief', Role.ADMIN.value)
        self.assertTrue(can(admin, 'users', 'delete'))


class ProtectedMediaTest(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.root, MEDIA_ACCEL_REDIRECT='')
        override.enable()
        self.addCleanup(override.disable)
        self.staff = make_user('desk')
        self.hotelier = make_role('hotelier', {'hotels': ['view']})

    def _file(self, rel, data=b'%PDF-1.4 proof'):
        path = os.path.join(self.root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return '/media/' + rel

    def _proof(self):
        """A transfer proof on disk, held by a payment (a proof without its
        record is never served)."""
        url = self._file('payments/proof/a.pdf')
        inv = make_invoice()
        make_payment(payment_number='PAY-PROOF', payment_date=date(2026, 6, 5), amount=1, amount_sar=1,
                     exchange_rate=1, method='Transfer', client=inv.client, created_by=self.staff,
                     proof='payments/proof/a.pdf')
        return url

    def test_anonymous_visitor_is_sent_to_login(self):
        url = self._proof()
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_user_without_the_module_gets_404(self):
        url = self._proof()
        self.client.force_login(self.hotelier)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_permitted_user_gets_the_file_inline(self):
        url = self._proof()
        self.client.force_login(self.staff)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp['Content-Disposition'].startswith('inline'))
        self.assertIn('private', resp['Cache-Control'])
        self.assertEqual(b''.join(resp.streaming_content), b'%PDF-1.4 proof')

    def test_spreadsheets_are_downloaded_not_shown(self):
        url = self._file(f'attachments/cl/{make_cl().pk}/sheet.xlsx', b'PK')
        self.client.force_login(self.staff)
        self.assertTrue(self.client.get(url)['Content-Disposition'].startswith('attachment'))

    def test_behind_nginx_the_file_is_handed_over_by_x_accel(self):
        url = self._proof()
        self.client.force_login(self.staff)
        with override_settings(MEDIA_ACCEL_REDIRECT='/protected-media/'):
            resp = self.client.get(url)
        self.assertEqual(resp['X-Accel-Redirect'], '/protected-media/payments/proof/a.pdf')
        self.assertEqual(resp.content, b'')

    def test_unknown_folders_and_traversal_are_never_served(self):
        self._file('logo.png', b'png')
        admin = make_user('chief', Role.ADMIN.value)
        self.client.force_login(admin)
        self.assertEqual(self.client.get('/media/logo.png').status_code, 404)
        self.assertEqual(self.client.get('/media/payments/proof/../../../config/settings.py').status_code, 404)

    def test_landing_images_stay_public(self):
        url = self._file('landing/team/1/face.png', b'png')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_invoice_attachment_needs_invoice_view(self):
        inv = make_invoice()
        url = self._file(f'attachments/invoice/{inv.pk}/rooming.pdf')
        self.client.force_login(make_role('bookings', {'cl': ['view']}))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(make_role('billing', {'invoice': ['view']}))
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_new_uploads_get_random_names(self):
        name = RandomFileName('payments/proof/')(None, 'Bukti Transfer Ahmad.PDF')
        self.assertRegex(name, r'^payments/proof/[0-9a-f]{32}\.pdf$')
        att = Attachment(cl_id=5, name='paspor.pdf')
        self.assertRegex(att.file.field.upload_to(att, 'paspor.pdf'), r'^attachments/cl/5/[0-9a-f]{32}\.pdf$')


class ModuleScopedViewsTest(TestCase):
    """What a user cannot open in a module must not reach them sideways."""

    def setUp(self):
        self.hotelier = make_role('hotelier', {'hotels': ['view']})
        self.staff = make_user('desk')
        self.cl = make_cl(guest_name='Zubair Fence', check_in=date.today() + timedelta(days=2))

    def test_search_returns_only_permitted_modules(self):
        self.client.force_login(self.hotelier)
        self.assertEqual(self.client.get('/search/', {'q': 'Zubair'}).json()['results'], [])
        self.client.force_login(self.staff)
        self.assertIn('CL', [r['type'] for r in self.client.get('/search/', {'q': 'Zubair'}).json()['results']])

    def test_assistant_refuses_a_user_without_data_access(self):
        self.client.force_login(self.hotelier)
        with mock.patch('hw.views.ai_views.get_chat_reply') as reply:
            resp = self.client.post('/ai/chat/', {'message': 'berapa tamu?'}, content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        reply.assert_not_called()

    def test_assistant_reads_only_permitted_modules(self):
        from hw import ai
        with mock.patch.object(ai, '_call_groq', return_value='ok') as call:
            ai.get_chat_reply('siapa tamu yang check in?', user=self.staff, modules=('invoice',))
        context = call.call_args.args[0][0]['content']
        self.assertNotIn('Zubair', context)
        self.assertNotIn('Confirmation Letter', context)

    def test_draft_message_hides_invoices_outside_the_users_modules(self):
        inv = make_invoice()
        self.client.force_login(self.hotelier)
        resp = self.client.post('/ai/draft/', {'type': 'invoice', 'pk': inv.pk}, content_type='application/json')
        self.assertEqual(resp.status_code, 404)

    def _home(self, user):
        self.client.force_login(user)
        return self.client.get('/dashboard/', HTTP_X_INERTIA='true').json()['props']

    def test_dashboard_draws_only_permitted_panels(self):
        props = self._home(self.hotelier)
        for key in ('sales', 'sold_months', 'checkins', 'top', 'collected', 'money', 'profit'):
            self.assertNotIn(key, props, key)
        self.assertEqual(props['todo'], [])
        self.assertEqual(props['due_soon_count'], 0)

        # Staff get their own dashboard (their CLs, to do, check-ins), with
        # no money blocks.
        props = self._home(self.staff)
        self.assertEqual(props['variant'], 'staff')
        for key in ('sales', 'checkins', 'todo'):
            self.assertIn(key, props, key)
        for key in ('collected', 'money', 'profit'):
            self.assertNotIn(key, props, key)
        self.assertGreaterEqual(props['due_soon_count'], 1)


class HealthCheckTest(TestCase):
    def test_errors_are_logged_not_returned(self):
        with mock.patch('hw.views.dev_views._db_ok', return_value=(False, 'password=hunter2 host=db.internal')), \
                self.assertLogs('hw.views.dev_views', level='ERROR'):
            resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(b'hunter2', resp.content)
        self.assertEqual(resp.json()['db'], 'unreachable')
