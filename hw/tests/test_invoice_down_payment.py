"""Invoice down payment: agreed percent per invoice, met by ordinary payments."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hw.context_processors import _invoice_notifs
from hw.finance import posting
from hw.models import Client, Invoice
from hw.models.payment import PaymentAllocation, PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_payment, make_room
from hw.views.invoice_views import _posted_down_payment


class DownPaymentBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dp', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.client_obj = Client.objects.create(name='PT DP')
        self.today = timezone.localdate()
        self.invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj, invoice_number='INV-DP-1', customer_name='PT DP',
            issued_date=self.today, due_date=self.today + timedelta(days=20), down_payment_percent=30,
        )
        self.line = make_hotel_line(
            invoice=self.invoice, reservation_number='R1', hotel='Dar Al Eiman',
            check_in=self.today + timedelta(days=60), check_out=self.today + timedelta(days=65), total_sar=45_850,
        )

    def _pay(self, amount_sar, number='PAY-DP-1'):
        payment = make_payment(
            payment_number=number, invoice=self.invoice, client=self.client_obj, payment_date=self.today,
            amount=amount_sar, currency='SAR', exchange_rate=1, amount_sar=amount_sar, method='Transfer',
            status=PaymentRecord.STATUS_CONFIRMED, created_by=self.user,
        )
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.line, amount_sar=amount_sar)
        posting.post_payment(payment, created_by=self.user)


class DownPaymentFiguresTest(DownPaymentBase):
    def test_amount_rounds_half_up_and_is_due_a_day_after_issue(self):
        self.assertEqual(self.invoice.down_payment_sar, 13_755)
        self.assertEqual(self.invoice.down_payment_due_date, self.today + timedelta(days=1))

    def test_other_percents_are_allowed(self):
        self.invoice.down_payment_percent = 20
        self.assertEqual(self.invoice.down_payment_sar, 9_170)

    def test_ordinary_payments_meet_it(self):
        self._pay(5_000)
        self.assertEqual(self.invoice.down_payment_outstanding_sar, 8_755)
        self._pay(8_755, number='PAY-DP-2')
        self.assertEqual(self.invoice.down_payment_outstanding_sar, 0)

    def test_overdue_only_after_the_due_date_while_unpaid(self):
        self.assertFalse(self.invoice.down_payment_overdue)
        self.invoice.issued_date = self.today - timedelta(days=2)
        self.assertTrue(self.invoice.down_payment_overdue)

    def test_no_percent_means_no_due_date(self):
        self.invoice.down_payment_percent = 0
        self.assertIsNone(self.invoice.down_payment_due_date)
        self.assertFalse(self.invoice.down_payment_overdue)


class DownPaymentNoticeTest(DownPaymentBase):
    def _notifs(self):
        return [n for n in _invoice_notifs(self.user, self.today, self.today + timedelta(days=7), 20, ['hotel']) if 'DP' in n['title']]

    def test_outstanding_down_payment_is_notified(self):
        notifs = self._notifs()
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0]['remaining'], 13_755)
        self.assertEqual(notifs[0]['days'], 1)

    def test_met_down_payment_is_not_notified(self):
        self._pay(13_755)
        self.assertEqual(self._notifs(), [])


class DownPaymentPostTest(DownPaymentBase):
    def _post(self, percent):
        cl = make_cl(client=self.client_obj, confirmation_number='CL-DP-1', hotel_name='Hotel DP')
        make_room(cl=cl, room_type='Quad', quantity=1, price=1000)
        return self.client.post('/invoice/new/', {
            'invoice_number': 'INV-DP-NEW', 'customer_name': 'PT DP', 'client_id': self.client_obj.pk,
            'issued_date': self.today.isoformat(), 'due_date': self.today.isoformat(),
            'down_payment_percent': percent, 'linked_cl_ids': json.dumps([cl.pk]), 'reservations': '[]',
        })

    def test_percent_is_saved_on_the_invoice(self):
        self._post('20')
        self.assertEqual(Invoice.objects.get(invoice_number='INV-DP-NEW').down_payment_percent, 20)

    def test_over_one_hundred_is_refused(self):
        self._post('120')
        self.assertFalse(Invoice.objects.filter(invoice_number='INV-DP-NEW').exists())

    def test_blank_means_none(self):
        request = SimpleNamespace(POST={'down_payment_percent': ''})
        self.assertEqual(_posted_down_payment(request), 0)
