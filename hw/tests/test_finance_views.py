"""Halaman finance read-only baru: Journal, Trial Balance, Client Ledger,
Penalty list. Fokus verifikasi: scoping company, kebenaran agregat, permission."""
from hw.tests.factories import make_cl, make_hotel_line, make_invoice
import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from hw.finance import posting
from hw.finance import queries as q
from hw.finance_helpers import create_payment_record
from hw.models import (
    CancellationPenalty, Client, FinancialPeriod,
)
from hw.models.journal import JournalEntry, JournalLine
from hw.finance import accounts as coa


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

    def _je(self, n, legs=(('cash_sby', 5000), ('receivable', -5000))):
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
        accounts = {g['account']: g for g in props['groups']}
        self.assertEqual(accounts[coa.CASH_SBY]['debit'], 5000)
        self.assertEqual(accounts[coa.INC_HOTEL]['credit'], 3000)

    def test_trial_balance_date_filter(self):
        self._je(8)
        r = self.client.get(reverse('trial_balance'), {
            'date_from': '2026-04-01', 'date_to': '2026-12-31',
        })
        accounts = {g['account'] for g in _props(r)['groups']}
        self.assertNotIn(coa.CASH_SBY, accounts)

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
