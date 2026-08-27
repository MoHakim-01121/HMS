from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, ServiceItem, CashMovement, Allocation
from hw.models.period import FinancialPeriod
from hw.finance_helpers import create_payment_record, confirm_payment, allocate_payment
from hw.views.context import _build_reservation_context


class AllocatePaymentDualWriteTest(TestCase):
    """allocate_payment() must mirror into CashMovement/Allocation -- same
    bridge invoice_billing.py/penalty_views.py use -- so a payment made
    through the Finance page is visible everywhere the old ledger is read
    (Invoice.total_paid_sar, per-reservation breakdown, client stats)."""

    def setUp(self):
        self.user = User.objects.create_user('ledger_sync', password='pw12345')
        self.client_obj = Client.objects.create(company='konoz', name='PT Ledger Sync')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-LS-001', customer_name='PT Ledger Sync',
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        FinancialPeriod.objects.create(
            name='2026-01', date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
        )

    def _allocate(self, amount=400, method='transfer', reservation=None, service_item=None):
        payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=amount, method=method, created_by=self.user,
            reservation=reservation, service_item=service_item,
        )
        confirm_payment(payment, confirmed_by=self.user)
        allocate_payment(payment, allocation_date=payment.payment_date, created_by=self.user)
        return payment

    def test_allocation_writes_cash_movement_and_updates_invoice_totals(self):
        self._allocate(amount=400)

        self.assertEqual(self.invoice.total_paid_sar, 400)
        self.assertEqual(self.invoice.remaining_sar, 600)
        movement = CashMovement.objects.get(invoice=self.invoice)
        self.assertEqual(movement.from_account, 'client')
        self.assertEqual(movement.to_account, 'sby')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_PARTIAL)

    def test_direct_method_routes_to_pusat(self):
        self._allocate(amount=1000, method='direct')
        movement = CashMovement.objects.get(invoice=self.invoice)
        self.assertEqual(movement.to_account, 'pusat')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_PAID)

    def test_allocation_tied_to_reservation_writes_allocation_row(self):
        self._allocate(amount=400, reservation=self.res)
        alloc = Allocation.objects.get(invoice=self.invoice)
        self.assertEqual(alloc.reservation_id, self.res.id)
        self.assertEqual(alloc.amount_sar, 400)

    def test_allocation_tied_to_reservation_appears_in_reservation_breakdown(self):
        # This is the gap invoice detail's per-reservation table had: it
        # read only the legacy Payment model, never CashMovement, so a
        # Finance-page payment allocated to a specific reservation was
        # invisible there even after total_paid_sar was fixed.
        self._allocate(amount=400, reservation=self.res)
        ctx = _build_reservation_context(self.invoice)
        row = next(r for r in ctx if r['id'] == self.res.id)
        self.assertEqual(row['paid_int'], 400)
        self.assertEqual(row['remaining_int'], 600)

    def test_allocation_without_reservation_or_service_item_writes_no_allocation_row(self):
        self._allocate(amount=400)
        self.assertEqual(Allocation.objects.filter(invoice=self.invoice).count(), 0)

    def test_two_allocations_accumulate_to_paid_status(self):
        self._allocate(amount=400)
        self._allocate(amount=600)
        self.assertEqual(self.invoice.total_paid_sar, 1000)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.STATUS_PAID)


class PaymentReverseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ledger_reverse', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        self.client_obj = Client.objects.create(company='konoz', name='PT Reverse')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-REV-001', customer_name='PT Reverse',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        # Wide enough to also cover reverse_journal_entry's entry_date, which
        # is always today's real date (timezone.now()), not the payment's own
        # payment_date -- a Jan-2026-only period would 404 the reversal via
        # PeriodLockedError, silently swallowed by the view's redirect.
        FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=400, method='transfer', created_by=self.user,
        )
        confirm_payment(self.payment, confirmed_by=self.user)
        allocate_payment(self.payment, allocation_date=self.payment.payment_date, created_by=self.user)

    def test_reverse_undoes_cash_movement_and_invoice_status(self):
        self.assertEqual(self.invoice.total_paid_sar, 400)

        resp = self.client.post(f'/finance/payments/{self.payment.pk}/reverse/')
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(CashMovement.objects.filter(invoice=self.invoice).count(), 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_paid_sar, 0)
        self.assertEqual(self.invoice.status, Invoice.STATUS_DRAFT)
        from hw.models.payment import PaymentRecord
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentRecord.STATUS_REVERSED)

    def test_reverse_does_not_touch_other_payments_cash_movement(self):
        # A second, unrelated payment on the same invoice must survive
        # reversing the first -- the note__contains(payment_number) scoping
        # must not accidentally match across payments.
        other = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 2),
            amount=300, method='transfer', created_by=self.user,
        )
        confirm_payment(other, confirmed_by=self.user)
        allocate_payment(other, allocation_date=other.payment_date, created_by=self.user)
        self.assertEqual(self.invoice.total_paid_sar, 700)

        self.client.post(f'/finance/payments/{self.payment.pk}/reverse/')

        self.assertEqual(self.invoice.total_paid_sar, 300)
        self.assertEqual(CashMovement.objects.filter(invoice=self.invoice).count(), 1)


class ServiceItemAllocationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ledger_svc', password='pw12345')
        self.client_obj = Client.objects.create(company='konoz', name='PT Services')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='services', invoice_number='SVC-LS-001',
            customer_name='PT Services', currency='SAR',
        )
        self.item = ServiceItem.objects.create(invoice=self.invoice, service_number=1, name='Visa', qty=1, price=500)
        FinancialPeriod.objects.create(
            name='2026-01', date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
        )

    def test_allocation_tied_to_service_item_writes_allocation_row(self):
        payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=500, method='transfer', created_by=self.user, service_item=self.item,
        )
        confirm_payment(payment, confirmed_by=self.user)
        allocate_payment(payment, allocation_date=payment.payment_date, created_by=self.user)

        alloc = Allocation.objects.get(invoice=self.invoice)
        self.assertEqual(alloc.service_item_id, self.item.id)
        movement = CashMovement.objects.get(invoice=self.invoice)
        self.assertEqual(movement.service_item_label_id, self.item.id)
