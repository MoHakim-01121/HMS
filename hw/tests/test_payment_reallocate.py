"""Reallocation of an effective payment (post-hoc) + unallocated tracking.

A payment that was received without (or with partial) allocation can later be
assigned to reservations. Because the ledger is append-only, reallocation
reverses the live payment entry and re-posts with the correct reservation
dimension on the CR Piutang lines.
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, PaymentRecord, PaymentAllocation
from hw.models.period import FinancialPeriod
from hw.models.journal import JournalEntry, JournalLine
from hw.finance import accounts as coa
from hw.finance import queries as fq
from hw.finance import posting
from hw.tests.factories import make_hotel_line, make_invoice


class PaymentReallocateTest(TestCase):
    def setUp(self):
        u = User.objects.create_user('realloc', password='pw12345')
        u.profile.role = 'manager'
        u.profile.save(update_fields=['role'])
        self.user = u
        self.client.force_login(u)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        c = Client.objects.create( name='PT Realloc')
        self.invoice = make_invoice(
 invoice_type='hotel', client=c,
            invoice_number='INV-REALLOC-001', customer_name='PT Realloc',
        )
        self.r1 = make_hotel_line(
            invoice=self.invoice, reservation_number='RE-1', total_sar=15000,
        )
        self.r2 = make_hotel_line(
            invoice=self.invoice, reservation_number='RE-2', total_sar=8000,
        )
        FinancialPeriod.objects.create(
            name='2026-08', date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        )

        # Charge invoice so AR + paid math works
        posting.post_entry(
            entry_type=JournalEntry.TYPE_CHARGE,
            description='Charge INV-REALLOC-001',
            entry_date=date(2026, 8, 10),
            lines=[
                {"account": coa.AR, "debit": 23000, "client": c.pk, "invoice": self.invoice.pk},
                {"account": coa.INC_HOTEL, "credit": 23000, "client": c.pk, "invoice": self.invoice.pk},
            ],
            source_type='Invoice', source_id=self.invoice.pk,
            idempotency_key='charge:INV-REALLOC-001',
            created_by=u,
        )

    def _record_unallocated(self, amount_sar=20000):
        """Create an effective (confirmed+allocated) payment with NO allocations."""
        from ..finance_helpers import create_payment_record, confirm_payment, allocate_payment as fh_allocate
        pr = create_payment_record(
            invoice=self.invoice, client=self.invoice.client,
            payment_date=date(2026, 8, 20), amount=amount_sar, currency='SAR',
            method='Transfer', created_by=self.user,
        )
        confirm_payment(pr, confirmed_by=self.user)
        fh_allocate(pr, allocation_date=pr.payment_date, created_by=self.user)
        return pr

    def test_payment_without_allocation_is_unallocated(self):
        pr = self._record_unallocated(20000)
        self.assertEqual(pr.status, PaymentRecord.STATUS_ALLOCATED)
        self.assertEqual(fq.payment_unallocated_sar(pr.pk), 20000)
        self.assertEqual(fq.invoice_unallocated_sar(self.invoice.pk), 20000)

        # AR credit carries NO reservation dimension -> reservation paid map empty
        self.assertEqual(fq.reservation_paid_map(self.invoice.pk), {})
        # invoice_paid reflects the CR even without reservation dim
        self.assertEqual(fq.invoice_paid_sar(self.invoice.pk), 20000)

    def test_payment_bound_directly_to_reservation_is_allocated(self):
        """A payment attached directly to one reservation (no PaymentAllocation
        rows) counts as fully allocated, not unallocated."""
        from ..finance_helpers import create_payment_record, confirm_payment, allocate_payment as fh_allocate
        pr = create_payment_record(
            invoice=self.invoice, client=self.invoice.client, reservation=self.r1,
            payment_date=date(2026, 8, 20), amount=15000, currency='SAR',
            method='Transfer', created_by=self.user,
        )
        self.assertEqual(int(pr.amount_sar), 15000)
        self.assertEqual(pr.reservation_id, self.r1.pk)
        confirm_payment(pr, confirmed_by=self.user)
        fh_allocate(pr, allocation_date=pr.payment_date, created_by=self.user)
        pr.refresh_from_db()

        self.assertEqual(pr.status, PaymentRecord.STATUS_ALLOCATED)
        self.assertEqual(PaymentAllocation.objects.filter(payment=pr).count(), 0)
        # Direct reservation binding -> fully allocated (no unallocated warning)
        self.assertEqual(fq.payment_unallocated_sar(pr.pk), 0)

    def test_reallocate_assigns_to_reservation(self):
        pr = self._record_unallocated(20000)

        resp = self.client.post(f'/finance/payments/{pr.pk}/reallocate/', {
            'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 12000},
                {'reservation_id': self.r2.pk, 'amount': 8000},
            ]),
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        pr.refresh_from_db()

        # PaymentAllocation rows replaced
        allocs = {a.reservation_id: a.amount_sar for a in pr.allocations.all()}
        self.assertEqual(allocs, {self.r1.pk: 12000, self.r2.pk: 8000})
        self.assertEqual(fq.payment_unallocated_sar(pr.pk), 0)

        # Reservation paid map now reflects the allocations
        rpm = fq.reservation_paid_map(self.invoice.pk)
        self.assertEqual(rpm.get(self.r1.pk), 12000)
        self.assertEqual(rpm.get(self.r2.pk), 8000)
        self.assertEqual(fq.invoice_unallocated_sar(self.invoice.pk), 0)

        # Journal AR lines carry the reservation dimension
        reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
        ar_live = JournalLine.objects.filter(
            invoice=self.invoice, account_id=coa.AR, credit__gt=0,
        ).exclude(journal_entry_id__in=reversed_ids).exclude(journal_entry__is_reversal=True)
        res_dims = set()
        for ln in ar_live:
            if ln.reservation_id:
                res_dims.add((ln.reservation_id, ln.credit))
        self.assertTrue((self.r1.pk, 12000) in res_dims)
        self.assertTrue((self.r2.pk, 8000) in res_dims)

    def test_partial_reallocate_leaves_remainder_unallocated(self):
        pr = self._record_unallocated(20000)

        self.client.post(f'/finance/payments/{pr.pk}/reallocate/', {
            'allocations': json.dumps([{'reservation_id': self.r1.pk, 'amount': 7000}]),
        }, follow=True)

        pr.refresh_from_db()
        self.assertEqual(fq.payment_unallocated_sar(pr.pk), 13000)
        rpm = fq.reservation_paid_map(self.invoice.pk)
        self.assertEqual(rpm.get(self.r1.pk), 7000)
        self.assertEqual(fq.invoice_unallocated_sar(self.invoice.pk), 13000)

    def test_reallocate_over_payment_is_rejected(self):
        pr = self._record_unallocated(20000)
        self.client.post(f'/finance/payments/{pr.pk}/reallocate/', {
            'allocations': json.dumps([{'reservation_id': self.r1.pk, 'amount': 25000}]),
        }, follow=True)
        pr.refresh_from_db()
        # No allocation created
        self.assertEqual(pr.allocations.count(), 0)
        self.assertEqual(fq.payment_unallocated_sar(pr.pk), 20000)

    def test_pending_payment_cannot_be_reallocated(self):
        from ..finance_helpers import create_payment_record
        pr = create_payment_record(
            invoice=self.invoice, client=self.invoice.client,
            payment_date=date(2026, 8, 20), amount=1000, currency='SAR',
            method='Cash', created_by=self.user,
        )
        # still pending
        self.client.post(f'/finance/payments/{pr.pk}/reallocate/', {
            'allocations': json.dumps([{'reservation_id': self.r1.pk, 'amount': 1000}]),
        }, follow=True)
        self.assertEqual(pr.allocations.count(), 0)
