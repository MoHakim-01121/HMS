"""Branch scope, phase 2a (access control audit 2026-10-08).

A branch's staff see and act on their own branch only; head office and the
admin role cover every branch. Organisation-wide modules need every branch.
Expenses belong to a branch, never to head office.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.branch_scope import branch_codes, covers_all, operating_branches
from hw.finance import expense_service
from hw.finance.errors import FinanceError
from hw.models import ActivityLog, Branch, Expense, ExpenseCategory, UserBranchAccess
from hw.models.period import FinancialPeriod
from hw.models.user import Role
from hw.permissions import can, perms_payload
from hw.models import CancellationPenalty, Client, PaymentRecord
from hw.tests.factories import make_cl, make_invoice


def make_user(username, role=Role.STAFF.value, branch=None):
    """`branch` None = every branch, else the one branch code the user covers."""
    user = User.objects.create_user(username, password='pw12345')
    profile = user.profile
    profile.role = role
    profile.all_branches = branch is None
    profile.save()
    if branch:
        UserBranchAccess.objects.create(profile=profile, branch_id=branch)
    return User.objects.get(pk=user.pk)


class ScopeRulesTest(TestCase):
    def test_head_office_and_admins_cover_every_branch(self):
        self.assertIsNone(branch_codes(make_user('hq')))
        # The admin role covers every branch even if its profile says otherwise.
        self.assertIsNone(branch_codes(make_user('chief', Role.ADMIN.value, branch='sby')))
        boss = User.objects.create_superuser('root', password='pw12345')
        self.assertTrue(covers_all(boss))

    def test_branch_staff_cover_their_branch(self):
        self.assertEqual(branch_codes(make_user('sby-staff', branch='sby')), {'sby'})

    def test_organisation_wide_modules_need_every_branch(self):
        # A role granted everything below: only the branch scope differs.
        from hw.models.role import RoleDefinition
        every = ['view', 'create', 'edit', 'delete', 'export']
        RoleDefinition.objects.create(slug='ops', label='Ops', order=90, permissions={
            m: every for m in ('journal', 'periods', 'landing', 'hotels')})
        branch_mgr = make_user('sby-mgr', 'ops', branch='sby')
        hq_mgr = make_user('hq-mgr', 'ops')
        for module, action in (('journal', 'view'), ('periods', 'edit'), ('landing', 'view'), ('hotels', 'edit')):
            self.assertFalse(can(branch_mgr, module, action), (module, action))
            self.assertTrue(can(hq_mgr, module, action), (module, action))
        # The shared hotel catalogue stays readable.
        self.assertTrue(can(branch_mgr, 'hotels', 'view'))
        payload = perms_payload(branch_mgr)
        self.assertNotIn('journal', payload)
        self.assertEqual(payload['hotels'], ['export', 'view'])

    def test_branch_staff_are_turned_away_from_the_ledger(self):
        self.client.force_login(make_user('sby-mgr', Role.MANAGER.value, branch='sby'))
        self.assertEqual(self.client.get('/finance/journal/').status_code, 302)


class UserBranchFormTest(TestCase):
    def setUp(self):
        self.client.force_login(make_user('chief', Role.ADMIN.value))
        self.target = make_user('desk')

    def _set(self, **fields):
        self.client.post(f'/users/{self.target.pk}/edit/', {'action': 'set_access', 'role': 'staff', **fields})
        return User.objects.get(pk=self.target.pk).profile

    def test_admin_limits_an_account_to_one_branch_and_back(self):
        profile = self._set(branch='sby')
        self.assertFalse(profile.all_branches)
        self.assertEqual(list(profile.branch_access.values_list('branch_id', flat=True)), ['sby'])
        log = ActivityLog.objects.filter(model_name='User', object_ref='desk').latest('pk')
        self.assertIn({'field': 'branch', 'old': 'all', 'new': 'sby'}, log.changes)

        profile = self._set(branch='all')
        self.assertTrue(profile.all_branches)
        self.assertFalse(profile.branch_access.exists())

    def test_head_office_is_not_a_branch_to_limit_to(self):
        profile = self._set(branch='pusat')
        self.assertTrue(profile.all_branches)  # refused, unchanged

    def test_an_administrator_always_covers_every_branch(self):
        self.client.post(f'/users/{self.target.pk}/edit/', {'action': 'set_access', 'role': 'admin', 'branch': 'sby'})
        self.assertTrue(User.objects.get(pk=self.target.pk).profile.all_branches)

    def test_new_account_gets_its_branch(self):
        self.client.post('/users/new/', {
            'username': 'surabaya1', 'full_name': 'Staf Surabaya', 'role': 'staff', 'branch': 'sby',
            'password': 'pw12345!x', 'password_confirm': 'pw12345!x',
        })
        self.assertEqual(branch_codes(User.objects.get(username='surabaya1')), {'sby'})


class ExpenseBranchTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        Branch.objects.filter(code='jkt').update(is_active=True)
        self.util = ExpenseCategory.objects.get(code='UTIL')
        self.hq = make_user('hq', Role.MANAGER.value)
        self.sby_staff = make_user('sby-staff', Role.FINANCE.value, branch='sby')
        self.sby_exp = self._record('sby', 'Listrik Surabaya')
        self.jkt_exp = self._record('jkt', 'Listrik Jakarta')

    def _record(self, code, vendor, user=None):
        return expense_service.submit_expense(
            branch=Branch.objects.get(code=code), expense_date=date(2026, 3, 1), created_by=user or self.hq,
            vendor=vendor, lines=[{'category': self.util, 'amount': 100}],
        )

    def test_head_office_records_no_expenses(self):
        with self.assertRaisesMessage(FinanceError, 'Pusat'):
            self._record('pusat', 'PLN Pusat')
        self.assertNotIn('pusat', [b.code for b in operating_branches(self.hq)])

    def test_branch_staff_see_only_their_branch(self):
        self.client.force_login(self.sby_staff)
        props = self.client.get('/finance/expenses/?year=all', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual([e['expense_number'] for e in props['expenses']], [self.sby_exp.expense_number])
        self.assertEqual(props['branch_choices'], [{'value': 'sby', 'label': 'Surabaya'}])
        self.assertEqual(sum(props['counts'].values()), 1)

        self.assertEqual(self.client.get(f'/finance/expenses/{self.jkt_exp.pk}/').status_code, 404)
        # A branch's Finance approves, pays and voids — but not another branch's expense.
        for action in ('approve', 'reject', 'pay', 'void'):
            self.assertEqual(self.client.post(f'/finance/expenses/{self.jkt_exp.pk}/{action}/').status_code, 404, action)
        self.jkt_exp.refresh_from_db()
        self.assertEqual(self.jkt_exp.status, Expense.STATUS_SUBMITTED)
        csv = self.client.get('/finance/expenses/export/csv/').content.decode()
        self.assertIn('Listrik Surabaya', csv)
        self.assertNotIn('Listrik Jakarta', csv)

    def test_branch_staff_record_for_their_branch_without_choosing(self):
        self.client.force_login(self.sby_staff)
        self.client.post('/finance/expenses/record/', {
            'expense_date': '2026-03-02', 'vendor': 'ATK Surabaya',
            'lines': '[{"category": "UTIL", "amount": 50, "no_receipt_reason": "Nota hilang"}]',
        })
        self.assertEqual(Expense.objects.get(vendor__name='ATK Surabaya').branch_id, 'sby')

    def test_branch_staff_cannot_record_for_another_branch(self):
        self.client.force_login(self.sby_staff)
        self.client.post('/finance/expenses/record/', {
            'branch': 'jkt', 'expense_date': '2026-03-02', 'vendor': 'Titipan Jakarta',
            'lines': '[{"category": "UTIL", "amount": 50}]',
        })
        self.assertFalse(Expense.objects.filter(vendor__name='Titipan Jakarta').exists())
        # The service refuses it too, whoever calls it.
        with self.assertRaisesMessage(FinanceError, 'di luar akses'):
            self._record('jkt', 'Titipan Jakarta', user=self.sby_staff)
        with self.assertRaisesMessage(FinanceError, 'di luar akses'):
            expense_service.approve_expense(self.jkt_exp, approved_by=self.sby_staff)


class OperationalScopeTest(TestCase):
    """A Surabaya account meets Jakarta's records nowhere: not in lists,
    exports, search, the dashboard or notifications, and opening one is a 404.
    Head office still sees both."""

    def setUp(self):
        Branch.objects.filter(code='jkt').update(is_active=True)
        self.sby_user = make_user('sby-mgr', Role.MANAGER.value, branch='sby')
        self.hq_user = make_user('hq-mgr', Role.MANAGER.value)
        self.records = {code: self._records(code) for code in ('sby', 'jkt')}

    def _records(self, code):
        mark = f'{code.upper()}MARK'
        client = Client.objects.create(name=f'Travel {mark}', owner_branch_id=code)
        cl = make_cl(client=client, check_in=date.today(), reservation_status='CANCELLED')
        cl.confirmation_number = f'{code}{cl.pk}'
        cl.save(update_fields=['confirmation_number'])
        make_cl(client=client, check_in=date.today() + timedelta(days=1))  # an arrival to be notified of
        return {
            'mark': mark, 'client': client, 'cl': cl,
            'invoice': make_invoice(client=client, branch_id=code, due_date=date.today()),
            'penalty': CancellationPenalty.objects.create(
                cl=cl, penalty_number=f'PEN-{mark}', cancellation_date=date.today(), penalty_amount=10),
        }

    def _get(self, url, **params):
        return self.client.get(url, params, HTTP_X_INERTIA='true')

    def test_lists_exports_search_and_dashboard_hold_only_the_users_branch(self):
        self.client.force_login(self.sby_user)
        jkt, sby = self.records['jkt']['mark'], self.records['sby']['mark']
        for url in ('/clients/', '/clients/map/data/', '/cl/', '/cl/export/csv/', '/invoice/',
                    '/invoice/export/csv/', '/finance/penalties/',
                    '/calendar/', '/dashboard/'):
            body = self._get(url).content.decode()
            self.assertNotIn(jkt, body, url)
        self.assertIn(sby, self._get('/clients/').content.decode())
        found = self.client.get('/search/', {'q': 'Travel'}).json()['results']
        self.assertTrue(found)
        self.assertTrue(all(jkt not in str(r) for r in found))
        notifs = self._get('/dashboard/').json()['props']['due_soon_notifs']
        self.assertTrue(notifs)
        self.assertTrue(all(jkt not in str(n) for n in notifs))

    def test_another_branchs_records_do_not_open(self):
        self.client.force_login(self.sby_user)
        jkt = self.records['jkt']
        for url in (f"/clients/{jkt['client'].pk}/", f"/clients/{jkt['client'].pk}/edit/",
                    f"/cl/{jkt['cl'].pk}/", f"/cl/{jkt['cl'].pk}/pdf/",
                    f"/invoice/{jkt['invoice'].pk}/", f"/invoice/{jkt['invoice'].pk}/pdf/",
                    f"/penalty/{jkt['penalty'].pk}/", f"/penalty/{jkt['penalty'].pk}/pdf/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        # Their own branch's records open (the 404s above are not a broken page).
        sby = self.records['sby']
        for url in (f"/clients/{sby['client'].pk}/", f"/cl/{sby['cl'].pk}/", f"/invoice/{sby['invoice'].pk}/",
                    f"/penalty/{sby['penalty'].pk}/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_head_office_sees_every_branch(self):
        self.client.force_login(self.hq_user)
        body = self._get('/clients/').content.decode()
        self.assertIn('SBYMARK', body)
        self.assertIn('JKTMARK', body)
        self.assertEqual(self.client.get(f"/cl/{self.records['jkt']['cl'].pk}/").status_code, 200)

    def test_branch_staff_read_cls_and_penalties_but_do_not_change_them(self):
        self.assertTrue(can(self.sby_user, 'cl', 'view'))
        for module, action in (('cl', 'create'), ('cl', 'edit'), ('penalty', 'create'), ('calendar', 'edit')):
            self.assertFalse(can(self.sby_user, module, action), (module, action))
            self.assertTrue(can(self.hq_user, module, action), (module, action))

    def test_a_branch_client_stays_in_the_branch(self):
        self.client.force_login(self.sby_user)
        self.client.post('/clients/new/', {'name': 'Travel Baru Surabaya'})
        self.assertEqual(Client.objects.get(name='Travel Baru Surabaya').owner_branch_id, 'sby')
        self.client.post('/clients/new/', {'name': 'Travel Titipan', 'owner_branch': 'jkt'})
        self.assertFalse(Client.objects.filter(name='Travel Titipan').exists())



class FinanceScopeTest(TestCase):
    """Money follows the same rule: a Surabaya account works on Surabaya's
    accounts and on Surabaya's clients' payments (also those head office
    received), never on Jakarta's; head office records remittance receipts."""

    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        from hw.tests.factories import make_account, make_remittance
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, MEDIA_ACCEL_REDIRECT='')
        override.enable()
        self.addCleanup(override.disable)

        Branch.objects.filter(code='jkt').update(is_active=True)
        self.maker = User.objects.create_user('maker', password='pw12345')
        self.sby_mgr = make_user('sby-fin', Role.FINANCE.value, branch='sby')
        self.hq_mgr = make_user('hq-fin', Role.FINANCE.value)
        sby_client = Client.objects.create(name='Travel Surabaya', owner_branch_id='sby')
        jkt_client = Client.objects.create(name='Travel Jakarta', owner_branch_id='jkt')
        self.pay = {
            'own': self._pay('PAY-SBYOWN', sby_client, 'sby'),
            'at_hq': self._pay('PAY-SBYATHQ', sby_client, 'pusat'),
            'jkt': self._pay('PAY-JKTOWN', jkt_client, 'jkt'),
            'jkt_at_hq': self._pay('PAY-JKTATHQ', jkt_client, 'pusat'),
        }
        self.jkt_account = make_account('jkt', 'SAR')
        self.sby_rem = make_remittance(date=date(2026, 6, 1), remittance_number='RMT-SBYMARK')
        self.jkt_rem = make_remittance(date=date(2026, 6, 1), remittance_number='RMT-JKTMARK',
                                       from_account=make_account('jkt', 'IDR'))

    def _pay(self, number, client, branch):
        from hw.tests.factories import make_payment
        return make_payment(payment_number=number, payment_date=date(2026, 6, 5), amount=10, amount_sar=10,
                            exchange_rate=1, method='Transfer', client=client, created_by=self.maker,
                            received_in=branch)

    def _body(self, url, **params):
        return self.client.get(url, params, HTTP_X_INERTIA='true').content.decode()

    def test_payments_of_the_branch_and_its_clients_only(self):
        self.client.force_login(self.sby_mgr)
        for url in ('/finance/payments/?year=all', '/finance/payments/export/csv/'):
            body = self._body(url)
            self.assertNotIn('PAY-JKT', body, url)
        body = self._body('/finance/payments/?year=all')
        self.assertIn('PAY-SBYOWN', body)
        self.assertIn('PAY-SBYATHQ', body)  # a Surabaya client paying at head office
        for key in ('jkt', 'jkt_at_hq'):
            self.assertEqual(self.client.get(f"/finance/payments/{self.pay[key].pk}/").status_code, 404, key)
        self.assertEqual(self.client.get(f"/finance/payments/{self.pay['at_hq'].pk}/").status_code, 200)

    def test_payment_accounts_are_the_branchs_and_head_offices(self):
        self.client.force_login(self.sby_mgr)
        props = self.client.get('/finance/payments/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual({a['branch'] for a in props['account_choices']}, {'sby', 'pusat'})
        from django.contrib.messages import get_messages
        before = PaymentRecord.objects.count()
        resp = self.client.post('/finance/payments/record/', {
            'client_id': self.pay['own'].client_id, 'amount': '5', 'payment_date': '2026-06-06',
            'account': self.jkt_account.token, 'method': 'Transfer',
        })
        self.assertIn('Rekening penerima di luar cabang Anda.', [str(m) for m in get_messages(resp.wsgi_request)])
        self.assertEqual(PaymentRecord.objects.count(), before)

    def test_remittances_and_their_receipts(self):
        self.client.force_login(self.sby_mgr)
        body = self._body('/remittance/?year=all')
        self.assertIn('RMT-SBYMARK', body)
        self.assertNotIn('RMT-JKTMARK', body)
        self.assertEqual(self.client.get(f'/remittance/{self.jkt_rem.pk}/').status_code, 404)
        # Head office records what came in; a branch only sends.
        self.assertEqual(self.client.get(f'/remittance/{self.sby_rem.pk}/receipt/').status_code, 404)
        self.client.force_login(self.hq_mgr)
        self.assertEqual(self.client.get(f'/remittance/{self.sby_rem.pk}/receipt/').status_code, 200)

    def test_accounts_and_reports_of_the_branch(self):
        self.client.force_login(self.sby_mgr)
        accounts = self.client.get('/finance/bank-accounts/', HTTP_X_INERTIA='true').json()['props']['accounts']
        self.assertTrue(accounts)
        self.assertTrue(all(a['branch'] == 'sby' for a in accounts), accounts)
        self.assertEqual(self.client.get(f'/finance/bank-accounts/bank/{self.jkt_account.pk}/').status_code, 404)
        flow = self.client.get('/finance/fund-flow/', {'branch': 'jkt'}, HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(flow['branch'], 'sby')
        self.assertEqual([b['value'] for b in flow['branch_choices']], ['sby'])
        for url in ('/finance/statements/', '/finance/ar-aging/', '/finance/ar-aging/export/csv/'):
            self.assertNotIn('Travel Jakarta', self._body(url), url)
        # Setting up accounts is head office's.
        self.assertFalse(can(self.sby_mgr, 'statements', 'edit'))

    def test_proof_files_follow_their_record(self):
        import os
        os.makedirs(os.path.join(self.media, 'payments', 'proof'))
        for key, name in (('jkt_at_hq', 'jkt.pdf'), ('at_hq', 'sby.pdf')):
            with open(os.path.join(self.media, 'payments', 'proof', name), 'wb') as f:
                f.write(b'%PDF-1.4')
            PaymentRecord.objects.filter(pk=self.pay[key].pk).update(proof=f'payments/proof/{name}')
        self.client.force_login(self.sby_mgr)
        self.assertEqual(self.client.get('/media/payments/proof/jkt.pdf').status_code, 404)
        self.assertEqual(self.client.get('/media/payments/proof/sby.pdf').status_code, 200)
