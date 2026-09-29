"""Void invoice + credit notes (Nota Kredit)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import credit_note_service as cns
from hw.finance import posting, queries
from hw.finance.errors import FinanceError
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import (
    BankAccount, Client, ConfirmationLetter, CreditNote, Invoice, JournalLine, LedgerAccount, Reservation,
)
from hw.models.period import FinancialPeriod

DAY = date(2026, 9, 10)


class CreditNoteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('cn', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.idr = BankAccount.objects.create(
            branch_id='sby', name='IDR', currency='IDR', ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'),
            bank_name='Mandiri', account_identifier='1')
        self.client_obj = Client.objects.create(name='PT Credit')
        self.inv = Invoice.objects.create(invoice_number='INV-CN-1', customer_name='x', client=self.client_obj,
                                          issued_date=date(2026, 9, 1), due_date=date(2026, 9, 20))
        self.r1 = Reservation.objects.create(invoice=self.inv, reservation_number='7801', hotel='Hilton', total_sar=10_000)
        self.r2 = Reservation.objects.create(invoice=self.inv, reservation_number='7802', hotel='Swiss', total_sar=8_000)
        posting.post_invoice_charge(self.inv, created_by=self.user)
        self.client.force_login(self.user)

    def _pay(self, sar):
        p = create_payment_record(self.inv, self.client_obj, DAY, sar * 4900, currency='IDR', exchange_rate=4900,
                                  method='Transfer', bank_account=self.idr, created_by=self.user)
        confirm_payment(p, self.user)
        return p

    def _cn(self, amount, res=None, **kw):
        return cns.issue_credit_note(self.inv, lines=[{'kind': 'reservation', 'id': (res or self.r2).pk, 'amount_sar': amount}],
                                     reason='Booking cancelled', issued_date=DAY, created_by=self.user, **kw)

    def _refresh(self):
        self.inv = Invoice.objects.get(pk=self.inv.pk)
        return self.inv

    # ── Credit notes ───────────────────────────────────────────────

    def test_credit_note_reduces_billing_not_paid(self):
        self._pay(4_000)
        cn = self._cn(8_000)
        inv = self._refresh()
        self.assertEqual(cn.credit_note_number, 'CN-202609-001')
        self.assertEqual(cn.to_deposit_sar, 0)
        self.assertEqual(inv.credited_sar, 8_000)
        self.assertEqual(inv.total_paid_sar, 4_000)          # a credit note is not money received
        self.assertEqual(inv.remaining_sar, 6_000)
        self.assertEqual(queries.invoice_outstanding_sar(inv.pk), 6_000)
        self.assertEqual(queries.invoice_paid_map([inv.pk]), {inv.pk: 4_000})
        self.assertEqual(queries.reservation_paid_map(inv.pk).get(self.r2.pk, 0), 0)
        self.assertEqual(queries.total_charged([inv.pk]), 10_000)
        self.assertEqual(inv.status, Invoice.STATUS_PARTIAL)
        # Revenue reduced on the same branch dimension as the charge (HQ).
        dr = JournalLine.objects.get(journal_entry__reference_type='CreditNote', account_id=coa.INC_HOTEL)
        self.assertEqual((dr.debit, dr.branch_id), (8_000, coa.HQ_BRANCH))

    def test_credit_beyond_open_goes_to_client_deposit(self):
        self._pay(12_000)
        cn = self._cn(8_000)
        inv = self._refresh()
        self.assertEqual(cn.to_deposit_sar, 2_000)
        self.assertEqual(queries.invoice_outstanding_sar(inv.pk), 0)
        self.assertEqual(queries.client_credit_balance(self.client_obj.pk), 2_000)
        self.assertEqual(inv.remaining_sar, 0)
        self.assertEqual(inv.status, Invoice.STATUS_PAID)

    def test_line_cap_and_validation(self):
        self._cn(5_000)
        with self.assertRaises(FinanceError):
            self._cn(3_001)                                  # only 3,000 left on 7802
        with self.assertRaises(FinanceError):
            cns.issue_credit_note(self.inv, lines=[{'kind': 'reservation', 'id': self.r1.pk, 'amount_sar': 10}],
                                  reason='', issued_date=DAY, created_by=self.user)
        other = Invoice.objects.create(invoice_number='INV-OTHER', customer_name='x', client=self.client_obj)
        foreign = Reservation.objects.create(invoice=other, reservation_number='9', total_sar=100)
        with self.assertRaises(FinanceError):
            self._cn(50, res=foreign)

    def test_void_credit_note_restores_billing(self):
        cn = self._cn(8_000)
        cns.void_credit_note(cn, reason='Issued by mistake', created_by=self.user)
        inv = self._refresh()
        self.assertEqual(inv.credited_sar, 0)
        self.assertEqual(inv.remaining_sar, 18_000)
        self.assertEqual(queries.invoice_outstanding_sar(inv.pk), 18_000)
        with self.assertRaises(FinanceError):
            cns.void_credit_note(cn, reason='again', created_by=self.user)

    def test_void_credit_note_refused_when_deposit_spent(self):
        self._pay(12_000)
        cn = self._cn(8_000)
        posting.post_refund(self.client_obj, from_location='sby', amount_sar=1_500, created_by=self.user, entry_date=DAY)
        with self.assertRaises(FinanceError):
            cns.void_credit_note(cn, reason='x', created_by=self.user)

    def test_charge_repost_keeps_credit_and_paid_straight(self):
        """An invoice edit re-posts the charge (reverse + post). Neither the
        reversal nor the credit note may be read as a payment."""
        self._pay(4_000)
        self._cn(2_000, res=self.r1)
        self.r1.total_sar = 11_000
        self.r1.save()
        posting.post_invoice_charge(self.inv, created_by=self.user)
        inv = self._refresh()
        self.assertEqual(inv.total_paid_sar, 4_000)
        self.assertEqual(queries.reservation_paid_map(inv.pk).get(self.r1.pk, 0), 0)
        self.assertEqual(queries.invoice_outstanding_sar(inv.pk), 19_000 - 2_000 - 4_000)
        self.assertEqual(inv.remaining_sar, 13_000)

    # ── Void ───────────────────────────────────────────────────────

    def test_void_invoice_releases_cls_and_stops_billing(self):
        cl = ConfirmationLetter.objects.create(confirmation_number='7801', client=self.client_obj, invoice=self.inv)
        released = cns.void_invoice(self.inv, reason='Wrong client', created_by=self.user)
        inv = self._refresh()
        self.assertEqual(released, ['7801'])
        cl.refresh_from_db()
        self.assertIsNone(cl.invoice_id)
        self.assertEqual(inv.status, Invoice.STATUS_VOID)
        self.assertEqual(queries.invoice_outstanding_sar(inv.pk), 0)
        self.assertEqual(queries.total_charged([inv.pk]), 0)
        self.assertEqual(inv.remaining_sar, 0)
        self.assertIsNone(posting.post_invoice_charge(inv, created_by=self.user))   # no re-billing
        inv.sync_status()
        self.assertEqual(inv.status, Invoice.STATUS_VOID)
        with self.assertRaises(FinanceError):
            self._pay(100)
        self.assertEqual(queries.ar_aging()['total'], 0)          # void is dated today
        self.assertEqual(queries.ar_aging(as_of=DAY)['total'], 18_000)  # still billed back then

    def test_void_refused_with_payment_or_credit_note(self):
        self._pay(1_000)
        self.assertTrue(cns.void_blockers(self.inv))
        with self.assertRaises(FinanceError):
            cns.void_invoice(self.inv, reason='x', created_by=self.user)

    def test_void_requires_reason(self):
        with self.assertRaises(FinanceError):
            cns.void_invoice(self.inv, reason=' ', created_by=self.user)

    # ── Views ──────────────────────────────────────────────────────

    def test_views(self):
        resp = self.client.post(f'/finance/invoices/{self.inv.pk}/credit-notes/new/', {
            'issued_date': '2026-09-10', 'reason': 'Rate corrected',
            'amounts': f'{{"reservation:{self.r1.pk}": 1500}}',
        })
        self.assertEqual(resp.status_code, 302)
        cn = CreditNote.objects.get()
        props = self.client.get(f'/invoice/{self.inv.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['credited_sar'], 1_500)
        self.assertEqual(props['invoice']['remaining_sar'], 16_500)
        self.assertEqual(props['credit_notes'][0]['number'], cn.credit_note_number)
        self.assertFalse(props['can_void'])
        listed = self.client.get('/finance/credit-notes/', HTTP_X_INERTIA='true').json()['props']['credit_notes']
        self.assertEqual(listed[0]['amount_sar'], 1_500)
        pdf = self.client.get(f'/finance/credit-notes/{cn.pk}/pdf/')
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        resp = self.client.post(f'/finance/credit-notes/{cn.pk}/void/', {'reason': 'Mistake'})
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(f'/finance/invoices/{self.inv.pk}/void/', {'reason': 'Duplicate'})
        self.assertEqual(resp.status_code, 302)
        self._refresh()
        self.assertTrue(self.inv.is_void)
        rows = self.client.get('/invoice/?status=void', HTTP_X_INERTIA='true').json()['props']['invoices']
        self.assertEqual([(r['invoice_number'], r['status']) for r in rows], [('INV-CN-1', 'void')])
        # A void invoice can't be edited any more.
        self.assertEqual(self.client.get(f'/invoice/{self.inv.pk}/edit/').status_code, 302)

    def test_staff_cannot_credit(self):
        from hw.models import UserProfile
        staff = User.objects.create_user('staff', password='pw12345')
        UserProfile.objects.filter(user=staff).update(role='staff')
        self.client.force_login(staff)
        resp = self.client.post(f'/finance/invoices/{self.inv.pk}/void/', {'reason': 'x'})
        self.assertIn(resp.status_code, (302, 403))
        self._refresh()
        self.assertFalse(self.inv.is_void)


class InertiaJsonPostTest(CreditNoteTest):
    """Inertia's useForm posts JSON, not form data — the views must read it."""

    def test_credit_note_and_void_via_json(self):
        import json
        resp = self.client.post(f'/finance/invoices/{self.inv.pk}/credit-notes/new/', json.dumps({
            'issued_date': '2026-09-10', 'reason': 'Rate corrected',
            'amounts': json.dumps({f'reservation:{self.r1.pk}': 500}),
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 302)
        cn = CreditNote.objects.get()
        self.client.post(f'/finance/credit-notes/{cn.pk}/void/', json.dumps({'reason': 'Mistake'}), content_type='application/json')
        cn.refresh_from_db()
        self.assertEqual(cn.status, CreditNote.STATUS_VOIDED)
        self.client.post(f'/finance/invoices/{self.inv.pk}/void/', json.dumps({'reason': 'Duplicate'}), content_type='application/json')
        self.assertTrue(self._refresh().is_void)
