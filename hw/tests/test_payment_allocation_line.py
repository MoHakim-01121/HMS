"""Schema v2 F5b: alokasi pembayaran menunjuk tepat satu baris invoice."""
from datetime import date

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.utils import DatabaseError
from django.test import TestCase

from hw.db_pg import pg_only
from hw.finance import posting
from hw.finance.errors import FinanceError
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import (
    CancellationPenalty, Client, ConfirmationLetter, InvoiceLine, PaymentAllocation, PaymentRecord,
)
from hw.models.journal import JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_client, make_hotel_line, make_invoice, make_service_line


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('alloc', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.client_obj = Client.objects.create(name='PT Alokasi')
        self.inv = make_invoice(client=self.client_obj, issued_date=date(2026, 3, 1))
        self.line = make_hotel_line(invoice=self.inv, reservation_number='9001', total_sar=5000)
        posting.post_invoice_charge(self.inv, created_by=self.user)

    def _payment(self, amount=5000, **kw):
        return create_payment_record(self.inv, self.client_obj, date(2026, 3, 5), amount, method='Transfer',
                                     created_by=self.user, **kw)


class AllocationTargetTest(_Base):
    def test_columns(self):
        fields = {f.name for f in PaymentAllocation._meta.get_fields()}
        self.assertIn('invoice_line', fields)
        self.assertFalse({'reservation', 'service_item', 'penalty'} & fields)
        self.assertFalse({'reservation', 'service_item'} & {f.name for f in PaymentRecord._meta.get_fields()})

    def test_payment_for_one_reservation_is_one_full_allocation(self):
        p = self._payment(reservation=self.line)
        alloc = p.allocations.get()
        self.assertEqual((alloc.invoice_line_id, alloc.amount_sar), (self.line.pk, 5000))
        self.assertEqual((alloc.reservation_id, alloc.service_item_id), (self.line.pk, None))
        confirm_payment(p, self.user)
        credit = JournalLine.objects.get(journal_entry__source_payment__isnull=False, credit__gt=0)
        self.assertEqual((credit.invoice_line_id, credit.credit), (self.line.pk, 5000))

    def test_service_allocation_posts_the_service_dimension(self):
        svc_inv = make_invoice(client=self.client_obj, invoice_type='visa', currency='SAR', issued_date=date(2026, 3, 1))
        svc = make_service_line(svc_inv, name='Visa', qty=2, price=300)
        posting.post_invoice_charge(svc_inv, created_by=self.user)
        p = create_payment_record(svc_inv, self.client_obj, date(2026, 3, 5), 600, method='Transfer',
                                  created_by=self.user, service_item=svc)
        confirm_payment(p, self.user)
        credit = JournalLine.objects.get(journal_entry__source_payment=p.pk, credit__gt=0)
        self.assertEqual((credit.invoice_line_id, credit.invoice_line.kind), (svc.pk, 'service'))

    def test_unallocated_part_stays_without_a_line(self):
        p = self._payment(7000)
        posting.allocate_payment(p, [(self.line, 5000)], created_by=self.user)
        confirm_payment(p, self.user)
        from hw.finance import queries as fq
        self.assertEqual(fq.payment_unallocated_sar(p.pk), 2000)
        credits = JournalLine.objects.filter(journal_entry__source_payment=p.pk, credit__gt=0)
        self.assertEqual({c.invoice_line_id: c.credit for c in credits}, {None: 2000, self.line.pk: 5000})

    def test_line_with_an_allocation_cannot_be_deleted(self):
        self._payment(reservation=self.line)
        with self.assertRaises(ProtectedError):
            InvoiceLine.objects.get(pk=self.line.pk).delete()

    def test_penalty_line_is_not_an_allocation_target(self):
        from hw.finance.penalty_billing import bill_penalty
        cl = self.line.confirmation_letter
        ConfirmationLetter.objects.filter(pk=cl.pk).update(reservation_status='CANCELLED')
        pen = CancellationPenalty.objects.create(cl=cl, penalty_number='PNL-9', cancellation_date=date(2026, 3, 2), penalty_amount=1000)
        bill_penalty(pen, user=self.user)
        pen_line = InvoiceLine.objects.get(kind='penalty', penalty=pen)
        p = self._payment(1000)
        with self.assertRaises(FinanceError):
            posting.allocate_payment(p, [(pen_line, 1000)], created_by=self.user)
        # The money goes to the reservation's line, and that pays the penalty.
        posting.allocate_payment(p, [(self.line, 1000)], created_by=self.user)
        confirm_payment(p, self.user)
        self.assertTrue(CancellationPenalty.objects.get(pk=pen.pk).is_paid)


@pg_only
class AllocationTriggerTest(_Base):
    def _refused(self, fn, text):
        with self.assertRaises(DatabaseError) as ctx, transaction.atomic():
            fn()
        self.assertIn(text, str(ctx.exception))

    def test_allocation_to_another_clients_invoice_is_refused(self):
        other = make_invoice(client=make_client('PT Lain'), issued_date=date(2026, 3, 1))
        other_line = make_hotel_line(invoice=other, reservation_number='9002', total_sar=100)
        p = self._payment(100)
        self._refused(
            lambda: PaymentAllocation.objects.create(payment=p, invoice_line=other_line, amount_sar=100),
            'milik client lain',
        )

    def test_allocation_to_a_penalty_line_is_refused(self):
        cl = self.line.confirmation_letter
        ConfirmationLetter.objects.filter(pk=cl.pk).update(reservation_status='CANCELLED')
        pen = CancellationPenalty.objects.create(cl=cl, penalty_number='PNL-9', cancellation_date=date(2026, 3, 2), penalty_amount=1000)
        pen_line = self.inv.add_penalty_line(pen)
        p = self._payment(1000)
        self._refused(
            lambda: PaymentAllocation.objects.create(payment=p, invoice_line=pen_line, amount_sar=1000),
            'denda dibayar lewat baris hotel',
        )
