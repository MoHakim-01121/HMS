"""Regression tests for the ledger integrity fixes.

Covers the review findings that were actually implemented:
* C1: penalty dual-write (_sync_penalty_ledger) is wired into penalty_new/edit
      (it was dead code before).
* C2: editing an invoice's payment list must not touch the penalty's own
      journal income.
* H2/C3/H4(delete): posted financial documents (invoice, services invoice,
      remittance, penalty) cannot be silently deleted once they touch the
      ledger.
* M3: visa/service invoices compute total_sar and remaining_sar correctly.
"""
from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_remittance, make_remittance_line, make_service_line
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import (
    Client, Invoice, CancellationPenalty, Remittance,
)
from hw.models.journal import JournalLine
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance.penalty_billing import bill_penalty
from hw.finance import queries as fq
from hw.finance_helpers import create_payment_record, confirm_payment
from hw.views.invoice_billing import _save_payments


class _Request:
    user = None
    POST = {}
    FILES = {}


class PenaltyLedgerSyncTest(TestCase):
    """C1 — penalty create/edit now actually writes to the ledger."""

    def setUp(self):
        self.user = User.objects.create_user('pen_ops', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        FinancialPeriod.objects.create(
            name='2026',            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.cl_obj = Client.objects.create( name='Amanah')
        self.inv = make_invoice(
 invoice_type='hotel', invoice_number='INV-PEN-1',
            customer_name='Amanah', client=self.cl_obj, issued_date=date(2026, 8, 1),
        )
        self.cl = make_cl(
 client=self.cl_obj, hotel_name='Hotel A',
            guest_name='Guest A', check_in=date(2026, 8, 10),
            check_out=date(2026, 8, 12), confirmation_number='CL-PEN-1',
            invoice=self.inv, reservation_status='CANCELLED',
        )

    def test_penalty_create_bills_it_on_the_reservation_invoice(self):
        resp = self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-001', 'cancellation_date': '2026-08-05',
            'reason': 'batal', 'penalty_amount': '1000',
        })
        self.assertEqual(resp.status_code, 302)
        penalty = CancellationPenalty.objects.get(penalty_number='PNL-001')
        self.assertEqual(penalty.invoice, self.inv)
        self.assertEqual(fq.account_balance(fq.coa.INC_PENALTY), -1000)
        self.assertEqual(fq.client_receivable(self.cl_obj.id), 1000)
        self.assertEqual(fq.kas_surabaya(), 0)   # a penalty is paid through Payments, not this form
        self.assertFalse(penalty.is_paid)

    def test_penalty_edit_resyncs_journal_to_new_amount(self):
        self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-003', 'cancellation_date': '2026-08-05', 'penalty_amount': '1000',
        })
        penalty = CancellationPenalty.objects.get(penalty_number='PNL-003')
        resp = self.client.post(f'/penalty/{penalty.pk}/edit/', {
            'penalty_number': 'PNL-003', 'cancellation_date': '2026-08-05', 'penalty_amount': '700',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fq.account_balance(fq.coa.INC_PENALTY), -700)
        self.assertEqual(fq.client_receivable(self.cl_obj.id), 700)


class PenaltyIndependentFromInvoicePaymentTest(TestCase):
    """Edit daftar payment invoice tidak menyentuh jurnal penalty."""

    def setUp(self):
        self.user = User.objects.create_user('pay_ops', password='pw12345')
        FinancialPeriod.objects.create(
            name='2026',            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.cl_obj = Client.objects.create( name='Bina')
        self.inv = make_invoice(
 invoice_type='hotel', invoice_number='INV-PAY-1',
            customer_name='Bina', client=self.cl_obj, issued_date=date(2026, 8, 1),
        )
        self.res = make_hotel_line(
            invoice=self.inv, reservation_number='R1', hotel='H', total_sar=5000,
        )
        self.cl = make_cl(
 client=self.cl_obj, hotel_name='Hotel B',
            guest_name='Guest B', check_in=date(2026, 8, 10),
            check_out=date(2026, 8, 12), confirmation_number='CL-PAY-1',
            invoice=self.inv, reservation_status='CANCELLED',
        )
        self.penalty = CancellationPenalty.objects.create(
            cl=self.cl, penalty_number='PNL-PAY', cancellation_date=date(2026, 8, 5),
            penalty_amount=1000,
        )
        posting.post_invoice_charge(self.inv, created_by=self.user)
        bill_penalty(self.penalty, user=self.user)

    def test_payment_save_keeps_penalty_income(self):
        before = fq.account_balance(fq.coa.INC_PENALTY)
        req = _Request()
        req.user = self.user
        req.POST = {
            'payments': '[{"ref":"R1","date":"2026-08-02","method":"transfer",'
                        '"amount":"500","currency":"SAR","exchange":"1","note":"","proof_keep":""}]',
        }
        _save_payments(self.inv, req, 'SAR')
        self.assertEqual(fq.invoice_paid_sar(self.inv.id), 500)
        self.assertEqual(fq.account_balance(fq.coa.INC_PENALTY), before)  # -1000


class DeleteGuardTest(TestCase):
    """H2/C3/H4(delete) — posted documents cannot be deleted."""

    def setUp(self):
        self.user = User.objects.create_user('del_ops', password='pw12345')
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        self.cl_obj = Client.objects.create( name='Sinar')
        FinancialPeriod.objects.create(
            name='2026',            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )

    def _hotel_invoice_with_charge(self):
        inv = make_invoice(
 invoice_type='hotel', invoice_number='INV-DEL-1',
            customer_name='Sinar', client=self.cl_obj, issued_date=date(2026, 8, 1),
        )
        make_hotel_line(
            invoice=inv, reservation_number='R1', hotel='H', total_sar=1000,
        )
        posting.post_invoice_charge(inv, created_by=self.user)
        return inv

    def test_invoice_delete_blocked_when_charges_exist(self):
        inv = self._hotel_invoice_with_charge()
        resp = self.client.post(f'/invoice/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/invoice/{inv.pk}/', resp['Location'])
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())

    def test_invoice_delete_allowed_when_no_ledger(self):
        inv = make_invoice(
 invoice_type='hotel', invoice_number='INV-DEL-2',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        resp = self.client.post(f'/invoice/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Invoice.objects.filter(pk=inv.pk).exists())

    def test_services_delete_blocked_when_charges_exist(self):
        inv = make_invoice(
 invoice_type='visa', invoice_number='SVC-DEL-1',
            customer_name='Sinar', client=self.cl_obj, issued_date=date(2026, 8, 1),
        )
        make_service_line(invoice=inv, name='Visa', qty=1, price=300)
        posting.post_invoice_charge(inv, created_by=self.user)
        resp = self.client.post(f'/services/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())

    def test_remittance_delete_blocked_when_lines_exist(self):
        rem = make_remittance(
 remittance_number='RMT-001', date=date(2026, 8, 1),
        )
        inv = make_invoice(client=self.cl_obj, invoice_number='INV-RMT-DEL')
        make_hotel_line(invoice=inv, reservation_number='R1', total_sar=500)
        make_remittance_line(remittance=rem, invoice=inv, linked_number='R1', amount_sar=500)
        resp = self.client.post(f'/remittance/{rem.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/remittance/{rem.pk}/', resp['Location'])
        self.assertTrue(Remittance.objects.filter(pk=rem.pk).exists())

    def test_remittance_delete_allowed_when_empty(self):
        rem = make_remittance(
 remittance_number='RMT-002', date=date(2026, 8, 1),
        )
        resp = self.client.post(f'/remittance/{rem.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Remittance.objects.filter(pk=rem.pk).exists())

    def test_penalty_delete_blocked_when_journaled(self):
        cl = make_cl(
 client=self.cl_obj, hotel_name='H', guest_name='G',
            confirmation_number='CL-DEL-1',
        )
        penalty = CancellationPenalty.objects.create(
            cl=cl, penalty_number='PNL-DEL', cancellation_date=date(2026, 8, 5),
            penalty_amount=500,
        )
        bill_penalty(penalty, user=self.user)
        self.assertTrue(JournalLine.objects.filter(penalty=penalty).exists())
        resp = self.client.post(f'/penalty/{penalty.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CancellationPenalty.objects.filter(pk=penalty.pk).exists())


class ServiceInvoiceTotalTest(TestCase):
    """M3 — visa invoices compute total/remaining correctly."""

    def test_visa_invoice_total_sar_includes_service_items(self):
        FinancialPeriod.objects.create(
            name='2026',            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        cl = Client.objects.create( name='Sinar')
        user = User.objects.create_user('svc_tot', password='x')
        inv = make_invoice(
 invoice_type='visa', invoice_number='SVC-TOT-1',
            customer_name='Sinar', client=cl, issued_date=date(2026, 8, 1),
        )
        make_service_line(invoice=inv, name='Visa', qty=2, price=150)
        make_service_line(invoice=inv, name='Insurance', qty=1, price=100)
        self.assertEqual(inv.total_sar, 400)
        self.assertEqual(inv.remaining_sar, 400)

        posting.post_invoice_charge(inv, created_by=user)
        p = create_payment_record(
            invoice=inv, client=cl, payment_date=date(2026, 8, 2),
            amount=300, method='transfer', created_by=user,
        )
        confirm_payment(p, confirmed_by=user)
        self.assertEqual(inv.total_paid_sar, 300)
        self.assertEqual(inv.remaining_sar, 100)

    def test_hotel_invoice_total_unaffected(self):
        inv = make_invoice(
 invoice_type='hotel', invoice_number='INV-TOT-1',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        make_hotel_line(invoice=inv, reservation_number='R1', total_sar=1000)
        self.assertEqual(inv.total_sar, 1000)
