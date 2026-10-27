"""Halaman finance read-only baru: Journal, Trial Balance, Client Ledger,
Penalty list. Fokus verifikasi: scoping company, kebenaran agregat, permission."""
import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from hw.finance import accounts as coa
from hw.finance import posting
from hw.finance import queries as q
from hw.finance_helpers import create_payment_record
from hw.models import (
    CancellationPenalty,
    Client,
    FinancialPeriod,
)
from hw.models.journal import JournalEntry, JournalLine
from hw.tests.factories import make_cl, make_hotel_line, make_invoice


def _props(response):
    """Inertia menyimpan payload sebagai JSON di context key 'page'."""
    return json.loads(response.context['page'])['props']


class FinanceViewsTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        # Superuser bypass role matrix (lihat hw/permissions.py)
        self.user = User.objects.create_user('fin', password='x', is_superuser=True)
        self.client.force_login(self.user)

        self.period = FinancialPeriod.objects.create(
            name='2026-TEST', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.konoz_client = Client.objects.create(name='PT Uji')
        self.invoice = make_invoice(
            invoice_type='hotel',
            invoice_number='INV-FV-001', customer_name='PT Uji',
            client=self.konoz_client,
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number='R-FV-1', total_sar=100000,
        )

    def _je(self, n, legs=(('cash_sby', 5000), ('receivable', -5000)), ar_client=None):
        je = JournalEntry.objects.create(
            entry_number=f'JE-T{n:06d}',
            entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description=f'Test entry {n}',
            entry_date=date(2026, 3, 1),
            period=self.period,
            created_by=self.user,
        )
        for i, (account, amount) in enumerate(legs, start=1):
            JournalLine.objects.create(
                journal_entry=je, line_no=i,
                account_id=coa.resolve_account_code(account),
                debit=amount if amount > 0 else 0,
                credit=-amount if amount < 0 else 0,
                client=ar_client if account == 'receivable' else None,
            )
        return je

    # â”€â”€ Journal â”€â”€

    def test_journal_list_shows_entries(self):
        mine = self._je(1)
        r = self.client.get(reverse('journal_list'))
        self.assertEqual(r.status_code, 200)
        numbers = [e['entry_number'] for e in _props(r)['entries']]
        self.assertIn(mine.entry_number, numbers)

    def test_journal_list_filters_by_type(self):
        je = self._je(3)
        r = self.client.get(reverse('journal_list'), {'type': 'payment'})
        numbers = [e['entry_number'] for e in _props(r)['entries']]
        self.assertNotIn(je.entry_number, numbers)

    def test_journal_detail_shows_lines_and_dim(self):
        je = JournalEntry.objects.create(
            entry_number='JE-T000004',
            entry_type=JournalEntry.TYPE_CHARGE,
            description='Charge PT Uji',
            entry_date=date(2026, 3, 2),
            period=self.period,
            created_by=self.user,
        )
        JournalLine.objects.create(
            journal_entry=je, line_no=1, account_id=coa.AR, debit=7000, credit=0,
            client=self.konoz_client, invoice=self.invoice,
        )
        JournalLine.objects.create(
            journal_entry=je, line_no=2, account_id=coa.INC_HOTEL, debit=0, credit=7000,
            invoice=self.invoice,
        )
        r = self.client.get(reverse('journal_detail', args=[je.pk]))
        self.assertEqual(r.status_code, 200)
        props = _props(r)
        self.assertEqual(props['lines'][0]['dim'], 'PT Uji')
        self.assertEqual(len(props['lines']), 2)

    # â”€â”€ Trial Balance â”€â”€

    def test_trial_balance_totals_and_balanced_flag(self):
        self._je(5, legs=(('cash_sby', 5000), ('receivable', -5000)))
        self._je(6, legs=(('receivable', 3000), ('income_hotel', -3000)))
        r = self.client.get(reverse('trial_balance'))
        props = _props(r)
        self.assertTrue(props['balanced'])
        self.assertEqual(props['total_debit'], 8000)
        self.assertEqual(props['total_credit'], 8000)
        accounts = {g['account']: g for g in props['rows']}
        self.assertEqual(accounts[coa.CASH_SBY]['debit'], 5000)
        self.assertEqual(accounts[coa.INC_HOTEL]['credit'], 3000)

    def test_trial_balance_date_filter(self):
        self._je(8)
        r = self.client.get(reverse('trial_balance'), {
            'date_from': '2026-04-01', 'date_to': '2026-12-31',
        })
        # Cash posted in March: the April–December range opens with it and
        # shows no movement.
        cash = next(g for g in _props(r)['rows'] if g['account'] == coa.CASH_SBY)
        self.assertEqual((cash['opening'], cash['debit'], cash['credit'], cash['closing']), (5000, 0, 0, 5000))

    # â”€â”€ Client Ledger (statements) â”€â”€

    def test_statements_match_per_client_helpers(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        p = create_payment_record(
            invoice=self.invoice, client=self.konoz_client,
            payment_date=date(2026, 3, 2), amount=60000, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

        r = self.client.get(reverse('statements_list'))
        rows = _props(r)['clients']
        row = next(x for x in rows if x['client_id'] == self.konoz_client.id)
        self.assertEqual(row['tagihan'], q.client_billed_sar(self.konoz_client.id))
        self.assertEqual(row['piutang'], q.client_receivable(self.konoz_client.id))
        self.assertEqual(row['saldo_dana'], q.client_credit_balance(self.konoz_client.id))
        self.assertEqual(row['tagihan'], 100000)
        self.assertEqual(row['piutang'], 40000)
        self.assertEqual(row['saldo_dana'], 0)

    def test_statements_omit_clients_without_ledger_activity(self):
        """The list is a ledger, not a directory: a client that never appears
        in the journal must not render as an all-zero row."""
        Client.objects.create(name='PT Hening')
        r = self.client.get(reverse('statements_list'))
        rows = _props(r)['clients']
        self.assertEqual(rows, [])
        self.assertEqual(_props(r)['pagination']['count'], 0)

    def test_statements_outstanding_filter_and_totals(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        paid = create_payment_record(
            invoice=self.invoice, client=self.konoz_client,
            payment_date=date(2026, 3, 2), amount=100000, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(paid, created_by=self.user)

        # Fully settled → filtered out of the outstanding-only view, but the
        # footer totals still cover the unfiltered set.
        r = self.client.get(reverse('statements_list'), {'show': 'owe'})
        self.assertEqual(_props(r)['clients'], [])

        r = self.client.get(reverse('statements_list'))
        props = _props(r)
        self.assertEqual(props['totals']['ar_debit'], 100000)
        self.assertEqual(props['totals']['ar_credit'], 100000)
        self.assertEqual(props['totals']['piutang'], 0)

    def test_statements_search_narrows_by_name(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        Client.objects.create(name='PT Alfa')

        self.assertEqual(_props(self.client.get(reverse('statements_list'), {'q': 'Alfa'}))['clients'], [])

        rows = _props(self.client.get(reverse('statements_list'), {'q': 'Uji'}))['clients']
        self.assertEqual([x['name'] for x in rows], ['PT Uji'])

    def test_statements_sort_key_is_validated(self):
        r = self.client.get(reverse('statements_list'), {'sort': 'piutang; drop table'})
        self.assertEqual(r.status_code, 200)

    # â”€â”€ Client statement detail â”€â”€

    def _statement(self, params=None):
        return _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]), {'from': '', **(params or {})},
        ))['statement']

    def test_client_statement_pagination_keeps_running_balance(self):
        """A page slice must not restart the balance at zero — each row's
        balance still walks the whole period, and the totals cover it too.

        Asserted on the query function directly: the view's page size is 50,
        far above this fixture's row count, so there is no page 2 to fetch."""
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        p = create_payment_record(
            invoice=self.invoice, client=self.konoz_client,
            payment_date=date(2026, 3, 2), amount=40000, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

        full = q.client_statement_with_opening(self.konoz_client.pk)
        self.assertGreater(full['count'], 1)

        tail = q.client_statement_with_opening(
            self.konoz_client.pk, offset=1, limit=1,
        )
        self.assertEqual(len(tail['rows']), 1)
        # Period-wide totals and closing balance are unaffected by the slice.
        self.assertEqual(tail['count'], full['count'])
        self.assertEqual(tail['closing_balance'], full['closing_balance'])
        self.assertEqual(tail['total_debit'], full['total_debit'])
        # And the sliced row keeps the balance it had in the full walk.
        self.assertEqual(tail['rows'][0]['balance'], full['rows'][1]['balance'])
        self.assertEqual(tail['closing_balance'], 60000)

    def _void_pair(self):
        """A charge that was reversed: both legs land on the ledger."""
        entry = posting.post_invoice_charge(self.invoice, created_by=self.user)
        posting.reverse_entry(entry, reversal_date=entry.entry_date, created_by=self.user)
        return entry

    def test_client_ledger_hides_reversed_pairs_with_a_true_running_balance(self):
        """Hidden reversed pairs leave no trace in the visible balances: each
        shown row's balance follows from the shown row above it, and the
        closing balance equals the full ledger's."""
        self._void_pair()
        posting.post_invoice_charge(self.invoice, created_by=self.user)

        full = q.client_ledger(self.konoz_client.pk, hide_voided=False)
        lean = q.client_ledger(self.konoz_client.pk)
        self.assertEqual(lean['hidden_voided'], 2)
        self.assertEqual(len(lean['rows']), len(full['rows']) - 2)
        self.assertEqual(lean['closing_balance'], full['closing_balance'])
        running = lean['opening_balance']
        for r in lean['rows']:
            running += r['debit'] - r['credit']
            self.assertEqual(r['balance'], running)
        self.assertEqual(
            sum(m['debit'] for m in lean['months'].values()), lean['total_debit'],
        )

    def test_client_ledger_search_narrows_rows_not_totals(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        p = create_payment_record(
            invoice=self.invoice, client=self.konoz_client,
            payment_date=date(2026, 3, 2), amount=40000, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

        every = q.client_ledger(self.konoz_client.pk)
        hit = q.client_ledger(self.konoz_client.pk, q=every['rows'][-1]['entry_number'].lower())
        self.assertEqual(len(hit['rows']), 1)
        self.assertEqual(hit['rows'][0]['balance'], every['rows'][-1]['balance'])
        self.assertEqual(hit['total_debit'], every['total_debit'])
        self.assertEqual(hit['period_count'], every['period_count'])

    def test_client_statement_defaults_to_the_last_three_months(self):
        """A bare URL opens on three calendar months; an explicit empty `from`
        is the "All time" choice and is honoured."""
        from unittest import mock
        posting.post_invoice_charge(self.invoice, created_by=self.user, entry_date=date(2026, 3, 1))
        with mock.patch('django.utils.timezone.localdate', return_value=date(2026, 12, 15)):
            bare = _props(self.client.get(
                reverse('client_finance_statement', args=[self.konoz_client.pk]),
            ))
        self.assertEqual(bare['date_from'], '2026-10-01')
        self.assertEqual(bare['statement']['count'], 0)  # March is outside it
        self.assertEqual(self._statement()['count'], 1)

    def test_client_statement_aging_uses_ar_aging_buckets(self):
        """One aging implementation for both pages: the detail's buckets are
        the AGING_BUCKETS keys, so a client's aging adds up to the AR Aging row."""
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        props = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]),
        ))
        self.assertEqual(
            set(props['aging']['buckets']), set(q.AGING_BUCKETS),
        )
        self.assertEqual(
            sum(props['aging']['buckets'].values()), props['aging']['total'],
        )

    def test_client_statement_aging_honours_period_filter(self):
        """A filtered statement must not show aging for invoices outside it."""
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.invoice.due_date = date(2026, 6, 1)
        self.invoice.save()

        unfiltered = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]),
        ))['aging']['total']
        self.assertEqual(unfiltered, 100000)

        # A period that ends before the invoice was ever billed owes nothing.
        filtered = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]),
            {'to': '2026-01-31'},
        ))['aging']
        self.assertEqual(filtered['total'], 0)

    def test_client_statement_aging_ages_as_of_period_end(self):
        """"Overdue" must be measured from the period the statement is showing.
        Unfiltered, this invoice has been late for months; locked to a period
        that ended before its due date it is simply not due yet."""
        posting.post_invoice_charge(self.invoice, created_by=self.user, entry_date=date(2026, 3, 1))
        self.invoice.due_date = date(2026, 3, 10)
        self.invoice.save()

        def aging(params):
            return _props(self.client.get(
                reverse('client_finance_statement', args=[self.konoz_client.pk]), params,
            ))['aging']

        before = aging({'to': '2026-03-05'})
        self.assertEqual(before['buckets']['current'], 100000)
        self.assertEqual(before['buckets']['1_30'], 0)

        after = aging({'to': '2026-03-20'})
        self.assertEqual(after['buckets']['current'], 0)
        self.assertEqual(after['buckets']['1_30'], 100000)
        self.assertEqual(after['invoices'][0]['days_overdue'], 10)

        # And the page says which day it judged, instead of implying today.
        props = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]), {'to': '2026-03-20'},
        ))
        self.assertEqual(props['aging_as_of'], '2026-03-20')

    def test_client_statement_aging_counts_unlinked_receivable_as_current(self):
        """A receivable with no invoice has no due date, so it cannot be aged.
        ar_aging() parks it in 'current'; the detail must agree or the two
        pages report different outstanding totals for the same client."""
        # The ledger is append-only: the client goes on the line when it is written.
        self._je(9, legs=(('receivable', 12345), ('income_hotel', -12345)), ar_client=self.konoz_client)
        aging = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]),
        ))['aging']
        self.assertEqual(aging['buckets']['current'], 12345)
        self.assertEqual(aging['total'], 12345)

    def test_client_statement_view_exposes_pagination(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        props = _props(self.client.get(
            reverse('client_finance_statement', args=[self.konoz_client.pk]),
        ))
        pag = props['pagination']
        self.assertEqual(pag['number'], 1)
        self.assertEqual(pag['count'], props['statement']['count'])
        self.assertEqual(len(props['statement']['transactions']), props['statement']['count'])
        # One page of 50 is not enough for this fixture, so no nav is offered.
        self.assertFalse(pag['has_other_pages'])

    def test_statement_rows_carry_what_the_page_renders(self):
        """The statement page reads these keys directly; a rename here would
        silently blank a column rather than fail loudly."""
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        self.invoice.due_date = date(2026, 3, 10)
        self.invoice.save()

        balance = self._statement()
        self.assertEqual(
            set(balance['transactions'][0]),
            {'date', 'entry_number', 'entry_type', 'entry_type_display',
             'description', 'account', 'account_display', 'invoice_number',
             'amount_sar', 'balance', 'is_voided'},
        )
        self.assertFalse(balance['transactions'][0]['is_voided'])

        open_mode = self._statement({'mode': 'open'})
        self.assertEqual(
            set(open_mode['open_items'][0]),
            {'id', 'invoice_number', 'invoice_type', 'issued_date', 'due_date',
             'billed', 'paid', 'remaining', 'overdue', 'days_overdue', 'bucket'},
        )
        # Open items sort worst-first, and each line says how late it is.
        self.assertGreaterEqual(
            open_mode['open_items'][0]['days_overdue'],
            open_mode['open_items'][-1]['days_overdue'],
        )

    def test_statement_pdf_by_reservation_mode(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        p = create_payment_record(
            invoice=self.invoice, client=self.konoz_client,
            payment_date=date(2026, 3, 2), amount=40000, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

        r = self.client.get(
            reverse('client_statement_pdf', args=[self.konoz_client.id]),
            {'mode': 'byres'},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')

    # â”€â”€ Penalty list â”€â”€

    def test_penalty_list_render_and_status_filter(self):
        from hw.finance.penalty_billing import bill_penalty
        from hw.models import Reservation
        cl_paid = make_cl(
            hotel_name='Hotel Uji', client=self.konoz_client,
            confirmation_number='CL-FV-001', reservation_status='CANCELLED',
        )
        cl_open = make_cl(
            hotel_name='Hotel Dua', client=self.konoz_client,
            confirmation_number='CL-FV-002', reservation_status='CANCELLED',
        )
        pen_paid = CancellationPenalty.objects.create(
            cl=cl_paid, penalty_number='PNL-901',
            cancellation_date=date(2026, 3, 1), penalty_amount=1000,
        )
        invoice, _created = bill_penalty(pen_paid, user=self.user)
        # Paid or not is derived: money received for the reservation covers its penalty.
        payment = create_payment_record(
            invoice=invoice, client=self.konoz_client, payment_date=date(2026, 3, 2),
            amount=1000, method='transfer', created_by=self.user,
            reservation=Reservation.objects.get(confirmation_letter=cl_paid),
        )
        posting.post_payment(payment, created_by=self.user)
        pen_open = CancellationPenalty.objects.create(
            cl=cl_open, penalty_number='PNL-902',
            cancellation_date=date(2026, 3, 2), penalty_amount=2000,
        )
        bill_penalty(pen_open, user=self.user)
        r = self.client.get(reverse('penalty_list'), {'status': 'paid'})
        props = _props(r)
        ids = [p['id'] for p in props['penalties']]
        self.assertEqual(ids, [pen_paid.id])

    # â”€â”€ Permission â”€â”€

    def test_finance_pages_denied_without_perm(self):
        from django.contrib.auth.models import User

        plain = User.objects.create_user('plain', password='x')
        # Role STAFF default punya akses luas; pakai role tanpa izin apa pun
        # agar can() False (lihat hw/permissions.py).
        from hw.models import RoleDefinition
        RoleDefinition.objects.create(slug='no_access', label='No access', permissions={})
        plain.profile.role = 'no_access'
        plain.profile.save()
        self.client.force_login(plain)
        for url in (
            reverse('journal_list'), reverse('trial_balance'),
            reverse('statements_list'), reverse('penalty_list'),
        ):
            r = self.client.get(url)
            self.assertIn(r.status_code, (302, 403), url)
