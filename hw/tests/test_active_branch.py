"""The branch picked in the sidebar (Shell A, 2026-10-16).

A user covering several branches looks at one at a time: lists narrow to the
picked branch, head office is the pick until they choose, and the
organisation's own pages show only while head office is picked. What they may
do (issue a CL for a branch's client, open a record by its link) stays their
coverage.
"""
from django.test import TestCase, override_settings

from hw.models import Client
from hw.models.user import Role
from hw.permissions import can, perms_payload
from hw.tests.factories import make_account, make_cl, make_invoice
from hw.tests.test_branch_scope import make_user


@override_settings(HMS_DEFAULT_BRANCH_PICK=True)
class ActiveBranchTest(TestCase):
    def setUp(self):
        self.admin = make_user('chief', Role.ADMIN.value)
        self.sby_client = Client.objects.create(name='Barokah Umrah', owner_branch_id='sby')
        self.cl = make_cl(client=self.sby_client, confirmation_number='CL-SBY-1')
        self.client.force_login(self.admin)

    def shared_branch(self):
        res = self.client.get('/cl/', HTTP_X_INERTIA='true')
        return res.json()['props']

    def test_head_office_is_the_pick_until_one_is_chosen(self):
        props = self.shared_branch()
        self.assertEqual(props['branch']['current']['code'], 'pusat')
        self.assertEqual([b['code'] for b in props['branch']['choices']], ['pusat', 'sby'])

    def test_lists_narrow_to_the_picked_branch(self):
        self.assertNotIn('CL-SBY-1', str(self.shared_branch()))
        self.client.post('/account/branch/', {'branch': 'sby', 'next': '/cl/'})
        self.assertIn('CL-SBY-1', str(self.shared_branch()))

    def test_a_record_of_another_branch_still_opens_by_its_link(self):
        self.assertEqual(self.client.get(f'/cl/{self.cl.pk}/').status_code, 200)

    def test_an_invoice_of_another_branch_still_opens_by_its_link(self):
        # The CL page links to its invoice; head office is picked, the
        # invoice is Surabaya's.
        invoice = make_invoice(client=self.sby_client, branch_id='sby')
        self.assertEqual(self.client.get(f'/invoice/{invoice.pk}/').status_code, 200)

    def test_an_account_of_another_branch_still_opens_by_its_link(self):
        account = make_account('sby', 'IDR')
        url = f'/finance/bank-accounts/{account.kind}/{account.pk}/'
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_switching_goes_back_to_the_page(self):
        res = self.client.post('/account/branch/', {'branch': 'sby', 'next': '/invoice/'})
        self.assertEqual(res['Location'], '/invoice/')
        res = self.client.post('/account/branch/', {'branch': 'sby', 'next': 'https://evil.example/'})
        self.assertEqual(res['Location'], '/')

    def test_an_unknown_branch_is_refused(self):
        self.assertEqual(self.client.post('/account/branch/', {'branch': 'jkt'}).status_code, 400)

    def test_organisation_pages_whichever_branch_is_picked(self):
        # Head office does not run HMS itself (2026-10-20): a user covering
        # every branch keeps the journal and users while a branch is picked.
        self.client.post('/account/branch/', {'branch': 'sby'})
        props = self.shared_branch()
        self.assertIn('journal', props['auth']['user']['perms'])
        self.assertIn('users', props['auth']['user']['perms'])
        self.assertIn('create', props['auth']['user']['perms']['cl'])
        self.assertEqual(self.client.get('/finance/journal/').status_code, 200)

    def test_a_single_branch_user_has_nothing_to_switch(self):
        self.client.force_login(make_user('sby-staff', Role.STAFF.value, branch='sby'))
        props = self.shared_branch()
        self.assertEqual(props['branch']['current']['code'], 'sby')
        self.assertEqual(props['branch']['choices'], [])
        self.assertEqual(self.client.post('/account/branch/', {'branch': 'pusat'}).status_code, 400)
