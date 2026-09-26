"""Editing a hotel invoice must not break the links hanging off its rows.

invoice_edit used to delete every Reservation and recreate it from the posted
form rows. Reservation is the dimension the ledger, the payment allocations and
the CL "paid" figures all key off (JournalLine.reservation, PaymentAllocation.
reservation, Reservation.confirmation_letter) -- and all three FKs are
SET_NULL. So a delete-recreate silently detached the money from the row it was
paid for, even when nothing about the row changed.
"""
import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, PaymentAllocation, Room
from hw.models.journal import JournalLine
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance import queries as fq
from hw.finance_helpers import create_payment_record


class InvoiceEditPreservesLinksTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('inv_edit', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        FinancialPeriod.objects.create(
            name='open', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.customer = Client.objects.create(name='PT Edit Link')
        self.check_in = date.today() + timedelta(days=30)
        self.cl = ConfirmationLetter.objects.create(
            hotel_name='Hotel Edit', guest_name='PT Edit Link', client=self.customer,
            confirmation_number='CL-EDIT-LINK-1',
            check_in=self.check_in, check_out=self.check_in + timedelta(days=2),
        )
        Room.objects.create(cl=self.cl, room_type='Quad', quantity=1, price=1000)

        # Invoice built the normal way: one Reservation per CL.
        self.client.post('/cl/invoice-from-cls/', {'cl_ids': [str(self.cl.pk)]})
        self.cl.refresh_from_db()
        self.invoice = self.cl.invoice
        self.res = self.invoice.reservations.get()

        # 2.000 SAR paid and allocated to that reservation.
        pr = create_payment_record(
            invoice=self.invoice, client=self.customer, payment_date=date.today(),
            amount=2000, method='Transfer', reference='TRX-EDIT-1',
            created_by=self.user,
        )
        posting.allocate_payment(pr, [(self.res, 2000)], created_by=self.user)
        posting.post_payment(pr, created_by=self.user)
        pr.status = pr.STATUS_ALLOCATED
        pr.save(update_fields=['status'])
        self.payment = pr

    def _edit_unchanged(self):
        """Re-submit the edit form exactly as the React form seeds it."""
        return self.client.post(f'/invoice/{self.invoice.pk}/edit/', {
            'invoice_number': self.invoice.invoice_number,
            'customer_name': self.invoice.customer_name,
            'client_id': str(self.customer.pk),
            'issued_date': self.invoice.issued_date.isoformat() if self.invoice.issued_date else '',
            'due_date': '',
            'linked_cl_ids': json.dumps([self.cl.pk]),
            'reservations': json.dumps([{
                'reservation_number': self.res.reservation_number,
                'hotel': self.res.hotel,
                'check_in': self.res.check_in.isoformat() if self.res.check_in else '',
                'check_out': self.res.check_out.isoformat() if self.res.check_out else '',
                'reservation_total': str(self.res.total_sar),
            }]),
            'payments': '[]',
        })

    def test_setup_is_sane(self):
        self.assertEqual(self.res.confirmation_letter_id, self.cl.pk)
        self.assertEqual(fq.reservation_paid_map(self.invoice.id), {self.res.pk: 2000})
        self.assertEqual(fq.cl_paid_sar_map([self.cl]), {self.cl.pk: 2000})

    def test_edit_keeps_reservation_row(self):
        self._edit_unchanged()
        rows = list(self.invoice.reservations.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, self.res.pk)

    def test_edit_keeps_cl_link_on_reservation(self):
        self._edit_unchanged()
        row = self.invoice.reservations.get()
        self.assertEqual(row.confirmation_letter_id, self.cl.pk)
        self.assertEqual(row.client_id, self.customer.pk)

    def test_edit_keeps_payment_allocation_target(self):
        self._edit_unchanged()
        alloc = PaymentAllocation.objects.get(payment=self.payment)
        self.assertIsNotNone(alloc.reservation_id)

    def test_edit_keeps_journal_reservation_dimension(self):
        self._edit_unchanged()
        self.assertFalse(
            JournalLine.objects.filter(
                invoice=self.invoice, reservation__isnull=True,
                journal_entry__entry_type='payment',
            ).exists(),
            'payment journal lines lost their reservation dimension',
        )

    def test_edit_keeps_paid_per_reservation(self):
        self._edit_unchanged()
        row = self.invoice.reservations.get()
        self.assertEqual(fq.reservation_paid_map(self.invoice.id), {row.pk: 2000})

    def test_edit_keeps_paid_on_cl(self):
        self._edit_unchanged()
        self.assertEqual(fq.cl_paid_sar_map([self.cl]), {self.cl.pk: 2000})
