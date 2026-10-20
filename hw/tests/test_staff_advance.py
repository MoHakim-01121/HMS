"""Staff operating cash (uang muka staf), decided 2026-10-17.

The office gives a staff member money with a transfer; they spend it on an
expense "paid with" that advance, which is paid out of the advance the moment
it is approved. The advance may go negative: the staff member fronted the
rest and the office owes them until the next transfer."""
from datetime import date

from hw.finance import exchange_service, expense_service, staff_advance
from hw.finance.accounts import advance_ledger_for, cash_ledger_for
from hw.finance.errors import FinanceError
from hw.models import Expense, MoneyAccount
from hw.models.journal import JournalLine
from hw.tests.test_branch_scope import make_user
from hw.tests.test_expense import DAY, ExpenseBase


class StaffAdvanceTest(ExpenseBase):
    def setUp(self):
        super().setUp()
        self.dimas = make_user('dimas', branch='sby')
        self.give(5_000_000)

    def give(self, amount, holder=None):
        holder = holder or self.dimas
        acc = staff_advance.advance_account(holder, 'sby', 'IDR', create=True)
        exchange_service.record_exchange(
            from_account=self.idr, amount_out=amount, to_account=acc, amount_in=amount,
            exchange_date=date(2026, 9, 5), created_by=self.user,
        )
        return acc

    @property
    def advance(self):
        return staff_advance.advance_account(self.dimas, 'sby', 'IDR')

    def _net(self, code):
        lines = JournalLine.objects.filter(account_id=code)
        return sum(l.debit - l.credit for l in lines)

    def test_giving_money_opens_the_advance_and_moves_its_value(self):
        acc = self.advance
        self.assertEqual((acc.kind, acc.holder, acc.ledger_account_id),
                         (MoneyAccount.KIND_STAFF, self.dimas, advance_ledger_for('sby', 'IDR')))
        self.assertEqual(staff_advance.balance(acc), 5_000_000)
        # 5 jt at the office's 5.000 per riyal = 1.000 SAR moves to the advance.
        self.assertEqual(self._net('1050-ADV-SBY-IDR'), 1_000)
        self.assertEqual(self._net(cash_ledger_for('sby', 'IDR')), 19_000)

    def test_expense_paid_with_the_advance_is_paid_on_approval(self):
        exp = self._submit(amount=2_000_000, spent_by=self.dimas, paid_with=self.advance)
        self.assertEqual(exp.status, Expense.STATUS_SUBMITTED)
        exp = expense_service.approve_expense(exp, approved_by=self.user)
        self.assertEqual(exp.status, Expense.STATUS_PAID)
        self.assertEqual(exp.payment.source_account, self.advance)
        self.assertEqual(exp.payment.payment_date, DAY)
        self.assertEqual(staff_advance.balance(self.advance), 3_000_000)
        self.assertEqual(self._net('1050-ADV-SBY-IDR'), 600)

    def test_the_advance_may_go_negative(self):
        # 7 jt spent out of a 5 jt advance: Dimas fronted 2 jt.
        exp = self._submit(amount=7_000_000, spent_by=self.dimas, paid_with=self.advance)
        expense_service.approve_expense(exp, approved_by=self.user)
        self.assertEqual(staff_advance.balance(self.advance), -2_000_000)
        # 5 jt at the advance's average + 2 jt at the office rate, both 5.000.
        self.assertEqual(Expense.objects.get(pk=exp.pk).total_amount_sar, 1_400)
        self.assertEqual(self._net('1050-ADV-SBY-IDR'), -400)
        # The next transfer closes what the office owes.
        self.give(2_000_000)
        self.assertEqual(staff_advance.balance(self.advance), 0)

    def test_returning_more_than_held_is_refused(self):
        with self.assertRaises(FinanceError):
            exchange_service.record_exchange(
                from_account=self.advance, amount_out=6_000_000, to_account=self.idr, amount_in=6_000_000,
                exchange_date=date(2026, 9, 6), created_by=self.user,
            )

    def test_an_advance_belongs_to_its_holder(self):
        other = make_user('fajar', branch='sby')
        with self.assertRaises(FinanceError):
            self._submit(spent_by=other, paid_with=self.advance)

    def test_office_accounts_are_chosen_at_payment_not_at_submit(self):
        with self.assertRaises(FinanceError):
            self._submit(paid_with=self.idr)

    def test_holders_are_the_branchs_active_users(self):
        jkt = make_user('jkt-staff', branch='jkt')
        gone = make_user('gone', branch='sby')
        gone.is_active = False
        gone.save()
        holders = set(staff_advance.branch_holders('sby'))
        self.assertIn(self.dimas, holders)
        self.assertNotIn(jkt, holders)
        self.assertNotIn(gone, holders)

    def test_line_receipts_and_no_receipt_reason_are_kept(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        slip = SimpleUploadedFile('bensin.jpg', b'\xff\xd8\xff' + b'0' * 100, content_type='image/jpeg')
        exp = self._submit(lines=[
            {'category': self.util, 'amount': 100_000, 'receipts': [slip]},
            {'category': self.util, 'amount': 50_000, 'no_receipt_reason': 'Parkir, tanpa struk'},
        ])
        first, second = exp.lines.order_by('id')
        self.assertEqual([r.name for r in first.receipts.all()], ['bensin.jpg'])
        self.assertEqual(second.no_receipt_reason, 'Parkir, tanpa struk')


class StaffAdvanceViewsTest(ExpenseBase):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.aisyah = make_user('aisyah', branch='sby')

    def _give(self, value, amount=1_000_000):
        return self.client.post('/finance/exchanges/new/', {
            'from_account': self.idr.token, 'to_account': value, 'amount_out': str(amount), 'amount_in': str(amount),
            'exchange_date': '2026-09-05', 'reference': '', 'note': '',
        })

    def test_transfer_form_offers_staff_to_give_to(self):
        props = self.client.get('/finance/exchanges/new/', HTTP_X_INERTIA='true').json()['props']
        self.assertIn(f'give:{self.aisyah.pk}:sby', [s['value'] for s in props['staff_choices']])

    def test_giving_to_a_staff_member_opens_their_advance(self):
        self._give(f'give:{self.aisyah.pk}:sby')
        acc = staff_advance.advance_account(self.aisyah, 'sby', 'IDR')
        self.assertEqual(staff_advance.balance(acc), 1_000_000)
        rows = self.client.get('/finance/bank-accounts/', HTTP_X_INERTIA='true').json()['props']['accounts']
        [row] = [r for r in rows if r['kind'] == 'staff']
        self.assertEqual((row['native_balance'], row['book_balance'], row['given_on']), (1_000_000, 200, '2026-09-05'))
        self.assertEqual(self.client.get(f'/finance/bank-accounts/staff/{acc.pk}/').status_code, 200)

    def test_a_failed_transfer_opens_no_advance(self):
        self._give(f'give:{self.aisyah.pk}:sby', amount=999_000_000)
        self.assertIsNone(staff_advance.advance_account(self.aisyah, 'sby', 'IDR'))

    def test_payment_forms_never_offer_an_advance(self):
        staff_advance.advance_account(self.aisyah, 'sby', 'IDR', create=True)
        props = self.client.get('/finance/payments/', HTTP_X_INERTIA='true').json()['props']
        self.assertFalse([a for a in props['account_choices'] if a['kind'] == 'staff'])
