"""Kontrol realokasi: batas per reservasi, lintas invoice client yang sama,
tanggal koreksi hari ini, dan jejak sebelum/sesudah.

Kasus lapangan: reservasi 15.000 sudah dibayar penuh, lalu di-amend jadi
13.000; kelebihan 2.000 dialokasikan ke reservasi lain dari pembayaran yang
sama -- termasuk reservasi di invoice lain milik client itu.
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hw.finance import posting
from hw.finance import queries as fq
from hw.finance.errors import FinanceError
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import BankTransaction, Client
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentLog, PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import ensure_current_period, make_hotel_line, make_invoice, set_line_total


class ReallocateControlsBase(TestCase):
    def setUp(self):
        self.maker = User.objects.create_user('rc_maker', password='pw12345')
        self.checker = User.objects.create_user('rc_checker', password='pw12345')
        for u in (self.maker, self.checker):
            u.profile.role = 'manager'
            u.profile.save(update_fields=['role'])
        self.period = FinancialPeriod.objects.create(
            name='2026-08', date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        )
        ensure_current_period()
        self.client_obj = Client.objects.create(name='PT Amend')
        self.inv_a = make_invoice(
            invoice_type='hotel', client=self.client_obj, invoice_number='INV-AMEND-A',
            issued_date=date(2026, 8, 5),
        )
        self.inv_b = make_invoice(
            invoice_type='hotel', client=self.client_obj, invoice_number='INV-AMEND-B',
            issued_date=date(2026, 8, 6),
        )
        self.r1 = make_hotel_line(invoice=self.inv_a, reservation_number='AM-1', total_sar=15000)
        self.r2 = make_hotel_line(invoice=self.inv_b, reservation_number='AM-2', total_sar=5000)
        posting.post_invoice_charge(self.inv_a, created_by=self.maker)
        posting.post_invoice_charge(self.inv_b, created_by=self.maker)

    def _paid_r1(self, amount=15000):
        """PAY-1: 15.000 dialokasikan penuh ke R1 dan dikonfirmasi user lain."""
        payment = create_payment_record(
            invoice=self.inv_a, client=self.client_obj, payment_date=date(2026, 8, 10),
            amount=amount, method='Transfer', created_by=self.maker,
        )
        posting.allocate_payment(payment, [(self.r1, amount)], created_by=self.maker)
        confirm_payment(payment, confirmed_by=self.checker)
        payment.refresh_from_db()
        return payment

    def _amend_r1(self, total):
        """CL R1 di-amend; menyimpan invoice memposting ulang charge-nya."""
        self.r1 = set_line_total(self.r1, total)
        posting.post_invoice_charge(self.inv_a, created_by=self.maker)


class AllocationCapTest(ReallocateControlsBase):
    def test_amended_reservation_keeps_its_value_and_sends_the_rest_to_another_invoice(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        self.assertEqual(posting.allocation_caps(payment, [self.r1.pk])[self.r1.pk], 13000)

        posting.reallocate_payment(payment, [(self.r1, 13000), (self.r2, 2000)], created_by=self.maker)

        self.assertEqual(fq.invoice_paid_sar(self.inv_a.pk), 13000)
        self.assertEqual(fq.invoice_paid_sar(self.inv_b.pk), 2000)
        self.assertEqual(posting.allocation_caps(payment, [self.r1.pk])[self.r1.pk], 13000)
        # The payment's journal credits each line under that line's own invoice.
        live = JournalEntry.objects.for_source('PaymentRecord', payment.pk).filter(
            entry_type=JournalEntry.TYPE_PAYMENT,
        ).live().get()
        ar = {ln.invoice_line_id: ln.invoice_id for ln in live.lines.filter(credit__gt=0)}
        self.assertEqual(ar, {self.r1.pk: self.inv_a.pk, self.r2.pk: self.inv_b.pk})

    def test_keeping_more_than_the_amended_value_is_refused(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        with self.assertRaisesRegex(FinanceError, 'melebihi sisa tagihannya \\(13,000 SAR\\)'):
            posting.reallocate_payment(payment, [(self.r1, 15000)], created_by=self.maker)

    def test_allocation_cannot_manufacture_an_overpayment(self):
        payment = create_payment_record(
            invoice=self.inv_b, client=self.client_obj, payment_date=date(2026, 8, 10),
            amount=9000, method='Transfer', created_by=self.maker,
        )
        with self.assertRaises(FinanceError):
            posting.allocate_payment(payment, [(self.r2, 9000)], created_by=self.maker)

    def test_confirmation_rechecks_a_pending_allocation(self):
        payment = create_payment_record(
            invoice=self.inv_a, client=self.client_obj, payment_date=date(2026, 8, 10),
            amount=15000, method='Transfer', created_by=self.maker,
        )
        posting.allocate_payment(payment, [(self.r1, 15000)], created_by=self.maker)
        self._amend_r1(13000)  # amended while the payment waits for its checker
        with self.assertRaises(FinanceError):
            confirm_payment(payment, confirmed_by=self.checker)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)


class ReallocateCorrectionTest(ReallocateControlsBase):
    def test_correction_is_dated_today_even_when_the_payment_month_is_closed(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        self.period.close(self.checker)

        posting.reallocate_payment(payment, [(self.r1, 13000), (self.r2, 2000)], created_by=self.maker)

        today = timezone.now().date()
        reversal = JournalEntry.objects.filter(reverses__source_payment=payment).get()
        repost = JournalEntry.objects.for_source('PaymentRecord', payment.pk).filter(
            entry_type=JournalEntry.TYPE_PAYMENT,
        ).live().get()
        self.assertEqual((reversal.entry_date, repost.entry_date), (today, today))
        # Cash did not move; the bank book still has the one receipt row.
        self.assertEqual(BankTransaction.objects.filter(source_type='PaymentRecord', source_id=payment.pk).count(), 1)
        cash = JournalLine.objects.filter(
            journal_entry__in=[reversal, repost], account_id=payment.receiving_account.ledger_account_id,
        )
        self.assertEqual(sum(l.debit - l.credit for l in cash), 0)

    def test_log_keeps_the_allocation_before_and_after(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        posting.reallocate_payment(payment, [(self.r1, 13000), (self.r2, 2000)], created_by=self.maker)

        log = PaymentLog.objects.filter(payment=payment, action=PaymentLog.ACTION_ALLOCATED).latest('pk')
        before = [(a['invoice'], a['amount_sar']) for a in log.before_state['allocations']]
        after = [(a['invoice'], a['amount_sar']) for a in log.after_state['allocations']]
        self.assertEqual(before, [('INV-AMEND-A', 15000)])
        self.assertEqual(after, [('INV-AMEND-A', 13000), ('INV-AMEND-B', 2000)])


class ReallocateViewTest(ReallocateControlsBase):
    def _login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

    def test_reallocate_across_the_clients_invoices(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        self._login(self.maker)
        self.client.post(f'/finance/payments/{payment.pk}/reallocate/', {
            'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 13000},
                {'reservation_id': self.r2.pk, 'amount': 2000},
            ]),
        })
        self.assertEqual(
            sorted(payment.allocations.values_list('invoice_line_id', 'amount_sar')),
            sorted([(self.r1.pk, 13000), (self.r2.pk, 2000)]),
        )
        self.assertEqual(PaymentRecord.objects.get(pk=payment.pk).invoice_id, self.inv_a.pk)

    def test_detail_offers_each_line_with_this_payments_cap(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        self._login(self.maker)
        resp = self.client.get(f'/finance/payments/{payment.pk}/', HTTP_X_INERTIA='true')
        rows = {r['id']: r for r in resp.json()['props']['reservations']}
        self.assertEqual(rows[self.r1.pk]['max_sar'], 13000)
        self.assertEqual(rows[self.r1.pk]['remaining_int'], -2000)
        self.assertEqual(rows[self.r2.pk]['max_sar'], 5000)
        self.assertEqual(rows[self.r2.pk]['invoice_number'], 'INV-AMEND-B')


class OverpaymentBannerTest(ReallocateControlsBase):
    def _login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

    def test_invoice_names_the_overpaid_reservation_and_its_payment(self):
        payment = self._paid_r1()
        self._amend_r1(13000)
        self._login(self.maker)
        props = self.client.get(f'/invoice/{self.inv_a.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(props['overpaid'], [{'line_id': self.r1.pk, 'number': 'AM-1', 'excess_sar': 2000}])
        self.assertEqual(props['overpaid_payments'], [{'id': payment.pk, 'number': payment.payment_number}])

    def test_staff_with_payment_rights_moves_the_excess_to_deposit(self):
        self._paid_r1()
        self._amend_r1(13000)
        staff = User.objects.create_user('rc_staff', password='pw12345')  # role staff: payments edit, no invoice delete
        self._login(staff)
        self.client.post(f'/finance/invoices/{self.inv_a.pk}/excess-to-deposit/')
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 2000)


class UnbilledBookingTest(ReallocateControlsBase):
    def test_detail_lists_the_clients_bookings_not_yet_invoiced(self):
        from hw.tests.factories import make_cl
        payment = self._paid_r1()
        make_cl(client=self.client_obj, confirmation_number='AM-NEW', check_in=date(2026, 9, 1),
                check_out=date(2026, 9, 3))
        self.client.force_login(self.maker)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        props = self.client.get(f'/finance/payments/{payment.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual([r['number'] for r in props['unbilled_reservations']], ['AM-NEW'])
        self.assertNotIn('AM-NEW', [r['number'] for r in props['reservations']])
