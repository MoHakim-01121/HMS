"""Edit transfer setoran: hanya data transfernya; alokasi diatur per penerimaan."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting, queries as fq
from hw.finance_helpers import create_payment_record
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_cash, make_hotel_line, make_invoice, make_remittance, make_remittance_line


class RemittanceEditViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('editor', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(name="2026", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.invoice = make_invoice(invoice_type='hotel', invoice_number='INV-EDIT-003', customer_name='Budi')
        r1 = make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=10000)
        rec = create_payment_record(
            invoice=self.invoice, client=self.invoice.client, payment_date=date(2026, 1, 5), amount=5000,
            method='cash', created_by=self.user, received_in='sby', reservation=r1,
        )
        posting.post_payment(rec, created_by=self.user)
        self.rem = make_remittance(date=date(2026, 1, 10), remittance_number='RMT-E20', amount_sent=4_750_000)
        fund_cash(self.rem.from_account, 100_000_000)
        posting.resync_remittance(self.rem, created_by=self.user)

    def test_form_has_no_editable_lines(self):
        resp = self.client.get(f'/remittance/{self.rem.pk}/edit/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual((props['lines'], props['reservasi'], props['lines_editable']), ([], [], False))

    def test_post_updates_transfer_and_resyncs_the_send_leg(self):
        resp = self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-12', 'receipt_reference': 'REF-9', 'note': 'revisi',
            'amount_idr': '9500000', 'exchange_rate': '4750',
        })
        self.assertEqual(resp.status_code, 302)
        self.rem.refresh_from_db()
        self.assertEqual((str(self.rem.date), self.rem.receipt_reference, self.rem.expected_sar),
                         ('2026-01-12', 'REF-9', 2000))
        self.assertEqual(fq.remittance_sent_sar(self.rem.pk), 2000)

    def test_amount_is_locked_once_hq_recorded_a_receipt(self):
        make_remittance_line(remittance=self.rem, invoice=self.invoice, linked_number='R1', amount_sar=500)
        self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-10', 'receipt_reference': '', 'note': '', 'amount_idr': '1', 'exchange_rate': '1',
        })
        self.rem.refresh_from_db()
        self.assertEqual(self.rem.amount_sent, 4_750_000)
        self.assertEqual([l.linked_number for l in self.rem.lines], ['R1'])

    def _send_entry_dates(self):
        from hw.models.journal import JournalEntry
        return [e.entry_date for e in JournalEntry.objects.for_source('Remittance', self.rem.pk)
                .filter(entry_type=JournalEntry.TYPE_REMITTANCE).live()]

    def test_a_corrected_date_moves_the_send_leg(self):
        self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-02-03', 'receipt_reference': '', 'note': '',
        })
        self.assertEqual(self._send_entry_dates(), [date(2026, 2, 3)])

    def test_edit_is_refused_whole_when_the_ledger_cannot_follow(self):
        # Januari ditutup: jurnal kirim lama tidak bisa dibalik, jadi
        # dokumennya juga tidak boleh berubah sendirian.
        FinancialPeriod.objects.filter(name="2026").update(
            date_to=date(2026, 1, 31), status=FinancialPeriod.STATUS_CLOSED)
        FinancialPeriod.objects.create(name="Feb-Des", date_from=date(2026, 2, 1), date_to=date(2026, 12, 31))
        resp = self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-02-03', 'receipt_reference': 'REF-X', 'note': '',
        })
        self.assertRedirects(resp, f'/remittance/{self.rem.pk}/edit/', fetch_redirect_response=False)
        self.rem.refresh_from_db()
        self.assertEqual((self.rem.date, self.rem.receipt_reference), (date(2026, 1, 10), ''))
        self.assertEqual(self._send_entry_dates(), [date(2026, 1, 10)])

    def test_an_invalid_proof_is_a_message_not_a_server_error(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
        for url in (f'/remittance/{self.rem.pk}/edit/', f'/remittance/{self.rem.pk}/upload-proof/'):
            resp = self.client.post(url, {'date': '2026-01-10', 'proof': bad})
            self.assertEqual(resp.status_code, 302, url)
            bad.seek(0)
        self.rem.refresh_from_db()
        self.assertFalse(self.rem.proof)
