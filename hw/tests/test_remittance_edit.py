import json
from datetime import date

from django.test import TestCase

from hw.models import Invoice, Payment, Remittance, RemittanceLine, Reservation
from hw.views.remittance_views import _addable_reservasi, _sync_remittance_lines


class SyncRemittanceLinesTest(TestCase):
    """Edit remittance: ubah nominal, tambah reservasi, hapus baris."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-EDIT-001', customer_name='Budi',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=10000)
        Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=8000)
        self.rem = Remittance.objects.create(company='konoz', date=date(2026, 1, 10), remittance_number='RMT-E01')
        self.line = RemittanceLine.objects.create(
            remittance=self.rem, invoice=self.invoice, linked_number='R1', amount_sar=2000,
        )

    def _lines(self):
        return {l.linked_number: int(l.amount_sar) for l in self.rem.lines.all()}

    def test_update_existing_amount(self):
        _sync_remittance_lines(self.rem, [{'line_id': self.line.pk, 'amount_sar': 3500}])
        self.assertEqual(self._lines(), {'R1': 3500})

    def test_add_new_reservation(self):
        _sync_remittance_lines(self.rem, [
            {'line_id': self.line.pk, 'amount_sar': 2000},
            {'linked_number': 'R2', 'invoice_id': self.invoice.pk, 'amount_sar': 1500},
        ])
        self.assertEqual(self._lines(), {'R1': 2000, 'R2': 1500})
        self.assertEqual(self.rem.lines.get(linked_number='R2').invoice_id, self.invoice.pk)

    def test_line_missing_from_payload_is_deleted(self):
        RemittanceLine.objects.create(remittance=self.rem, invoice=self.invoice, linked_number='R2', amount_sar=900)
        _sync_remittance_lines(self.rem, [{'line_id': self.line.pk, 'amount_sar': 2000}])
        self.assertEqual(self._lines(), {'R1': 2000})

    def test_zero_amount_deletes_the_line(self):
        _sync_remittance_lines(self.rem, [{'line_id': self.line.pk, 'amount_sar': 0}])
        self.assertEqual(self._lines(), {})

    def test_new_line_with_zero_amount_is_ignored(self):
        _sync_remittance_lines(self.rem, [
            {'line_id': self.line.pk, 'amount_sar': 2000},
            {'linked_number': 'R2', 'invoice_id': self.invoice.pk, 'amount_sar': 0},
        ])
        self.assertEqual(self._lines(), {'R1': 2000})

    def test_garbage_amount_is_treated_as_zero(self):
        _sync_remittance_lines(self.rem, [{'line_id': self.line.pk, 'amount_sar': 'abc'}])
        self.assertEqual(self._lines(), {})

    def test_cannot_touch_line_of_another_remittance(self):
        other = Remittance.objects.create(company='konoz', date=date(2026, 1, 11), remittance_number='RMT-E02')
        foreign = RemittanceLine.objects.create(remittance=other, invoice=self.invoice, linked_number='R2', amount_sar=700)
        _sync_remittance_lines(self.rem, [{'line_id': foreign.pk, 'amount_sar': 9999}])
        foreign.refresh_from_db()
        self.assertEqual(int(foreign.amount_sar), 700)   # milik remittance lain, tidak ikut berubah
        self.assertEqual(self._lines(), {})              # dan tidak diklaim jadi baris di sini


class AddableReservasiTest(TestCase):
    """Daftar reservasi yang bisa ditambahkan ke sebuah remittance."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-EDIT-002', customer_name='Budi',
        )
        Reservation.objects.create(
            invoice=self.invoice, reservation_number='R1', total_sar=10000,
            check_in=date(2026, 3, 1), check_out=date(2026, 3, 5),
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=8000)
        self.rem = Remittance.objects.create(company='konoz', date=date(2026, 1, 10), remittance_number='RMT-E10')

    def _pay(self, res, amount, method='cash'):
        Payment.objects.create(
            invoice=self.invoice, linked_number=res, amount=amount, currency='SAR',
            exchange_rate=1, method=method, payment_date=date(2026, 1, 5),
        )

    def test_lists_reservation_with_idle_money(self):
        self._pay('R1', 5000)
        rows = _addable_reservasi(self.rem)
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['mengendap'], 5000)
        self.assertEqual(rows[0]['check_in'], '01/03/2026')
        self.assertEqual(rows[0]['customer_name'], 'Budi')

    def test_excludes_reservation_already_in_this_remittance(self):
        self._pay('R1', 5000)
        self._pay('R2', 3000)
        RemittanceLine.objects.create(remittance=self.rem, invoice=self.invoice, linked_number='R1', amount_sar=1000)
        self.assertEqual([r['linked_number'] for r in _addable_reservasi(self.rem)], ['R2'])

    def test_excludes_reservation_already_fully_sent(self):
        self._pay('R1', 5000)
        other = Remittance.objects.create(company='konoz', date=date(2026, 1, 9), remittance_number='RMT-E11')
        RemittanceLine.objects.create(remittance=other, invoice=self.invoice, linked_number='R1', amount_sar=5000)
        self.assertEqual(_addable_reservasi(self.rem), [])

    def test_direct_payment_is_not_addable(self):
        self._pay('R1', 5000, method='direct')
        self.assertEqual(_addable_reservasi(self.rem), [])


