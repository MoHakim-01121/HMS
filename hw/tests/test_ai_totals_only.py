"""Ask AI: only totals reach the model provider, never a name or document number."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hw import ai
from hw.models import ConfirmationLetter, Invoice
from hw.models.confirmation import ReservationStatus
from hw.tests.factories import make_cl, make_client, make_hotel_line, make_invoice


class TotalsOnlyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('rina', password='x')
        self.today = timezone.localdate()
        client = make_client(name='PT Rahasia Klien')
        self.cl = make_cl(client=client, guest_name='Zubair Tamu', hotel_name='Hotel Rahasia',
                          confirmation_number='77123', check_in=self.today + timedelta(days=2),
                          check_out=self.today + timedelta(days=4))
        self.inv = make_invoice(client=client, customer_name='PT Rahasia Klien', invoice_number='INV-7712')
        make_hotel_line(self.inv, total_sar=1000)

    def _sent(self, history=None):
        with mock.patch.object(ai, '_call_groq', return_value='ok') as call:
            ai.get_chat_reply('invoice belum lunas?', history=history, user=self.user)
        return call.call_args.args[0][0]['content']

    def test_no_name_or_document_number_is_sent(self):
        sent = self._sent()
        for secret in ('PT Rahasia Klien', 'Zubair', 'Hotel Rahasia', '77123', 'INV-7712'):
            self.assertNotIn(secret, sent)

    def test_totals_are_sent(self):
        sent = self._sent()
        self.assertIn('Belum lunas: 1 invoice | sisa 1,000 SAR', sent)
        self.assertIn('Check-in 7 hari ke depan: 1 CL', sent)

    def test_void_invoices_and_cancelled_cls_do_not_count(self):
        Invoice.objects.filter(pk=self.inv.pk).update(status=Invoice.STATUS_VOID, voided_at=timezone.now())
        ConfirmationLetter.objects.update(reservation_status=ReservationStatus.CANCELLED)
        sent = self._sent()
        self.assertIn('Invoice Hotel: 0 invoice', sent)
        self.assertIn('Confirmation Letter aktif: 0 CL', sent)
