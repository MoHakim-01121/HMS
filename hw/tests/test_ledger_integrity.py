"""Regression tests for the ledger integrity fixes.

Covers the review findings that were actually implemented:
* C1: penalty dual-write (_sync_penalty_ledger) is wired into penalty_new/edit
      (it was dead code before).
* C2: editing an invoice's payment list must not delete the penalty's own
      CashMovement.
* H2/C3/H4(delete): posted financial documents (invoice, services invoice,
      remittance, penalty) cannot be silently deleted once they touch the
      ledger.
* M3: visa/service invoices compute total_sar and remaining_sar correctly.
* H4(schema): a CashMovement may label at most one of reservation /
      service_item / penalty.
"""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from hw.models import (
    Client, Invoice, Reservation, ConfirmationLetter, Room,
    CancellationPenalty, Charge, ChargeReason, Allocation, AllocationReason,
    CashMovement, CashAccount, Remittance, RemittanceLine, ServiceItem,
)
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

        self.cl_obj = Client.objects.create(company='konoz', name='Amanah')
        self.inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-PEN-1',
            customer_name='Amanah', issued_date=date(2026, 8, 1),
        )
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', client=self.cl_obj, hotel_name='Hotel A',
            guest_name='Guest A', check_in=date(2026, 8, 10),
            check_out=date(2026, 8, 12), confirmation_number='CL-PEN-1',
            invoice=self.inv,
        )

    def test_penalty_create_writes_charge_and_paid_movement(self):
        resp = self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-001', 'cancellation_date': '2026-08-05',
            'reason': 'batal', 'penalty_amount': '1000', 'penalty_currency': 'SAR',
            'exchange_rate': '1', 'is_paid': 'on', 'payment_method': 'transfer',
        })
        self.assertEqual(resp.status_code, 302)
        penalty = CancellationPenalty.objects.get(penalty_number='PNL-001')
        self.assertEqual(Charge.objects.filter(penalty=penalty).count(), 1)
        self.assertEqual(Charge.objects.get(penalty=penalty).amount_sar, 1000)
        self.assertEqual(CashMovement.objects.filter(penalty_label=penalty).count(), 1)
        self.assertEqual(Allocation.objects.filter(penalty=penalty).count(), 1)

    def test_penalty_create_unpaid_writes_charge_without_movement(self):
        resp = self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-002', 'cancellation_date': '2026-08-05',
            'penalty_amount': '500', 'penalty_currency': 'SAR', 'exchange_rate': '1',
        })
        self.assertEqual(resp.status_code, 302)
        penalty = CancellationPenalty.objects.get(penalty_number='PNL-002')
        self.assertEqual(Charge.objects.filter(penalty=penalty).count(), 1)
        self.assertEqual(CashMovement.objects.filter(penalty_label=penalty).count(), 0)

    def test_penalty_edit_resyncs_ledger(self):
        penalty = CancellationPenalty.objects.create(
            cl=self.cl, penalty_number='PNL-003', cancellation_date=date(2026, 8, 5),
            penalty_amount=1000, is_paid=True, payment_method='transfer',
        )
        resp = self.client.post(f'/penalty/{penalty.pk}/edit/', {
            'penalty_number': 'PNL-003', 'cancellation_date': '2026-08-05',
            'penalty_amount': '700', 'penalty_currency': 'SAR', 'exchange_rate': '1',
            'is_paid': 'on', 'payment_method': 'direct',
        })
        self.assertEqual(resp.status_code, 302)
        penalty.refresh_from_db()
        charge = Charge.objects.get(penalty=penalty)
        self.assertEqual(charge.amount_sar, 700)
        mov = CashMovement.objects.get(penalty_label=penalty)
        self.assertEqual(mov.to_account, CashAccount.PUSAT)


