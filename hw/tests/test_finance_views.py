"""Halaman finance read-only baru: Journal, Trial Balance, Client Ledger,
Penalty list. Fokus verifikasi: scoping company, kebenaran agregat, permission."""
import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from hw import ledger
from hw.models import (
    CashAccount, Allocation, AllocationReason, CashMovement, Charge, ChargeReason,
    CancellationPenalty, Client, ConfirmationLetter, FinancialPeriod, Invoice,
    Reservation,
)
from hw.models.journal import JournalEntry, JournalLine


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
        self.konoz_client = Client.objects.create(name='PT Uji', company='konoz')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-FV-001', customer_name='PT Uji',
            client=self.konoz_client,
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R-FV-1', total_sar=100000,
        )

    def _je(self, n, company='konoz', legs=(('cash_sby', 5000), ('receivable', -5000))):
        je = JournalEntry.objects.create(
            entry_number=f'JE-T{n:06d}',
            entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description=f'Test entry {n}',
            entry_date=date(2026, 3, 1),
            period=self.period,
            company=company,
            created_by=self.user,
        )
        for account, amount in legs:
            JournalLine.objects.create(journal_entry=je, account=account, amount_sar=amount)
        return je

    # â”€â”€ Journal â”€â”€

    def test_journal_list_scopes_by_company(self):
        mine = self._je(1)
        other = self._je(2, company='ijabah')
        r = self.client.get(reverse('journal_list'))
        self.assertEqual(r.status_code, 200)
        numbers = [e['entry_number'] for e in _props(r)['entries']]
        self.assertIn(mine.entry_number, numbers)
        self.assertNotIn(other.entry_number, numbers)

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
            journal_entry=je, account='receivable', amount_sar=7000,
            client=self.konoz_client, invoice=self.invoice,
        )
        JournalLine.objects.create(
            journal_entry=je, account='income_hotel', amount_sar=-7000,
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
        self.assertEqual(accounts['cash_sby']['debit'], 5000)
        self.assertEqual(accounts['income_hotel']['credit'], 3000)

    def test_trial_balance_excludes_other_company(self):
        self._je(7, company='ijabah', legs=(('cash_sby', 99000), ('receivable', -99000)))
        r = self.client.get(reverse('trial_balance'))
        props = _props(r)
        self.assertFalse(props['groups'])
        self.assertEqual(props['total_debit'], 0)

    def test_trial_balance_date_filter(self):
        je = self._je(8)
        r = self.client.get(reverse('trial_balance'), {
            'date_from': '2026-04-01', 'date_to': '2026-12-31',
        })
        accounts = {g['account'] for g in _props(r)['groups']}
        self.assertNotIn('cash_sby', accounts)

    # â”€â”€ Client Ledger (statements) â”€â”€

    def test_statements_match_per_client_helpers(self):
        Charge.objects.create(
            company='konoz', client=self.konoz_client, date=date(2026, 3, 1),
            amount_sar=100000, reason=ChargeReason.choices[0][0],
            reservation=self.res,
        )
        CashMovement.objects.create(
            company='konoz', client=self.konoz_client, date=date(2026, 3, 2),
            from_account=CashAccount.CLIENT, to_account=CashAccount.SBY,
            amount=60000,
        )
        Allocation.objects.create(
            company='konoz', client=self.konoz_client, date=date(2026, 3, 3),
            amount_sar=40000, reason=AllocationReason.choices[0][0],
            reservation=self.res,
        )
        r = self.client.get(reverse('statements_list'))
        rows = _props(r)['clients']
        row = next(x for x in rows if x['client_id'] == self.konoz_client.id)
        self.assertEqual(row['tagihan'], ledger.total_charged_by_client(self.konoz_client))
        self.assertEqual(row['piutang'], ledger.piutang_klien(self.konoz_client))
        self.assertEqual(row['saldo_dana'], ledger.saldo_dana(self.konoz_client))
        self.assertEqual(row['piutang'], 60000)
        self.assertEqual(row['saldo_dana'], 20000)

    # â”€â”€ Penalty list â”€â”€

    def test_penalty_list_render_and_status_filter(self):
        cl_paid = ConfirmationLetter.objects.create(
            hotel_name='Hotel Uji', guest_name='Budi',
            confirmation_number='CL-FV-001',
        )
        cl_open = ConfirmationLetter.objects.create(
            hotel_name='Hotel Dua', guest_name='Ani',
            confirmation_number='CL-FV-002',
        )
        pen_paid = CancellationPenalty.objects.create(
            cl=cl_paid, client=self.konoz_client, penalty_number='PNL-901',
            cancellation_date=date(2026, 3, 1), penalty_amount=1000,
            amount_sar=1000, is_paid=True,
        )
        CancellationPenalty.objects.create(
            cl=cl_open, client=self.konoz_client, penalty_number='PNL-902',
            cancellation_date=date(2026, 3, 2), penalty_amount=2000,
            amount_sar=2000, is_paid=False,
        )
        r = self.client.get(reverse('penalty_list'), {'status': 'paid'})
        props = _props(r)
        ids = [p['id'] for p in props['penalties']]
        self.assertEqual(ids, [pen_paid.id])

    # â”€â”€ Permission â”€â”€

    def test_finance_pages_denied_without_perm(self):
        from django.contrib.auth.models import User

        plain = User.objects.create_user('plain', password='x')
        # Role STAFF default punya akses luas; pakai role tak dikenal agar
        # matrix lookup kosong dan can() False (lihat hw/permissions.py).
        plain.profile.role = 'no_such_role'
        plain.profile.save()
        self.client.force_login(plain)
        for url in (
            reverse('journal_list'), reverse('trial_balance'),
            reverse('statements_list'), reverse('penalty_list'),
        ):
            r = self.client.get(url)
            self.assertIn(r.status_code, (302, 403), url)
