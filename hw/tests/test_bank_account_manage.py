"""Bank accounts managed from the UI (Bank Balances) + invoice branch "Pay to"."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Invoice, Reservation
from hw.models.bank import BankAccount
from hw.models.period import FinancialPeriod


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


def activate_jkt():
    # Migration 0081 seeds Jakarta inactive; the dev/prod data has it active.
    from hw.models import Branch
    Branch.objects.filter(code='jkt').update(is_active=True)


def post_data(**over):
    data = {
        'branch': 'sby', 'bank_name': 'Bank Mandiri', 'account_identifier': '1400550011119',
        'account_name': 'PT Konoz United', 'currency': 'IDR', 'ledger_account': '',
        'show_on_invoice': 'on', 'is_active': 'on', 'note': '',
    }
    data.update(over)
    return data


class BankAccountManageTests(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.admin = make_user('bank_admin', 'admin')
        self.staff = make_user('bank_staff', 'staff')

    def test_admin_creates_account_with_default_branch_ledger(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/finance/bank-accounts/new/', post_data())
        self.assertEqual(resp.status_code, 302)
        acc = BankAccount.objects.get(account_identifier='1400550011119')
        self.assertEqual(acc.branch_id, 'sby')
        self.assertEqual(acc.ledger_account_id, '1000-KAS-SBY')
        self.assertTrue(acc.show_on_invoice)
        self.assertEqual(str(acc), 'Bank Mandiri 1400550011119 (IDR)')

    def test_duplicate_account_is_rejected(self):
        self.client.force_login(self.admin)
        self.client.post('/finance/bank-accounts/new/', post_data())
        resp = self.client.post('/finance/bank-accounts/new/', post_data(), HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('account_identifier', resp.json()['props']['errors'])
        self.assertEqual(BankAccount.objects.filter(account_identifier='1400550011119').count(), 1)

    def test_required_fields(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/finance/bank-accounts/new/', post_data(bank_name='', account_identifier='', branch='zzz'), HTTP_X_INERTIA='true')
        errors = resp.json()['props']['errors']
        self.assertTrue({'bank_name', 'account_identifier', 'branch'} <= set(errors))

    def test_staff_cannot_create(self):
        self.client.force_login(self.staff)
        self.client.post('/finance/bank-accounts/new/', post_data())
        self.assertFalse(BankAccount.objects.filter(account_identifier='1400550011119').exists())

    def test_edit_deactivate_clears_invoice_flag(self):
        self.client.force_login(self.admin)
        self.client.post('/finance/bank-accounts/new/', post_data())
        acc = BankAccount.objects.get(account_identifier='1400550011119')
        self.client.post(f'/finance/bank-accounts/{acc.pk}/edit/', post_data(is_active=''))
        acc.refresh_from_db()
        self.assertFalse(acc.is_active)
        self.assertFalse(acc.show_on_invoice)

    def test_list_shows_inactive_and_flag(self):
        self.client.force_login(self.admin)
        self.client.post('/finance/bank-accounts/new/', post_data(is_active=''))
        resp = self.client.get('/finance/bank-accounts/', HTTP_X_INERTIA='true')
        rows = [a for a in resp.json()['props']['accounts'] if a.get('account_identifier') == '1400550011119']
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['is_active'])


class InvoicePayToTests(TestCase):
    def setUp(self):
        activate_jkt()
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.admin = make_user('iv_admin', 'admin')
        self.client.force_login(self.admin)
        self.client.post('/finance/bank-accounts/new/', post_data())
        self.client.post('/finance/bank-accounts/new/', post_data(branch='jkt', account_identifier='999', bank_name='BSI'))
        self.client.post('/finance/bank-accounts/new/', post_data(account_identifier='555', show_on_invoice=''))

    def test_infer_branch_from_reservation_owner(self):
        inv = Invoice.objects.create(invoice_type='hotel', invoice_number='INV-BR-1', customer_name='X', currency='SAR')
        self.assertEqual(inv.infer_branch_id(), 'sby')  # default
        Reservation.objects.create(invoice=inv, reservation_number='R1', hotel='H', owner_branch_id='jkt')
        self.assertEqual(inv.infer_branch_id(), 'jkt')

    def test_detail_lists_only_flagged_accounts_of_invoice_branch(self):
        inv = Invoice.objects.create(invoice_type='hotel', invoice_number='INV-BR-2', customer_name='X', currency='SAR', branch_id='sby')
        resp = self.client.get(f'/invoice/{inv.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual([a['account_identifier'] for a in props['pay_to']], ['1400550011119'])
        self.assertEqual(props['invoice']['branch']['code'], 'sby')

    def test_draft_message_uses_the_same_pay_to_accounts(self):
        from hw.ai import generate_draft_message
        inv = Invoice.objects.create(invoice_type='hotel', invoice_number='INV-BR-3', customer_name='X', currency='SAR', branch_id='sby')
        Reservation.objects.create(invoice=inv, reservation_number='R3', hotel='H', total_sar=1000)
        msg = generate_draft_message('invoice', inv)
        self.assertIn('Informasi Pembayaran:', msg)
        self.assertIn('No. Rekening : 1400550011119', msg)
        self.assertNotIn('555', msg)   # not flagged for invoices
        self.assertNotIn('999', msg)   # other branch
        self.assertNotIn('Informasi Pembayaran', generate_draft_message('invoice_lunas', inv))

    def test_draft_message_omits_payment_block_without_pay_to(self):
        from hw.ai import generate_draft_message
        inv = Invoice.objects.create(invoice_type='hotel', invoice_number='INV-BR-4', customer_name='X', currency='SAR', branch_id='pusat')
        self.assertNotIn('Informasi Pembayaran', generate_draft_message('invoice', inv))


class BankAccountGuardTests(TestCase):
    """Regression coverage for the review findings on bank account management."""

    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.admin = make_user('guard_admin', 'admin')
        self.client.force_login(self.admin)
        self.client.post('/finance/bank-accounts/new/', post_data())
        self.acc = BankAccount.objects.get(account_identifier='1400550011119')

    def test_ledger_outside_cash_class_is_rejected(self):
        resp = self.client.post('/finance/bank-accounts/new/',
                                post_data(account_identifier='777', ledger_account='1100-AR'), HTTP_X_INERTIA='true')
        self.assertIn('ledger_account', resp.json()['props']['errors'])
        self.assertFalse(BankAccount.objects.filter(account_identifier='777').exists())

    def test_name_is_not_doubled(self):
        self.assertEqual(str(self.acc), 'Bank Mandiri 1400550011119 (IDR)')

    def test_account_with_statement_keeps_branch_and_currency(self):
        from hw.models import BankStatement
        BankStatement.objects.create(bank_account=self.acc, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                     opening_balance=0, closing_balance=0)
        self.client.post(f'/finance/bank-accounts/{self.acc.pk}/edit/', post_data(branch='jkt', currency='USD'))
        self.acc.refresh_from_db()
        self.assertEqual((self.acc.branch_id, self.acc.currency), ('sby', 'IDR'))

    def test_inactive_account_does_not_resolve(self):
        from hw.views.helpers import resolve_money_account
        self.assertEqual(resolve_money_account(f'bank:{self.acc.pk}')[0], self.acc)
        self.acc.is_active = False
        self.acc.save()
        self.assertEqual(resolve_money_account(f'bank:{self.acc.pk}'), (None, None))


class InvoiceFormBranchTests(TestCase):
    def setUp(self):
        import json
        from hw.models import Client
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        activate_jkt()
        self.client.force_login(make_user('form_admin', 'admin'))
        self.c = Client.objects.create(name='PT Branch')
        self.base = {
            'customer_name': 'PT Branch', 'client_id': str(self.c.pk),
            'issued_date': '2026-01-01', 'due_date': '',
            'reservations': json.dumps([{'reservation_number': 'R1', 'hotel': 'H', 'check_in': '', 'check_out': '', 'reservation_total': '100'}]),
            'payments': '[]',
        }

    def test_picked_branch_is_saved(self):
        self.client.post('/invoice/new/', {**self.base, 'invoice_number': 'INV-FB-1', 'branch': 'jkt'})
        self.assertEqual(Invoice.objects.get(invoice_number='INV-FB-1').branch_id, 'jkt')

    def test_automatic_branch_falls_back_to_default(self):
        self.client.post('/invoice/new/', {**self.base, 'invoice_number': 'INV-FB-2', 'branch': ''})
        self.assertEqual(Invoice.objects.get(invoice_number='INV-FB-2').branch_id, 'sby')


class OpeningBalanceTests(TestCase):
    """The account's real opening balance anchors the cash book as one row."""

    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.client.force_login(make_user('ob_admin', 'admin'))

    def _row(self, acc):
        from hw.models import BankTransaction
        return BankTransaction.objects.filter(source_type='OpeningBalanceBank', source_id=acc.pk).first()

    def test_opening_balance_becomes_one_cash_row_that_follows_edits(self):
        self.client.post('/finance/bank-accounts/new/', post_data(opening_balance='25000000', opening_date='2026-09-01'))
        acc = BankAccount.objects.get()
        row = self._row(acc)
        self.assertEqual((row.direction, row.currency, row.amount, row.transaction_date, row.status),
                         ('in', 'IDR', 25_000_000, date(2026, 9, 1), 'posted'))

        self.client.post(f'/finance/bank-accounts/{acc.pk}/edit/', post_data(opening_balance='30000000', opening_date='2026-09-02'))
        row.refresh_from_db()
        self.assertEqual((row.amount, row.transaction_date), (30_000_000, date(2026, 9, 2)))
        from hw.models import BankTransaction
        self.assertEqual(BankTransaction.objects.filter(source_type='OpeningBalanceBank').count(), 1)

        self.client.post(f'/finance/bank-accounts/{acc.pk}/edit/', post_data(opening_balance='', opening_date=''))
        row.refresh_from_db()
        self.assertEqual(row.status, 'voided')

    def test_balance_without_date_is_refused(self):
        resp = self.client.post('/finance/bank-accounts/new/', post_data(opening_balance='100'), HTTP_X_INERTIA='true')
        self.assertIn('opening_date', resp.json()['props']['errors'])
        self.assertFalse(BankAccount.objects.exists())

    def test_opening_balance_alone_does_not_lock_the_currency(self):
        self.client.post('/finance/bank-accounts/new/', post_data(opening_balance='100', opening_date='2026-09-01'))
        acc = BankAccount.objects.get()
        props = self.client.get(f'/finance/bank-accounts/{acc.pk}/edit/', HTTP_X_INERTIA='true').json()['props']
        self.assertFalse(props['locked'])
