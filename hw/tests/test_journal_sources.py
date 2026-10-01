"""Schema v2 F8 — sumber jurnal bertipe, satu dimensi baris invoice, nominal asli."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance.errors import FinanceError
from hw.finance.hashing import verify_chain
from hw.finance.posting import _split_native, native, post_entry, reverse_entry
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_account, make_hotel_line, make_invoice


class JournalSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('jsrc', password='x')
        FinancialPeriod.objects.create(name='2040', date_from=date(2040, 1, 1), date_to=date(2040, 12, 31))
        self.invoice = make_invoice()

    def _post(self, lines=None, **kw):
        return post_entry(
            entry_type=kw.pop('entry_type', JournalEntry.TYPE_ADJUSTMENT), description='t',
            entry_date=date(2040, 1, 10),
            lines=lines or [
                {'account': coa.CASH_SBY, 'debit': 100},
                {'account': coa.OPENING_EQUITY, 'credit': 100},
            ],
            created_by=self.user, **kw,
        )

    def test_source_is_a_typed_foreign_key(self):
        e = self._post(entry_type=JournalEntry.TYPE_CHARGE, source_type='Invoice', source_id=self.invoice.pk)
        self.assertEqual(e.source_invoice_id, self.invoice.pk)
        self.assertEqual((e.source_type, e.source_id), ('Invoice', self.invoice.pk))
        self.assertEqual(list(JournalEntry.objects.for_source('Invoice', self.invoice.pk)), [e])
        self.assertEqual(list(self.invoice.journal_entries.all()), [e])

    def test_manual_entry_has_no_source(self):
        e = self._post()
        self.assertEqual(e.source_type, '')
        self.assertIsNone(e.source_id)

    def test_alias_needs_its_entry_type(self):
        with self.assertRaises(FinanceError):
            self._post(entry_type=JournalEntry.TYPE_REMITTANCE, source_type='RemittanceDiff', source_id=1)

    def test_unknown_source_is_refused(self):
        with self.assertRaises(FinanceError):
            self._post(source_type='Visit', source_id=1)

    def test_reversal_points_at_original_only_once(self):
        e = self._post(entry_type=JournalEntry.TYPE_CHARGE, source_type='Invoice', source_id=self.invoice.pk)
        rev = reverse_entry(e, reversal_date=date(2040, 1, 11), created_by=self.user)
        self.assertTrue(rev.is_reversal)
        self.assertEqual(rev.source_type, 'JournalEntry')
        self.assertIsNone(rev.source_invoice_id)
        self.assertEqual(e.reversed_by, rev)
        self.assertEqual(list(JournalEntry.objects.for_source('Invoice', self.invoice.pk).live()), [])
        with self.assertRaises(FinanceError):
            reverse_entry(e, reversal_date=date(2040, 1, 12), created_by=self.user)

    def test_database_refuses_two_sources(self):
        e = self._post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            JournalEntry.objects.create(
                entry_number='JE-X', entry_type=JournalEntry.TYPE_CHARGE, description='x',
                entry_date=date(2040, 1, 10), period=e.period,
                source_invoice=self.invoice, reverses=e,
            )

    def test_invoice_line_must_belong_to_the_invoice(self):
        line = make_hotel_line(self.invoice)
        other = make_invoice()
        with self.assertRaises(FinanceError):
            self._post(lines=[
                {'account': coa.AR, 'debit': 100, 'client': other.client_id, 'invoice': other.pk, 'invoice_line': line.pk},
                {'account': coa.OPENING_EQUITY, 'credit': 100},
            ])

    def test_invoice_is_filled_from_the_line(self):
        line = make_hotel_line(self.invoice)
        e = self._post(lines=[
            {'account': coa.AR, 'debit': 100, 'client': self.invoice.client_id, 'invoice_line': line.pk},
            {'account': coa.OPENING_EQUITY, 'credit': 100},
        ])
        self.assertEqual(e.lines.get(debit=100).invoice_id, self.invoice.pk)


class NativeAmountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('jnat', password='x')
        FinancialPeriod.objects.create(name='2040', date_from=date(2040, 1, 1), date_to=date(2040, 12, 31))

    def test_sar_account_has_no_native_columns(self):
        self.assertEqual(native(make_account('sby', 'SAR'), 500, 1), {})

    def test_foreign_cash_leg_keeps_its_amount_and_balances_in_sar(self):
        idr = make_account('sby', 'IDR')
        e = post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT, description='idr', entry_date=date(2040, 2, 1),
            lines=[
                {'account': idr.ledger_account_id, 'debit': 100, **native(idr, 425_000, 4250.123456789)},
                {'account': coa.OPENING_EQUITY, 'credit': 100},
            ],
            created_by=self.user,
        )
        cash = e.lines.get(debit=100)
        self.assertEqual((cash.currency, cash.amount_txn), ('IDR', 425_000))
        self.assertEqual(str(cash.fx_rate), '4250.12345679')
        self.assertTrue(e.is_balanced)
        self.assertEqual(verify_chain(), [])

    def test_split_native_puts_rounding_on_the_last_part(self):
        self.assertEqual(_split_native(1000, [1, 1, 1]), [333, 333, 334])
        self.assertEqual(sum(_split_native(425_001, [70, 30])), 425_001)