class PenaltyMovementProtectedFromPaymentResyncTest(TestCase):
    """C2 — _save_payments must not delete penalty movements."""

    def setUp(self):
        self.user = User.objects.create_user('pay_ops', password='pw12345')
        self.cl_obj = Client.objects.create(company='konoz', name='Bina')
        self.inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-PAY-1',
            customer_name='Bina', issued_date=date(2026, 8, 1),
        )
        self.res = Reservation.objects.create(
            invoice=self.inv, reservation_number='R1', hotel='H', total_sar=5000,
        )
        self.cl = ConfirmationLetter.objects.create(
            company='konoz', client=self.cl_obj, hotel_name='Hotel B',
            guest_name='Guest B', check_in=date(2026, 8, 10),
            check_out=date(2026, 8, 12), confirmation_number='CL-PAY-1',
            invoice=self.inv,
        )
        self.penalty = CancellationPenalty.objects.create(
            cl=self.cl, penalty_number='PNL-PAY', cancellation_date=date(2026, 8, 5),
            penalty_amount=1000, is_paid=True, payment_method='transfer',
        )
        from hw.views.penalty_views import _sync_penalty_ledger
        _sync_penalty_ledger(self.penalty)

    def test_payment_save_keeps_penalty_movement(self):
        self.assertEqual(CashMovement.objects.filter(penalty_label=self.penalty).count(), 1)
        req = _Request()
        req.user = self.user
        req.POST = {
            'payments': '[{"ref":"R1","date":"2026-08-02","method":"transfer",'
                        '"amount":"500","currency":"SAR","exchange":"1","note":"","proof_keep":""}]',
        }
        _save_payments(self.inv, req, 'SAR')
        self.assertEqual(
            CashMovement.objects.filter(penalty_label=self.penalty).count(), 1,
            'edit daftar payment menghapus CashMovement penalty',
        )
        self.assertEqual(CashMovement.objects.filter(reservation_label=self.res).count(), 1)


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
        self.cl_obj = Client.objects.create(company='konoz', name='Sinar')

    def _hotel_invoice_with_charge(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-DEL-1',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        res = Reservation.objects.create(
            invoice=inv, reservation_number='R1', hotel='H', total_sar=1000,
        )
        Charge.objects.create(
            company='konoz', client=self.cl_obj, invoice=inv, date=date(2026, 8, 1),
            amount_sar=1000, reservation=res, reason=ChargeReason.INITIAL,
        )
        return inv

    def test_invoice_delete_blocked_when_charges_exist(self):
        inv = self._hotel_invoice_with_charge()
        resp = self.client.post(f'/invoice/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/invoice/{inv.pk}/', resp['Location'])
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())
        self.assertEqual(Charge.objects.filter(invoice=inv).count(), 1)

    def test_invoice_delete_allowed_when_no_ledger(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-DEL-2',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        resp = self.client.post(f'/invoice/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Invoice.objects.filter(pk=inv.pk).exists())

    def test_services_delete_blocked_when_charges_exist(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='visa', invoice_number='SVC-DEL-1',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        item = ServiceItem.objects.create(invoice=inv, name='Visa', qty=1, price=300)
        Charge.objects.create(
            company='konoz', client=self.cl_obj, invoice=inv, date=date(2026, 8, 1),
            amount_sar=300, service_item=item, reason=ChargeReason.INITIAL,
        )
        resp = self.client.post(f'/services/{inv.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())

    def test_remittance_delete_blocked_when_lines_exist(self):
        rem = Remittance.objects.create(
            company='konoz', remittance_number='RMT-001', date=date(2026, 8, 1),
        )
        RemittanceLine.objects.create(remittance=rem, linked_number='R1', amount_sar=500)
        resp = self.client.post(f'/remittance/{rem.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/remittance/{rem.pk}/', resp['Location'])
        self.assertTrue(Remittance.objects.filter(pk=rem.pk).exists())

    def test_remittance_delete_allowed_when_empty(self):
        rem = Remittance.objects.create(
            company='konoz', remittance_number='RMT-002', date=date(2026, 8, 1),
        )
        resp = self.client.post(f'/remittance/{rem.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Remittance.objects.filter(pk=rem.pk).exists())

    def test_penalty_delete_blocked_when_charges_exist(self):
        cl = ConfirmationLetter.objects.create(
            company='konoz', client=self.cl_obj, hotel_name='H', guest_name='G',
            confirmation_number='CL-DEL-1',
        )
        penalty = CancellationPenalty.objects.create(
            cl=cl, penalty_number='PNL-DEL', cancellation_date=date(2026, 8, 5),
            penalty_amount=500,
        )
        Charge.objects.create(
            company='konoz', client=self.cl_obj, date=date(2026, 8, 5),
            amount_sar=500, penalty=penalty, reason=ChargeReason.CANCELLATION,
        )
        resp = self.client.post(f'/penalty/{penalty.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CancellationPenalty.objects.filter(pk=penalty.pk).exists())


class ServiceInvoiceTotalTest(TestCase):
    """M3 — visa invoices compute total/remaining correctly."""

    def test_visa_invoice_total_sar_includes_service_items(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='visa', invoice_number='SVC-TOT-1',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        ServiceItem.objects.create(invoice=inv, name='Visa', qty=2, price=150)
        ServiceItem.objects.create(invoice=inv, name='Insurance', qty=1, price=100)
        self.assertEqual(inv.total_sar, 400)
        self.assertEqual(inv.remaining_sar, 400)
        CashMovement.objects.create(
            company='konoz', invoice=inv, date=date(2026, 8, 2),
            from_account=CashAccount.CLIENT, to_account=CashAccount.SBY,
            amount=300, currency='SAR', exchange_rate=1,
        )
        self.assertEqual(inv.total_paid_sar, 300)
        self.assertEqual(inv.remaining_sar, 100)

    def test_hotel_invoice_total_unaffected(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-TOT-1',
            customer_name='Sinar', issued_date=date(2026, 8, 1),
        )
        Reservation.objects.create(invoice=inv, reservation_number='R1', total_sar=1000)
        self.assertEqual(inv.total_sar, 1000)


class CashMovementLabelConstraintTest(TestCase):
    """H4(schema) — at most one target label per movement."""

    def test_two_labels_are_rejected(self):
        inv = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-CON-1',
            customer_name='X', issued_date=date(2026, 8, 1),
        )
        res = Reservation.objects.create(invoice=inv, reservation_number='R1', total_sar=1)
        cl = ConfirmationLetter.objects.create(
            company='konoz', hotel_name='H', guest_name='G', confirmation_number='CL-CON-1',
        )
        penalty = CancellationPenalty.objects.create(
            cl=cl, penalty_number='PNL-CON', cancellation_date=date(2026, 8, 5),
        )
        with self.assertRaises(IntegrityError):
            CashMovement.objects.create(
                company='konoz', invoice=inv, date=date(2026, 8, 1),
                from_account=CashAccount.CLIENT, to_account=CashAccount.SBY,
                amount=100, currency='SAR', exchange_rate=1,
                reservation_label=res, penalty_label=penalty,
            )
