"""Schema v2 F5a: denda pembatalan ditagih di invoice dan ditutup dari uang reservasinya.

Skenario dasarnya: CL 5 malam x 2.000 = 10.000 SAR, lalu dibatalkan dengan
denda 1 malam (2.000), 2 malam (4.000), atau penuh (10.000).
"""
from datetime import date

from django.contrib.auth.models import User
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from hw.finance import credit_note_service as cns
from hw.finance import posting
from hw.finance import queries as fq
from hw.finance.penalty_billing import penalty_state, reservation_balances
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import CancellationPenalty, Client, ConfirmationLetter, Invoice, InvoiceLine, Reservation
from hw.models.journal import JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import cl_form_payload, make_cl, make_invoice, make_room
from hw.views.context import _build_reservation_context


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('pen', password='pw12345')
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.client_obj = Client.objects.create(name='PT Maju Jaya', owner_branch_id='sby')
        self.cl = make_cl(
            client=self.client_obj, confirmation_number='8001', hotel_name='Al Safwah',
            check_in=date(2026, 5, 1), check_out=date(2026, 5, 6),
        )
        make_room(cl=self.cl, room_type='Quad', quantity=1, price=2000)      # 5 nights = 10,000

    def _invoice(self):
        inv = make_invoice(client=self.client_obj, invoice_number='INV-8001', issued_date=date(2026, 4, 1))
        inv.add_hotel_line(self.cl)
        posting.post_invoice_charge(inv, created_by=self.user)
        return inv

    def _pay(self, inv, sar):
        line = Reservation.objects.get(invoice=inv, confirmation_letter=self.cl)
        p = create_payment_record(inv, self.client_obj, date(2026, 4, 5), sar, method='Transfer',
                                  created_by=self.user, reservation=line)
        confirm_payment(p, self.user)
        return p

    def _cancel_with_penalty(self, amount):
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(reservation_status='CANCELLED')
        return self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-8001', 'cancellation_date': '2026-04-10', 'penalty_amount': str(amount),
        })

    def _row(self, inv):
        return _build_reservation_context(Invoice.objects.get(pk=inv.pk))[0]


class PaidReservationCancelledTest(_Base):
    """Already paid 10,000, then cancelled with a penalty."""

    def _case(self, penalty, *, excess):
        inv = self._invoice()
        self._pay(inv, 10_000)
        self.assertEqual(self._cancel_with_penalty(penalty).status_code, 302)
        inv = Invoice.objects.get(pk=inv.pk)
        pen = CancellationPenalty.objects.get(penalty_number='PNL-8001')
        self.assertEqual(pen.invoice, inv)                       # same invoice
        self.assertEqual(inv.total_sar, penalty)                 # reservation now bills 0
        self.assertEqual(fq.invoice_charged_sar(inv.pk), penalty)
        self.assertEqual(inv.remaining_sar, -excess)             # negative = overpaid
        state = penalty_state(pen)
        self.assertEqual((state['due'], state['paid'], state['is_paid']), (penalty, penalty, True))
        row = self._row(inv)
        self.assertEqual((row['total_int'], row['penalty_int'], row['paid_int'], row['remaining_int']),
                         (penalty, penalty, 10_000, -excess))
        self.assertEqual(fq.client_receivable(self.client_obj.pk), -excess)

    def test_one_night_penalty_leaves_8000_excess(self):
        self._case(2_000, excess=8_000)

    def test_two_night_penalty_leaves_6000_excess(self):
        self._case(4_000, excess=6_000)

    def test_full_penalty_leaves_nothing(self):
        self._case(10_000, excess=0)


