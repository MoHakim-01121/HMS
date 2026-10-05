"""Pemisahan tugas pada konfirmasi pembayaran: pencatat ≠ penyetuju.

Hanya admin yang boleh mengonfirmasi pembayaran yang ia catat sendiri, dan
pengecualian itu tercatat di PaymentLog.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance_helpers import create_payment_record
from hw.models import Client
from hw.models.journal import JournalEntry
from hw.models.payment import PaymentLog, PaymentRecord
from hw.models.period import FinancialPeriod


def _user(username, role=None, superuser=False):
    user = User.objects.create_user(username, password='pw12345', is_superuser=superuser)
    if role:
        user.profile.role = role
        user.profile.save(update_fields=['role'])
    return user


class PaymentMakerCheckerTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Maker Checker')
        self.staff = _user('mc_staff', role='staff')
        self.manager = _user('mc_manager', role='manager')
        self.admin = _user('mc_admin', superuser=True)

    def _payment(self, created_by):
        return create_payment_record(
            invoice=None, client=self.client_obj, payment_date=date(2026, 1, 5),
            amount=1000, method='Cash', created_by=created_by,
        )

    def _confirm_as(self, user, payment):
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        return self.client.post(f'/finance/payments/{payment.pk}/confirm/')

    def _status(self, payment):
        payment.refresh_from_db()
        return payment.status

    def test_recorder_cannot_confirm_own_payment(self):
        payment = self._payment(self.manager)
        resp = self._confirm_as(self.manager, payment)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._status(payment), PaymentRecord.STATUS_PENDING)
        self.assertFalse(
            JournalEntry.objects.for_source('PaymentRecord', payment.pk).exists(),
            'a refused confirmation must post nothing',
        )

    def test_another_user_can_confirm(self):
        payment = self._payment(self.staff)
        self._confirm_as(self.manager, payment)
        self.assertEqual(self._status(payment), PaymentRecord.STATUS_CONFIRMED)
        self.assertEqual(payment.confirmed_by, self.manager)

    def test_admin_self_confirm_is_allowed_and_logged(self):
        payment = self._payment(self.admin)
        self._confirm_as(self.admin, payment)
        self.assertEqual(self._status(payment), PaymentRecord.STATUS_CONFIRMED)
        log = PaymentLog.objects.get(payment=payment, action=PaymentLog.ACTION_CONFIRMED)
        self.assertIn('pencatatnya sendiri', log.note)
