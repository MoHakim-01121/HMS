"""Bank statements in the account currency: CSV import, IDR reconciliation
against the cash book, and suggested (never automatic) matches."""
from datetime import date

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from hw.finance import reconciliation_service as rs
from hw.finance import statement_import as si
from hw.finance.bank_ledger import sync_opening_balance
from hw.finance.errors import FinanceError
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import BankAccount, BankStatement, Client, Invoice, LedgerAccount
from hw.models.bank_transaction import BankTransaction
from hw.models.period import FinancialPeriod

MANDIRI = '''Account No,Date,Val. Date,Transaction Code,Description,Description,Reference No.,Debit,Credit,Balance
1400012345678,03/09/2026,03/09/2026,1234,TRANSFER DARI PT ALPHA,INV-1,REF001,0.00,"49,000,000.00","84,000,000.00"
1400012345678,04/09/2026,04/09/2026,1236,BIAYA ADMIN,,REF003,"15,000.00",0.00,"83,985,000.00"
'''

BCA = '''Informasi Rekening - Mutasi Rekening
No. rekening : 1234567890
Tanggal Transaksi,Keterangan,Cabang,Jumlah,Saldo
'03/09,'TRSF E-BANKING CR PT BETA,'0000,"1,500,000.00 CR","36,500,000.00"
'04/09,'BIAYA ADM,'0000,"15,000.00 DB","36,485,000.00"
'PEND,'SETORAN,'0000,"100,000.00 CR",
'''

SEMICOLON_ID = '''Tanggal;Keterangan;Debet;Kredit;Saldo
05-09-2026;Setoran tunai;;2.500.000,00;12.500.000,00
06-09-2026;Tarik tunai;1.000.000,00;;11.500.000,00
'''


class ParserTest(SimpleTestCase):
    def test_mandiri(self):
        r = si.parse(MANDIRI)
        self.assertEqual([(l['direction'], l['amount']) for l in r['lines']], [('in', 49_000_000), ('out', 15_000)])
        self.assertEqual((r['opening_balance'], r['closing_balance']), (35_000_000, 83_985_000))
        self.assertEqual((r['period_start'], r['period_end']), (date(2026, 9, 3), date(2026, 9, 4)))
        self.assertEqual(r['lines'][0]['reference'], 'REF001')

    def test_bca_amount_with_cr_db_and_pending_rows(self):
        r = si.parse(BCA, default_year=2026)
        self.assertEqual([(l['line_date'], l['direction'], l['amount']) for l in r['lines']],
                         [(date(2026, 9, 3), 'in', 1_500_000), (date(2026, 9, 4), 'out', 15_000)])
        self.assertEqual(r['opening_balance'], 35_000_000)
        self.assertEqual([s['reason'] for s in r['skipped']], ['no date'])      # PEND

    def test_semicolon_and_indonesian_decimals(self):
        r = si.parse(SEMICOLON_ID)
        self.assertEqual([(l['direction'], l['amount']) for l in r['lines']], [('in', 2_500_000), ('out', 1_000_000)])
        self.assertEqual(r['opening_balance'], 10_000_000)

    def test_mapping_override_and_errors(self):
        r = si.parse(SEMICOLON_ID, mapping={'date': 0, 'description': 1, 'amount': 4})
        self.assertEqual(r['lines'][0]['amount'], 12_500_000)
        with self.assertRaises(si.ImportError_):
            si.parse('')
        with self.assertRaises(si.ImportError_):
            si.parse('a,b\n1,2\n')

    def test_parse_amount(self):
        self.assertEqual(si.parse_amount('1.500.000,50')[0], 1500000.5)
        self.assertEqual(si.parse_amount('1,500,000.50')[0], 1500000.5)
        self.assertEqual(si.parse_amount('1.500')[0], 1500)
        self.assertEqual(si.parse_amount('(2,000.00)')[2], True)
        self.assertIsNone(si.parse_amount('0.00'))


class IdrReconciliationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('rec', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.idr = BankAccount.objects.create(
            branch_id='sby', name='Mandiri IDR', currency='IDR', ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'),
            bank_name='Mandiri', account_identifier='1400012345678', opening_balance=35_000_000, opening_date=date(2026, 9, 1))
        sync_opening_balance(self.idr)
        client = Client.objects.create(name='PT Alpha')
        inv = Invoice.objects.create(invoice_number='INV-1', customer_name='x', client=client)
        p = create_payment_record(inv, client, date(2026, 9, 2), 49_000_000, currency='IDR', exchange_rate=4900,
                                  method='Transfer', bank_account=self.idr, created_by=self.user)
        confirm_payment(p, self.user)
        self.pay_tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=p.pk)
        self.client.force_login(self.user)

    def _import(self, **extra):
        return self.client.post('/finance/reconciliation/import/', {
            'account': f'bank:{self.idr.pk}', 'csv_text': MANDIRI, 'filename': 'mandiri-sep.csv', **extra,
        }, HTTP_X_INERTIA='true')

    def test_import_preview_then_save_and_reconcile_in_rupiah(self):
        preview = self._import().json()['props']
        self.assertEqual(len(preview['preview']['lines']), 2)
        self.assertEqual(preview['form']['opening_balance'], '35000000')
        self.assertEqual(preview['form']['period_start'], '2026-09-03')
        resp = self._import(step='save', mapping=preview['form']['mapping'], period_start='2026-09-01',
                            period_end='2026-09-30', opening_balance='35000000', closing_balance='83985000')
        self.assertEqual(resp.status_code, 302)
        st = BankStatement.objects.get()
        self.assertEqual((st.currency, st.source_filename), ('IDR', 'mandiri-sep.csv'))

        # The client transfer is suggested (a day apart, same rupiah amount);
        # the bank fee has no cash-book row yet.
        suggestions = rs.suggest_matches(st)
        self.assertEqual(list(suggestions.values()), [self.pay_tx])
        summary = rs.statement_summary(st)
        self.assertEqual(summary['book_balance'], 84_000_000)
        self.assertEqual(summary['difference'], -15_000)                  # the unrecorded fee
        self.assertEqual(summary['statement_gap'], 0)

        # Nothing is matched until someone clicks.
        self.assertEqual(summary['lines_matched'], 0)
        self.client.post(f'/finance/reconciliation/{st.pk}/match-suggested/')
        self.pay_tx.refresh_from_db()
        self.assertEqual(self.pay_tx.status, BankTransaction.STATUS_RECONCILED)
        self.assertEqual(rs.statement_summary(st)['lines_matched'], 1)

    def test_match_refuses_other_account_and_amount_mismatch(self):
        st = rs.create_statement(account=self.idr, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                 opening_balance=35_000_000, closing_balance=84_000_000,
                                 lines=[{'line_date': date(2026, 9, 3), 'direction': 'in', 'amount': 48_999_000}])
        line = st.lines.get()
        with self.assertRaises(rs.MatchMismatchError):
            rs.match_line(line, self.pay_tx)
        other = BankAccount.objects.create(branch_id='sby', name='BCA', currency='IDR', bank_name='BCA', account_identifier='9',
                                           ledger_account=self.idr.ledger_account)
        other_tx = BankTransaction.objects.create(bank_account=other, direction='in', amount=48_999_000, amount_sar=1,
                                                  currency='IDR', transaction_date=date(2026, 9, 3), source_type='X', source_id=1)
        with self.assertRaises(FinanceError):
            rs.match_line(line, other_tx, force=True)
        self.assertEqual(rs.suggest_matches(st), {})

    def test_line_outside_period_rejected(self):
        with self.assertRaises(FinanceError):
            rs.create_statement(account=self.idr, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                opening_balance=0, closing_balance=0,
                                lines=[{'line_date': date(2026, 10, 1), 'direction': 'in', 'amount': 5}])

    def test_detail_props(self):
        st = rs.create_statement(account=self.idr, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                 opening_balance=35_000_000, closing_balance=84_000_000,
                                 lines=[{'line_date': date(2026, 9, 3), 'direction': 'in', 'amount': 49_000_000}])
        props = self.client.get(f'/finance/reconciliation/{st.pk}/', HTTP_X_INERTIA='true').json()['props']['statement']
        self.assertEqual(props['currency'], 'IDR')
        self.assertEqual(props['suggested_count'], 1)
        self.assertEqual(props['lines'][0]['suggested']['id'], self.pay_tx.pk)
        self.assertEqual(props['difference'], 0)


class ImportJsonPostTest(IdrReconciliationTest):
    def test_preview_via_json(self):
        import json
        props = self.client.post('/finance/reconciliation/import/', json.dumps({
            'account': f'bank:{self.idr.pk}', 'csv_text': MANDIRI, 'filename': 'm.csv', 'step': 'preview',
        }), content_type='application/json', HTTP_X_INERTIA='true').json()['props']
        self.assertIsNone(props['error'])
        self.assertEqual(len(props['preview']['lines']), 2)