class PartlyOrNotPaidTest(_Base):
    def test_partial_payment_covers_part_of_the_penalty(self):
        inv = self._invoice()
        self._pay(inv, 3_000)
        self._cancel_with_penalty(4_000)
        pen = CancellationPenalty.objects.get()
        state = penalty_state(pen)
        self.assertEqual((state['due'], state['paid'], state['is_paid']), (4_000, 3_000, False))
        self.assertEqual(Invoice.objects.get(pk=inv.pk).remaining_sar, 1_000)

    def test_unpaid_reservation_owes_the_penalty(self):
        inv = self._invoice()
        self._cancel_with_penalty(4_000)
        inv = Invoice.objects.get(pk=inv.pk)
        self.assertEqual((inv.total_sar, inv.remaining_sar), (4_000, 4_000))
        self.assertFalse(CancellationPenalty.objects.get().is_paid)
        # Paying it later is an ordinary payment against the reservation.
        self._pay(inv, 4_000)
        pen = CancellationPenalty.objects.get()
        self.assertTrue(pen.is_paid)
        self.assertEqual(pen.payment_date, date(2026, 4, 5))
        self.assertEqual(Invoice.objects.get(pk=inv.pk).remaining_sar, 0)


class UninvoicedReservationTest(_Base):
    def test_saving_the_penalty_issues_an_invoice(self):
        self.assertIsNone(self.cl.invoice)
        resp = self.client.get(f'/cl/{self.cl.pk}/penalty/new/', HTTP_X_INERTIA='true')
        # (status is still DEFINITE here, so the form is refused until cancelled)
        self.assertEqual(resp.status_code, 302)
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(reservation_status='CANCELLED')
        billing = self.client.get(f'/cl/{self.cl.pk}/penalty/new/', HTTP_X_INERTIA='true').json()['props']['billing']
        self.assertTrue(billing['creates_invoice'])

        self.assertEqual(self._cancel_with_penalty(4_000).status_code, 302)
        pen = CancellationPenalty.objects.get()
        inv = pen.invoice
        self.assertIsNotNone(inv)
        self.assertEqual((inv.client_id, inv.branch_id, inv.currency, inv.issued_date),
                         (self.client_obj.pk, 'sby', 'SAR', date(2026, 4, 10)))
        kinds = sorted(inv.lines.values_list('kind', flat=True))
        self.assertEqual(kinds, ['hotel', 'penalty'])
        self.assertEqual((inv.total_sar, inv.remaining_sar), (4_000, 4_000))
        self.assertEqual(inv.revisions.get().reason, 'issue')

    def test_form_says_which_invoice_when_already_invoiced(self):
        inv = self._invoice()
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(reservation_status='CANCELLED')
        billing = self.client.get(f'/cl/{self.cl.pk}/penalty/new/', HTTP_X_INERTIA='true').json()['props']['billing']
        self.assertEqual((billing['creates_invoice'], billing['invoice_number']), (False, inv.invoice_number))


