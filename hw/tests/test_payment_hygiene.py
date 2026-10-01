"""Batch 3: allocation hygiene, honest KPIs, filtered exports, bulk queries.

Each test here pins a behaviour that used to fail quietly rather than loudly:
allocations outliving the payment that created them, a dashboard number capped
by its own preview slice, an export ignoring the filter the user was looking
at, and a per-row query where a bulk one exists.
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import queries as fq
from hw.models import Client
from hw.models.payment import PaymentRecord, PaymentAllocation
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice, make_payment


def _props(response):
    return json.loads(response.context['page'])['props']


class PaymentHygieneBase(TestCase):
    def setUp(self):
        user = User.objects.create_user('hygiene', password='pw12345')
        user.profile.role = 'manager'
        user.profile.save(update_fields=['role'])
        self.user = user
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        self.period = FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Hygiene')
        self.invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-HYG-001', customer_name='PT Hygiene',
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number='HYG-R1', hotel='Hotel Hygiene',
            total_sar=30000,
        )
        # A reservation on a different invoice — a valid pk, wrong owner.
        self.other_invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-HYG-OTHER', customer_name='PT Hygiene',
        )
        self.foreign_res = make_hotel_line(
            invoice=self.other_invoice, reservation_number='HYG-X1',
            hotel='Hotel Elsewhere', total_sar=9000,
        )

    def _payment(self, number='PAY-HYG-001', amount_sar=20000,
                 status=PaymentRecord.STATUS_PENDING, **kw):
        return make_payment(
            payment_number=number, invoice=self.invoice, client=self.client_obj,
            payment_date=date(2026, 1, 10), amount=amount_sar, currency='SAR',
            exchange_rate=1, amount_sar=amount_sar, method='Transfer',
            status=status, period=self.period, created_by=self.user, **kw
        )


class AllocationCleanupTest(PaymentHygieneBase):
    def test_rejecting_a_payment_removes_its_allocations(self):
        payment = self._payment()
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.res, amount_sar=20000)

        resp = self.client.post(f'/finance/payments/{payment.pk}/reject/')
        self.assertEqual(resp.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_REJECTED)
        self.assertEqual(payment.allocations.count(), 0)

    def test_rejected_payment_reports_no_allocated_money(self):
        payment = self._payment(number='PAY-HYG-002')
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.res, amount_sar=20000)
        self.client.post(f'/finance/payments/{payment.pk}/reject/')

        self.assertEqual(fq.payment_unallocated_sar(payment.pk), payment.amount_sar)

    def test_the_dropped_rows_are_kept_in_the_payment_log(self):
        payment = self._payment(number='PAY-HYG-003')
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.res, amount_sar=20000)
        self.client.post(f'/finance/payments/{payment.pk}/reject/')

        log = payment.logs.filter(action='rejected').first()
        self.assertIsNotNone(log)
        self.assertEqual(len(log.before_state['allocations']), 1)
        self.assertEqual(log.before_state['allocations'][0]['amount_sar'], 20000)

    def test_voiding_a_payment_removes_its_allocations(self):
        payment = self._payment(number='PAY-HYG-004', status=PaymentRecord.STATUS_CONFIRMED)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.res, amount_sar=20000)

        resp = self.client.post(f'/finance/payments/{payment.pk}/void/')
        self.assertEqual(resp.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_VOIDED)
        self.assertEqual(payment.allocations.count(), 0)


class ForeignReservationIsRefusedTest(PaymentHygieneBase):
    def test_apply_refuses_a_reservation_from_another_invoice(self):
        payment = self._payment(number='PAY-HYG-010', status=PaymentRecord.STATUS_CONFIRMED)

        resp = self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            data=json.dumps({'allocations': [
                {'reservation_id': self.res.pk, 'amount': 10000},
                {'reservation_id': self.foreign_res.pk, 'amount': 5000},
            ]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 302)
        # Nothing partial: the whole request is refused, not silently trimmed.
        self.assertEqual(payment.allocations.count(), 0)

    def test_reallocate_refuses_a_reservation_from_another_invoice(self):
        payment = self._payment(number='PAY-HYG-011', status=PaymentRecord.STATUS_CONFIRMED)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.res, amount_sar=20000)

        resp = self.client.post(
            f'/finance/payments/{payment.pk}/reallocate/',
            data=json.dumps({'allocations': [
                {'reservation_id': self.foreign_res.pk, 'amount': 5000},
            ]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 302)
        # The existing allocation is untouched by a refused reallocation.
        self.assertEqual(payment.allocations.count(), 1)
        self.assertEqual(payment.allocations.first().reservation_id, self.res.pk)


class FinanceHubKpiTest(PaymentHygieneBase):
    def test_pending_review_counts_every_pending_payment_not_just_the_preview(self):
        for i in range(9):
            self._payment(number=f'PAY-HYG-P{i}', amount_sar=1000)

        props = _props(self.client.get('/finance/'))
        self.assertEqual(props['payments']['pending_review'], 9)
        self.assertEqual(props['payments']['pending_review_total'], 9000)


class PaymentExportFilterTest(PaymentHygieneBase):
    def test_export_honours_the_invoice_filter(self):
        self._payment(number='PAY-HYG-E1', amount_sar=1000)
        make_payment(
            payment_number='PAY-HYG-E2', invoice=self.other_invoice,
            client=self.client_obj, payment_date=date(2026, 1, 10), amount=2000,
            currency='SAR', exchange_rate=1, amount_sar=2000, method='Transfer',
            status=PaymentRecord.STATUS_PENDING, period=self.period,
            created_by=self.user,
        )

        body = self.client.get(
            f'/finance/payments/export/csv/?invoice={self.invoice.pk}'
        ).content.decode('utf-8', 'replace')
        self.assertIn('PAY-HYG-E1', body)
        self.assertNotIn('PAY-HYG-E2', body)


class UnallocatedMapTest(PaymentHygieneBase):
    def test_bulk_map_agrees_with_the_single_row_helper(self):
        unallocated = self._payment(number='PAY-HYG-M1', amount_sar=5000)
        partial = self._payment(number='PAY-HYG-M2', amount_sar=8000)
        PaymentAllocation.objects.create(payment=partial, invoice_line=self.res, amount_sar=3000)
        direct = self._payment(number='PAY-HYG-M3', amount_sar=7000)
        PaymentAllocation.objects.create(payment=direct, invoice_line=self.res, amount_sar=7000)

        ids = [unallocated.pk, partial.pk, direct.pk]
        bulk = fq.payment_unallocated_map(ids)
        self.assertEqual(bulk, {pk: fq.payment_unallocated_sar(pk) for pk in ids})
        self.assertEqual(bulk[unallocated.pk], 5000)
        self.assertEqual(bulk[partial.pk], 5000)
        self.assertEqual(bulk[direct.pk], 0)

    def test_empty_input_needs_no_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(fq.payment_unallocated_map([]), {})

    def test_bulk_map_is_a_fixed_number_of_queries(self):
        for i in range(6):
            self._payment(number=f'PAY-HYG-N{i}', amount_sar=1000)
        ids = list(PaymentRecord.objects.values_list('pk', flat=True))
        with self.assertNumQueries(2):
            fq.payment_unallocated_map(ids)
