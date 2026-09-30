"""Alokasi remittance ke reservasi SAAT PUSAT MENERIMA (bukan saat kirim).

Alur: transfer lump-sum (IDR + kurs) keluar dari Kas SBY tanpa dimensi
reservasi; setiap RemittanceSettlement membawa alokasinya sendiri
(RemittanceLine.settlement). Alokasi dijurnal sebagai reklasifikasi Kas SBY
bertanggal penerimaan -- jurnal kirim tidak pernah diposting ulang, jadi
periode bulan transfer yang sudah ditutup tidak menghalangi alokasi.

Skenario utama = simulasi yang disetujui user 2026-09-17:
  a tagihan 32.000 lunas · b tagihan 15.000 dibayar 9.000 · c 9.000 lunas
  kirim 240.000.000 IDR @ 4.800 = 50.000 SAR
  terima 40.000 → a 32.000 + c 8.000 (b ditahan, belum lunas)
  terima 10.000 → c 1.000 + b 9.000
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import posting
from hw.finance import remittance_allocation as ra
from hw.finance import settlement_service as svc
from hw.finance.errors import FinanceError
from hw.finance_helpers import create_payment_record
from hw.management.commands.check_finance import Command as CheckFinance
from hw.models import Client, Remittance, RemittanceLine
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.models.settlement import RemittanceSettlement
from hw.tests.factories import make_hotel_line, make_invoice


def _net(account_id):
    agg = JournalLine.objects.filter(account_id=account_id).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or 0) - (agg['c'] or 0)


class AllocationBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alloc', password='pw12345')
        self.period = FinancialPeriod.objects.create(
            name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Amanah')
        self.invoice = make_invoice(
            invoice_type='hotel', invoice_number='INV-ALC-001', customer_name='PT Amanah',
            client=self.client_obj,
        )
        self.a = self._res('A', 32000, date(2026, 9, 18))
        self.b = self._res('B', 15000, date(2026, 9, 25))
        self.c = self._res('C', 9000, date(2026, 9, 20))
        self._pay(self.a, 32000)
        self._pay(self.b, 9000)
        self._pay(self.c, 9000)
        self.rem = self._transfer(240_000_000, 4800, date(2026, 9, 10))

    def _res(self, number, total, check_in):
        return make_hotel_line(
            invoice=self.invoice, reservation_number=number, total_sar=total, check_in=check_in,
        )

    def _pay(self, res, amount, pay_date=date(2026, 9, 1)):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=pay_date,
            amount=amount, method='transfer', created_by=self.user,
            received_in='sby', reservation=res,
        )
        posting.post_payment(p, created_by=self.user)

    def _transfer(self, idr, rate, when, number='RMT-ALC-1'):
        rem = Remittance.objects.create(
            remittance_number=number, date=when, amount_idr=idr, exchange_rate=rate,
        )
        posting.resync_remittance(rem, created_by=self.user, send_segments=[])
        return rem

    def _receive(self, amount, when, allocations, rem=None):
        return svc.add_settlement(
            rem or self.rem, received_amount_sar=amount, received_date=when,
            created_by=self.user, allocations=allocations,
        )

    def _idle(self):
        return {r['linked_number']: r['mengendap'] for r in ra.build_reservasi_mengendap()}


class SimulationScenarioTest(AllocationBase):
    def test_transfer_first_then_allocate_on_each_receipt(self):
        self.assertEqual(_net(coa.TRANSIT), 50000)
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(self._idle(), {'A': 32000, 'B': 9000, 'C': 9000})

        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self.rem.refresh_from_db()
        self.assertEqual(_net(coa.TRANSIT), 10000)
        self.assertEqual(_net(coa.CASH_PUSAT), 40000)
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(self.rem.status, Remittance.STATUS_PENDING)
        self.assertEqual(self._idle(), {'A': 0, 'B': 9000, 'C': 1000})
        self.assertEqual(self.rem.allocated_sar, 40000)
        self.assertEqual(self.rem.unallocated_sar, 10000)

        self._receive(10000, date(2026, 9, 15), [
            {'linked_number': 'C', 'amount_sar': 1000},
            {'linked_number': 'B', 'amount_sar': 9000},
        ])
        self.rem.refresh_from_db()
        self.assertEqual(_net(coa.TRANSIT), 0)
        self.assertEqual(_net(coa.CASH_PUSAT), 50000)
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(self.rem.status, Remittance.STATUS_RECEIVED)
        self.assertEqual(self._idle(), {'A': 0, 'B': 0, 'C': 0})
        self.assertEqual(self.rem.unallocated_sar, 0)

    def test_send_entry_is_never_reposted(self):
        self._receive(40000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 32000}])
        self.assertFalse(JournalEntry.objects.filter(is_reversal=True).exists())
        send = JournalEntry.objects.filter(reference_type='Remittance', reference_id=self.rem.pk)
        self.assertEqual(send.count(), 1)

    def test_allocation_lines_belong_to_their_receipt(self):
        s1 = self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self.assertEqual(
            {(l.linked_number, l.amount_sar, l.invoice_id) for l in s1.allocations.all()},
            {('A', 32000, self.invoice.pk), ('C', 8000, self.invoice.pk)},
        )

    def test_receipt_without_allocations_is_still_allowed(self):
        self._receive(40000, date(2026, 9, 12), None)
        self.rem.refresh_from_db()
        self.assertEqual(self.rem.allocated_sar, 0)
        self.assertEqual(self._idle(), {'A': 32000, 'B': 9000, 'C': 9000})

    def test_finance_check_stays_clean(self):
        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self.assertEqual(CheckFinance()._remittance_line_mismatch(), [])


class SuggestionTest(AllocationBase):
    def test_paid_in_full_first_then_nearest_check_in(self):
        rows = ra.candidates(self.rem)
        self.assertEqual([r['linked_number'] for r in rows], ['A', 'C', 'B'])
        self.assertEqual([r['paid_in_full'] for r in rows], [True, True, False])

    def test_suggest_matches_simulation(self):
        self.assertEqual(ra.suggest(ra.candidates(self.rem), 40000), {'A': 32000, 'C': 8000})

    def test_candidates_skip_reservations_without_idle_money(self):
        self._res('D', 5000, date(2026, 9, 19))
        self.assertNotIn('D', [r['linked_number'] for r in ra.candidates(self.rem)])


class ValidationTest(AllocationBase):
    def test_rejects_more_than_client_money_ready(self):
        with self.assertRaises(FinanceError):
            self._receive(40000, date(2026, 9, 12), [{'linked_number': 'B', 'amount_sar': 12000}])
        self.assertFalse(RemittanceSettlement.objects.exists())
        self.assertEqual(_net(coa.TRANSIT), 50000)

    def test_rejects_more_than_transfer_total(self):
        d = self._res('D', 10000, date(2026, 9, 19))
        self._pay(d, 10000)
        with self.assertRaises(FinanceError):
            self._receive(50000, date(2026, 9, 12), [
                {'linked_number': 'A', 'amount_sar': 32000},
                {'linked_number': 'B', 'amount_sar': 9000},
                {'linked_number': 'C', 'amount_sar': 9000},
                {'linked_number': 'D', 'amount_sar': 2000},
            ])
        self.assertFalse(RemittanceSettlement.objects.exists())

    def test_rejects_reservation_without_idle_money(self):
        self._res('D', 5000, date(2026, 9, 19))
        with self.assertRaises(FinanceError):
            self._receive(40000, date(2026, 9, 12), [{'linked_number': 'D', 'amount_sar': 1000}])

    def test_rejects_allocation_on_remittance_without_amount_idr(self):
        legacy = Remittance.objects.create(remittance_number='RMT-ALC-OLD', date=date(2026, 9, 10))
        with self.assertRaises(FinanceError):
            self._receive(1000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 1000}], rem=legacy)

    def test_zero_amounts_are_ignored(self):
        s1 = self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'B', 'amount_sar': 0},
        ])
        self.assertEqual([l.linked_number for l in s1.allocations.all()], ['A'])


class ShortfallTest(AllocationBase):
    def test_last_receipt_may_allocate_more_than_received_then_close_diff(self):
        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self._receive(9850, date(2026, 9, 15), [
            {'linked_number': 'C', 'amount_sar': 1000},
            {'linked_number': 'B', 'amount_sar': 9000},
        ])
        self.assertEqual(_net(coa.TRANSIT), 150)
        svc.close_remittance_diff(self.rem, created_by=self.user, entry_date=date(2026, 9, 16))
        self.rem.refresh_from_db()
        self.assertEqual(_net(coa.TRANSIT), 0)
        self.assertEqual(_net(coa.EXP_BANKFEE), 150)
        self.assertEqual(self.rem.status, Remittance.STATUS_RECEIVED)
        self.assertEqual(self._idle(), {'A': 0, 'B': 0, 'C': 0})


class CorrectionTest(AllocationBase):
    def setUp(self):
        super().setUp()
        self.s1 = self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])

    def test_reallocate_receipt(self):
        svc.set_settlement_allocations(self.s1, [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'B', 'amount_sar': 8000},
        ], created_by=self.user, entry_date=date(2026, 9, 13))
        self.assertEqual(self._idle(), {'A': 0, 'B': 1000, 'C': 9000})
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(_net(coa.TRANSIT), 10000)
        self.assertEqual(sorted(l.linked_number for l in self.s1.allocations.all()), ['A', 'B'])

    def test_own_allocation_counts_as_available_when_correcting(self):
        svc.set_settlement_allocations(self.s1, [
            {'linked_number': 'A', 'amount_sar': 31000},
            {'linked_number': 'C', 'amount_sar': 9000},
        ], created_by=self.user, entry_date=date(2026, 9, 13))
        self.assertEqual(self._idle(), {'A': 1000, 'B': 9000, 'C': 0})

    def test_invalid_correction_keeps_previous_allocation(self):
        with self.assertRaises(FinanceError):
            svc.set_settlement_allocations(self.s1, [
                {'linked_number': 'B', 'amount_sar': 12000},
            ], created_by=self.user, entry_date=date(2026, 9, 13))
        self.assertEqual(self._idle(), {'A': 0, 'B': 9000, 'C': 1000})

    def test_clearing_allocations_restores_idle_money(self):
        svc.set_settlement_allocations(self.s1, [], created_by=self.user, entry_date=date(2026, 9, 13))
        self.assertEqual(self._idle(), {'A': 32000, 'B': 9000, 'C': 9000})
        self.assertFalse(RemittanceLine.objects.exists())


class ClosedTransferPeriodTest(TestCase):
    """Transfer akhir September, periode September ditutup, uang diterima
    Oktober: alokasi tetap bisa karena dijurnal di tanggal penerimaan."""

    def test_allocation_after_transfer_period_closed(self):
        user = User.objects.create_user('alloc2', password='pw12345')
        sept = FinancialPeriod.objects.create(
            name='2026-09', date_from=date(2026, 9, 1), date_to=date(2026, 9, 30),
        )
        FinancialPeriod.objects.create(
            name='2026-10', date_from=date(2026, 10, 1), date_to=date(2026, 10, 31),
        )
        client_obj = Client.objects.create(name='PT Rawda')
        invoice = make_invoice(
            invoice_type='hotel', invoice_number='INV-ALC-002', customer_name='PT Rawda', client=client_obj,
        )
        res = make_hotel_line(invoice=invoice, reservation_number='R9', total_sar=4800)
        p = create_payment_record(
            invoice=invoice, client=client_obj, payment_date=date(2026, 9, 2), amount=4800,
            method='transfer', created_by=user, received_in='sby', reservation=res,
        )
        posting.post_payment(p, created_by=user)
        rem = Remittance.objects.create(
            remittance_number='RMT-ALC-9', date=date(2026, 9, 28), amount_idr=23_040_000, exchange_rate=4800,
        )
        posting.resync_remittance(rem, created_by=user, send_segments=[])
        sept.status = FinancialPeriod.STATUS_CLOSED
        sept.save(update_fields=['status'])

        svc.add_settlement(
            rem, received_amount_sar=4800, received_date=date(2026, 10, 2), created_by=user,
            allocations=[{'linked_number': 'R9', 'amount_sar': 4800}],
        )
        rows = {r['linked_number']: r['mengendap'] for r in ra.build_reservasi_mengendap()}
        self.assertEqual(rows['R9'], 0)


class TransferPositionTest(AllocationBase):
    def test_parts_always_add_up_to_unallocated(self):
        pos = ra.transfer_position(self.rem)
        self.assertEqual((pos['in_transit'], pos['received_unallocated'], pos['fee']), (50000, 0, 0))

        s1 = self._receive(40000, date(2026, 9, 12), None)
        self.rem.refresh_from_db()
        pos = ra.transfer_position(self.rem)
        self.assertEqual((pos['in_transit'], pos['received_unallocated'], pos['fee']), (10000, 40000, 0))
        self.assertEqual([t['remittance_number'] for t in ra.open_transfers()], ['RMT-ALC-1'])

        svc.set_settlement_allocations(s1, [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ], created_by=self.user, entry_date=date(2026, 9, 13))
        self.rem.refresh_from_db()
        pos = ra.transfer_position(self.rem)
        self.assertEqual((pos['in_transit'], pos['received_unallocated'], pos['fee']), (10000, 0, 0))

    def test_unallocated_remainder_after_closed_diff_is_fee(self):
        self._receive(49850, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'B', 'amount_sar': 9000},
            {'linked_number': 'C', 'amount_sar': 8850},
        ])
        svc.close_remittance_diff(self.rem, created_by=self.user, entry_date=date(2026, 9, 13))
        self.rem.refresh_from_db()
        pos = ra.transfer_position(self.rem)
        self.assertEqual((pos['in_transit'], pos['received_unallocated'], pos['fee']), (0, 0, 150))
        self.assertEqual(ra.open_transfers(), [])


class ReceiptViewTest(AllocationBase):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        self.url = f'/remittance/{self.rem.pk}/receipt/'

    def _page(self, url):
        return self.client.get(url, HTTP_X_INERTIA='true').json()

    def _post_json(self, url, body, **extra):
        return self.client.post(url, data=json.dumps(body), content_type='application/json', **extra)

    def test_form_offers_candidates_in_fill_order(self):
        page = self._page(self.url + '?next=/remittance/')
        self.assertEqual(page['component'], 'Remittance/Receipt')
        props = page['props']
        self.assertEqual([c['linked_number'] for c in props['candidates']], ['A', 'C', 'B'])
        b = props['candidates'][2]
        self.assertEqual((b['paid_sar'], b['total_sar'], b['paid_in_full']), (9000, 15000, False))
        self.assertEqual(props['rem']['remaining_to_allocate'], 50000)
        self.assertEqual(props['form']['received_amount_sar'], 50000)
        self.assertEqual(props['next'], '/remittance/')

    def test_post_with_allocations(self):
        resp = self._post_json(self.url, {
            'received_amount_sar': '40000', 'received_date': '2026-09-12', 'next': '/remittance/',
            'allocations': [
                {'linked_number': 'A', 'invoice_id': self.invoice.pk, 'amount_sar': 32000},
                {'linked_number': 'C', 'invoice_id': self.invoice.pk, 'amount_sar': 8000},
            ],
        })
        self.assertRedirects(resp, '/remittance/', fetch_redirect_response=False)
        self.assertEqual(self._idle(), {'A': 0, 'B': 9000, 'C': 1000})

    def test_invalid_allocation_returns_form_with_input_and_error(self):
        resp = self._post_json(self.url, {
            'received_amount_sar': '40000', 'received_date': '2026-09-12',
            'allocations': [{'linked_number': 'B', 'invoice_id': self.invoice.pk, 'amount_sar': 12000}],
        }, HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        page = resp.json()
        self.assertEqual(page['component'], 'Remittance/Receipt')
        self.assertIn('B', page['props']['error'])
        self.assertEqual(page['props']['form']['allocations'][0]['amount_sar'], 12000)
        self.assertFalse(RemittanceSettlement.objects.exists())

    def test_form_redirects_when_remittance_already_received(self):
        self.rem.status = Remittance.STATUS_RECEIVED
        self.rem.save(update_fields=['status'])
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_reallocation_form_and_post(self):
        s1 = self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        url = f'/remittance/{self.rem.pk}/receipt/{s1.pk}/allocation/'
        props = self._page(url)['props']
        self.assertEqual(props['settlement']['id'], s1.pk)
        self.assertEqual({a['linked_number'] for a in props['form']['allocations']}, {'A', 'C'})
        c = next(x for x in props['candidates'] if x['linked_number'] == 'C')
        self.assertEqual((c['current'], c['available']), (8000, 9000))

        resp = self._post_json(url, {
            'next': f'/remittance/{self.rem.pk}/',
            'allocations': [
                {'linked_number': 'A', 'invoice_id': self.invoice.pk, 'amount_sar': 32000},
                {'linked_number': 'B', 'invoice_id': self.invoice.pk, 'amount_sar': 8000},
            ],
        })
        self.assertRedirects(resp, f'/remittance/{self.rem.pk}/', fetch_redirect_response=False)
        self.assertEqual(self._idle(), {'A': 0, 'B': 1000, 'C': 9000})

    def test_detail_groups_allocations_under_their_receipt(self):
        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        props = self._page(f'/remittance/{self.rem.pk}/')['props']
        self.assertEqual(props['lines'], [])
        receipt = props['rem']['settlements'][0]
        self.assertEqual([a['linked_number'] for a in receipt['allocations']], ['A', 'C'])
        self.assertEqual(receipt['allocations'][0]['check_in'], '18/09/2026')
        self.assertTrue(props['rem']['can_allocate'])
        self.assertEqual(props['rem']['position']['in_transit'], 10000)

    def test_new_transfer_form_warns_about_open_transfers(self):
        props = self._page('/remittance/new/')['props']
        self.assertEqual(props['open_transfers'][0]['in_transit'], 50000)


class TrackingDataTest(AllocationBase):
    def _tracking(self):
        from hw.views.remittance_views import _compute_tracking_data
        return _compute_tracking_data()

    def test_bridge_matches_simulation_after_first_receipt(self):
        self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        data = self._tracking()
        self.assertEqual(data['summary'], {
            'client_unallocated': 10000, 'in_transit': 10000,
            'received_unallocated': 0, 'fee': 0, 'still_sby': 0,
        })
        rows = {r['linked_number']: r for r in data['reservations']}
        self.assertEqual(rows['B']['unallocated'], 9000)
        self.assertEqual((rows['B']['paid_sar'], rows['B']['total_sar']), (9000, 15000))
        self.assertEqual(
            [(h['kind'], h['date'], h['amount_sar']) for h in rows['C']['history']],
            [('receipt', '12/09/2026', 8000)],
        )
        self.assertEqual(data['pending_allocations'], [])

    def test_received_but_unallocated_is_listed_as_pending(self):
        s1 = self._receive(40000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 32000}])
        data = self._tracking()
        self.assertEqual(data['summary']['received_unallocated'], 8000)
        self.assertEqual(data['summary']['still_sby'], 0)
        self.assertEqual(
            [(p['settlement_id'], p['amount_sar']) for p in data['pending_allocations']],
            [(s1.pk, 8000)],
        )


class SendSegmentsTest(AllocationBase):
    def test_receipt_allocations_are_not_send_segments(self):
        self._receive(40000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 32000}])
        self.assertEqual(ra.send_segments(self.rem), [])
        posting.resync_remittance(self.rem, created_by=self.user, send_segments=ra.send_segments(self.rem))
        self.assertEqual(self._idle()['A'], 0)
        self.assertEqual(_net(coa.TRANSIT), 10000)

    def test_resync_keeps_unallocated_remainder_of_lump_sum(self):
        """Regresi: segmen sebagian dulu mengganti seluruh jurnal kirim, jadi
        sisa yang masih di jalan tercatat seolah kembali ke Kas SBY."""
        posting.resync_remittance(self.rem, created_by=self.user, send_segments=[
            {'reservation': self.a, 'invoice': self.invoice, 'client': self.client_obj, 'amount_sar': 32000},
        ])
        self.assertEqual(_net(coa.TRANSIT), 50000)
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(self.rem.settlement_basis_sar, 50000)
