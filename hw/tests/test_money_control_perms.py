"""Mengambil uang kembali (void/reverse pembayaran) dan memutuskan uang keluar
dari deposit (setujui/tolak refund dan transfer) butuh payments.delete --
sama dengan void expense, exchange, dan invoice. Staff hanya punya edit, jadi
ia mencatat; Manager/Admin yang memutuskan."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance.deposit import request_refund
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import Client
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_account


def _user(username, role):
    user = User.objects.create_user(username, password='pw12345')
    user.profile.role = role
    user.profile.save(update_fields=['role'])
    return user


class MoneyControlPermissionTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.client_obj = Client.objects.create(name='PT Money Control')
        self.staff = _user('mcp_staff', 'staff')
        self.staff2 = _user('mcp_staff2', 'staff')
        self.manager = _user('mcp_manager', 'manager')

    def _post_as(self, user, url):
        self.client.force_login(user)
        return self.client.post(url)

    def _confirmed_payment(self):
        payment = create_payment_record(
            invoice=None, client=self.client_obj, payment_date=date(2026, 1, 5),
            amount=1000, method='Cash', created_by=self.staff,
        )
        confirm_payment(payment, confirmed_by=self.manager)
        return payment

    def _status(self, obj):
        obj.refresh_from_db()
        return obj.status

    def test_staff_cannot_void_or_reverse_a_payment(self):
        payment = self._confirmed_payment()
        for action in ('void', 'reverse'):
            self._post_as(self.staff, f'/finance/payments/{payment.pk}/{action}/')
            self.assertEqual(self._status(payment), PaymentRecord.STATUS_CONFIRMED, action)

    def test_manager_can_void_a_payment(self):
        payment = self._confirmed_payment()
        self._post_as(self.manager, f'/finance/payments/{payment.pk}/void/')
        self.assertEqual(self._status(payment), PaymentRecord.STATUS_VOIDED)

    def test_manager_can_reverse_a_payment(self):
        payment = self._confirmed_payment()
        self._post_as(self.manager, f'/finance/payments/{payment.pk}/reverse/')
        self.assertEqual(self._status(payment), PaymentRecord.STATUS_REVERSED)

    def _pending_refund(self):
        posting.post_adjustment(
            lines=[{"account": posting.coa.CASH_SBY, "debit": 5_000},
                   {"account": posting.coa.CUST_CREDIT, "credit": 5_000, "client": self.client_obj.pk}],
            description='deposit awal', entry_date=date(2026, 3, 1), created_by=self.manager,
        )
        return request_refund(
            self.client_obj, account=make_account('sby', 'SAR'), amount_sar=2_000, amount_paid=2_000,
            refund_date=date(2026, 3, 10), created_by=self.staff,
        )

    def test_another_staff_cannot_approve_a_refund(self):
        refund = self._pending_refund()
        self._post_as(self.staff2, f'/finance/refunds/{refund.pk}/confirm/')
        self.assertEqual(self._status(refund), 'pending')

    def test_manager_approves_a_refund(self):
        refund = self._pending_refund()
        self._post_as(self.manager, f'/finance/refunds/{refund.pk}/confirm/')
        self.assertEqual(self._status(refund), 'confirmed')