class RefusedPenaltyFormTest(_Base):
    def test_a_refused_save_keeps_what_was_typed(self):
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(reservation_status='CANCELLED')
        resp = self.client.post(f'/cl/{self.cl.pk}/penalty/new/', {
            'penalty_number': 'PNL-8002', 'cancellation_date': '2026-04-10',
            'penalty_amount': '0', 'reason': 'Guest cancelled late',
        }, HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertIn('penalty_amount', props['errors'])
        self.assertEqual((props['penalty']['reason'], props['penalty']['penalty_number']),
                         ('Guest cancelled late', 'PNL-8002'))


class PenaltyLineRulesTest(_Base):
    def setUp(self):
        super().setUp()
        self.inv = self._invoice()
        self._cancel_with_penalty(4_000)
        self.pen = CancellationPenalty.objects.get()

    def test_charge_carries_the_reservation_and_pusat_revenue(self):
        hotel_line = InvoiceLine.objects.get(invoice=self.inv, kind='hotel')
        ar = JournalLine.objects.filter(penalty=self.pen, account_id=fq.coa.AR, debit__gt=0).latest('pk')
        income = JournalLine.objects.filter(penalty=self.pen, account_id=fq.coa.INC_PENALTY).latest('pk')
        self.assertEqual((ar.invoice_line_id, ar.invoice_id, ar.branch_id), (hotel_line.pk, self.inv.pk, 'sby'))
        self.assertEqual((income.credit, income.branch_id), (4_000, 'pusat'))

    def test_changing_the_amount_reposts_once(self):
        self.client.post(f'/penalty/{self.pen.pk}/edit/', {
            'penalty_number': 'PNL-8001', 'cancellation_date': '2026-04-10', 'penalty_amount': '2000',
        })
        self.assertEqual(fq.invoice_charged_sar(self.inv.pk), 2_000)
        self.assertEqual(InvoiceLine.objects.filter(kind='penalty', penalty=self.pen).count(), 1)
        self.assertEqual(self.inv.revisions.order_by('-revision_no').first().total, 2_000)

    def test_void_invoice_unbills_and_reinvoicing_bills_it_again(self):
        cns.void_invoice(self.inv, reason='salah cabang', created_by=self.user)
        self.assertIsNone(CancellationPenalty.objects.get().invoice)
        self.assertEqual(Invoice.objects.get(pk=self.inv.pk).total_sar, 4_000)      # history kept
        new = make_invoice(client=self.client_obj, invoice_number='INV-8002', issued_date=date(2026, 4, 12))
        new.add_hotel_line(self.cl)                       # the penalty follows its reservation
        self.assertEqual(CancellationPenalty.objects.get().invoice, new)
        self.assertEqual(new.total_sar, 4_000)

    def test_taking_the_reservation_off_the_invoice_takes_the_penalty_too(self):
        import json
        other = make_cl(client=self.client_obj, confirmation_number='8002',
                        check_in=date(2026, 5, 1), check_out=date(2026, 5, 2))
        make_room(cl=other, room_type='Quad', quantity=1, price=500)
        resp = self.client.post(f'/invoice/{self.inv.pk}/edit/', {
            'client_id': str(self.client_obj.pk), 'invoice_number': self.inv.invoice_number,
            'issued_date': '2026-04-01', 'due_date': '', 'linked_cl_ids': json.dumps([other.pk]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(CancellationPenalty.objects.get().invoice)
        inv = Invoice.objects.get(pk=self.inv.pk)
        self.assertEqual((inv.total_sar, fq.invoice_charged_sar(inv.pk)), (500, 500))

    def test_penalty_can_be_waived_with_a_credit_note(self):
        line = InvoiceLine.objects.get(kind='penalty', penalty=self.pen)
        rows = {r['kind']: r for r in cns.creditable_lines(self.inv)}
        self.assertEqual(rows['penalty']['available'], 4_000)
        cns.issue_credit_note(
            self.inv, lines=[{'kind': 'penalty', 'id': line.pk, 'amount_sar': 4_000}],
            reason='Denda dibebaskan', issued_date=date(2026, 4, 11), created_by=self.user,
        )
        self.assertEqual(Invoice.objects.get(pk=self.inv.pk).due_sar, 0)
        self.assertEqual(fq.account_balance(fq.coa.INC_PENALTY), 0)
        self.assertEqual(penalty_state(self.pen)['due'], 0)
        self.assertEqual(reservation_balances(self.inv)[InvoiceLine.objects.get(invoice=self.inv, kind='hotel').pk]['remaining'], 0)

    def test_billed_penalty_is_not_deleted(self):
        self.client.post(f'/penalty/{self.pen.pk}/delete/')
        self.assertTrue(CancellationPenalty.objects.filter(pk=self.pen.pk).exists())
        with self.assertRaises(ProtectedError):
            self.pen.delete()

    def test_reservation_with_a_penalty_stays_cancelled(self):
        cl = ConfirmationLetter.objects.get(pk=self.cl.pk)
        resp = self.client.post(f'/cl/{cl.pk}/edit/', cl_form_payload(cl, reservation_status='DEFINITE'),
                                HTTP_X_INERTIA='true')
        self.assertIn('reservation_status', resp.json()['props']['errors'])
        self.assertEqual(ConfirmationLetter.objects.get(pk=cl.pk).reservation_status, 'CANCELLED')

    def test_penalty_no_longer_stores_invoice_or_paid_flag(self):
        fields = {f.name for f in CancellationPenalty._meta.get_fields()}
        self.assertFalse({'invoice', 'is_paid', 'payment_date', 'payment_method', 'payment_note'} & fields)
