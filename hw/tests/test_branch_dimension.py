"""FASE C — receiving_account + branch dimension threaded into journal lines."""
from datetime import date

import base64

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase

from hw.models import BankAccount, Branch, CashAccount, Client, Invoice, Reservation
from hw.models.journal import LedgerAccount
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance_helpers import create_payment_record, confirm_payment


class ReceivingAccountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fc', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT FaseC')
        self.inv = Invoice.objects.create(invoice_number='INV-FC-1', customer_name='PT FaseC',
                                          client=self.client_obj)
        self.res = Reservation.objects.create(
            invoice=self.inv, reservation_number='R1', total_sar=5000,
            owner_branch=Branch.objects.get(code='sby'),
        )

    def test_at_most_one_receiving_account(self):
        cash = CashAccount.objects.get(branch_id='sby')
        bank = BankAccount.objects.create(
            branch=Branch.objects.get(code='sby'), name='Ops', currency='SAR',
            ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'),
            bank_name='BCA', account_identifier='1',
        )
        with self.assertRaises(IntegrityError):
            PaymentRecord.objects.create(
                payment_number='PAY-X', invoice=self.inv, client=self.client_obj,
                payment_date=date(2026, 1, 1), amount=1, amount_sar=1,
                method='Cash', status=PaymentRecord.STATUS_PENDING,
 created_by=self.user,
                period=FinancialPeriod.objects.first(),
                bank_account=bank, cash_account=cash,
            )

    def test_create_payment_record_derives_cash_account_from_received_in(self):
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 1, 5), 3000,
            method='Transfer', received_in='jkt', created_by=self.user,
        )
        self.assertEqual(pr.cash_account.branch_id, 'jkt')
        self.assertEqual(pr.receiving_branch_code, 'jkt')

    def test_payment_journal_lines_carry_receiving_branch(self):
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 1, 5), 3000,
            method='Transfer', received_in='jkt', created_by=self.user,
        )
        confirm_payment(pr, self.user)
        lines = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
            journal_entry__reference_id=pr.pk,
        )
        self.assertTrue(lines.exists())
        self.assertTrue(all(l.branch_id == 'jkt' for l in lines))

    def test_charge_receivable_is_branch_revenue_is_hq(self):
        # The owning branch holds the receivable; hotel revenue is HQ's — the
        # branch sells as an agent and remits the full SAR value.
        posting.post_invoice_charge(self.inv, created_by=self.user, entry_date=date(2026, 1, 1))
        lines = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_CHARGE,
            journal_entry__reference_id=self.inv.pk,
        )
        self.assertTrue(lines.exists())
        by_account = {(l.account_id, l.branch_id) for l in lines}
        self.assertEqual(by_account, {('1100-AR', 'sby'), ('4100-INC-HOTEL', 'pusat')})


class PaymentRecordAccountPickerViewTest(TestCase):
    """The Payment List 'Record Payment' dialog posts `account` (cash:<id> /
    bank:<id>) instead of a raw `received_in` string."""

    def setUp(self):
        self.user = User.objects.create_user('acctpick', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT Picker')
        self.inv = Invoice.objects.create(
            invoice_number='INV-PICK-1', customer_name='PT Picker', client=self.client_obj,
        )
        self.jkt_cash = CashAccount.objects.get(branch_id='jkt')

    def test_account_field_sets_cash_account_and_receiving_branch(self):
        proof = SimpleUploadedFile('proof.png', base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
        ), content_type='image/png')
        resp = self.client.post('/finance/payments/record/', {
            'invoice_id': str(self.inv.pk), 'payment_date': '2026-02-01',
            'amount': '4000', 'currency': 'SAR', 'exchange_rate': '1',
            'account': f'cash:{self.jkt_cash.pk}', 'proof': proof,
        })
        self.assertEqual(resp.status_code, 302)
        pr = PaymentRecord.objects.get(invoice=self.inv)
        self.assertEqual(pr.cash_account_id, self.jkt_cash.pk)
        self.assertEqual(pr.receiving_branch_code, 'jkt')

    def test_list_props_expose_account_choices(self):
        resp = self.client.get('/finance/payments/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertIn('account_choices', props)
        self.assertTrue(any(c['branch'] == 'jkt' for c in props['account_choices']))