class RemittanceEditViewTest(TestCase):
    """Alur penuh lewat HTTP: buka form edit lalu simpan perubahan."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('editor', password='pw12345')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()

        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-EDIT-003', customer_name='Budi',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=10000)
        Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=8000)
        for res, amount in (('R1', 5000), ('R2', 3000)):
            Payment.objects.create(
                invoice=self.invoice, linked_number=res, amount=amount, currency='SAR',
                exchange_rate=1, method='cash', payment_date=date(2026, 1, 5),
            )
        self.rem = Remittance.objects.create(company='konoz', date=date(2026, 1, 10), remittance_number='RMT-E20')
        self.line = RemittanceLine.objects.create(
            remittance=self.rem, invoice=self.invoice, linked_number='R1', amount_sar=2000,
        )

    def test_form_offers_reservations_that_can_be_added(self):
        resp = self.client.get(f'/remittance/{self.rem.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertEqual([l['linked_number'] for l in props['lines']], ['R1'])
        self.assertEqual([r['linked_number'] for r in props['reservasi']], ['R2'])
        self.assertEqual(props['reservasi'][0]['mengendap'], 3000)

    def test_post_adds_removes_and_updates_in_one_save(self):
        payload = [
            {'linked_number': 'R2', 'invoice_id': self.invoice.pk, 'amount_sar': 1500},
        ]
        resp = self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-12',
            'status': 'pending',
            'receipt_reference': 'REF-9',
            'note': 'revisi',
            'lines': json.dumps(payload),
        })
        self.assertEqual(resp.status_code, 302)
        self.rem.refresh_from_db()
        self.assertEqual(str(self.rem.date), '2026-01-12')
        self.assertEqual(self.rem.receipt_reference, 'REF-9')
        # R1 dihapus karena tidak ada di payload, R2 ditambahkan
        self.assertEqual(
            {l.linked_number: int(l.amount_sar) for l in self.rem.lines.all()},
            {'R2': 1500},
        )

    def test_post_without_lines_key_keeps_existing_lines(self):
        resp = self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-12', 'status': 'pending', 'receipt_reference': '', 'note': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual([l.linked_number for l in self.rem.lines.all()], ['R1'])

    def test_received_remittance_can_still_be_opened_and_saved(self):
        self.rem.status = 'received'
        self.rem.save(update_fields=['status'])

        resp = self.client.get(f'/remittance/{self.rem.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)   # tidak lagi dilempar ke halaman detail
        self.assertEqual(resp.json()['props']['rem']['status'], 'received')

        resp = self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-12', 'status': 'received', 'receipt_reference': 'REF-KOREKSI', 'note': '',
            'lines': json.dumps([{'line_id': self.line.pk, 'amount_sar': 2500}]),
        })
        self.assertEqual(resp.status_code, 302)
        self.rem.refresh_from_db()
        self.assertEqual(self.rem.receipt_reference, 'REF-KOREKSI')
        self.assertEqual(self.rem.status, 'received')   # status tidak ikut ter-reset
        self.assertEqual(int(self.rem.lines.get().amount_sar), 2500)

    def test_received_remittance_can_be_reverted_to_pending(self):
        self.rem.status = 'received'
        self.rem.save(update_fields=['status'])
        self.client.post(f'/remittance/{self.rem.pk}/edit/', {
            'date': '2026-01-10', 'status': 'pending', 'receipt_reference': '', 'note': '',
        })
        self.rem.refresh_from_db()
        self.assertEqual(self.rem.status, 'pending')
