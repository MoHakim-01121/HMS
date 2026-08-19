import uuid
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase

from hw.models import (
    Client, Invoice, Reservation, ServiceItem, ConfirmationLetter, CancellationPenalty,
    Charge, Allocation, CashMovement,
    Account, ChargeReason, AllocationReason,
)
from hw import ledger


class LedgerTestBase(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Test')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-LEDGER-001', customer_name='PT Test',
        )
        self.r1 = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=10000)

    def charge(self, reservation, amount, reason=ChargeReason.INITIAL, date='2026-07-01', invoice=None):
        return Charge.objects.create(
            company='konoz', client=self.client_obj, date=date, amount_sar=amount, invoice=invoice or self.invoice,
            reservation=reservation, reason=reason,
        )

    def alloc(self, reservation, amount, reason=AllocationReason.INITIAL, date='2026-07-01', transfer_group=None, invoice=None):
        return Allocation.objects.create(
            company='konoz', client=self.client_obj, date=date, amount_sar=amount, invoice=invoice or self.invoice,
            reservation=reservation, reason=reason, transfer_group=transfer_group,
        )

    def mov(self, from_account, to_account, amount, date='2026-07-01', reservation_label=None,
            service_item_label=None, remittance=None, client=None, reverses=None, currency='SAR',
            exchange_rate=1, invoice=None):
        return CashMovement.objects.create(
            company='konoz', client=client or self.client_obj, date=date, invoice=invoice or self.invoice,
            from_account=from_account, to_account=to_account, amount=amount,
            currency=currency, exchange_rate=exchange_rate,
            reservation_label=reservation_label, service_item_label=service_item_label,
            remittance=remittance, reverses=reverses,
        )


class ChargeDerivedTest(LedgerTestBase):
    def test_tagihan_sums_charges_for_reservation(self):
        self.charge(self.r1, 10000)
        self.assertEqual(ledger.tagihan(self.r1), 10000)

    def test_tagihan_reflects_revision(self):
        self.charge(self.r1, 10000)
        self.charge(self.r1, -2000, reason=ChargeReason.REVISION)
        self.assertEqual(ledger.tagihan(self.r1), 8000)

    def test_terbayar_sums_allocations_for_reservation(self):
        self.alloc(self.r1, 6000)
        self.assertEqual(ledger.terbayar(self.r1), 6000)

    def test_piutang_is_tagihan_minus_terbayar(self):
        self.charge(self.r1, 10000)
        self.alloc(self.r1, 6000)
        self.assertEqual(ledger.piutang(self.r1), 4000)


class SaldoDanaTest(LedgerTestBase):
    def test_saldo_dana_is_client_cash_in_minus_allocated(self):
        self.charge(self.r1, 10000)
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.alloc(self.r1, 6000)
        self.assertEqual(ledger.saldo_dana(self.client_obj), 0)

    def test_saldo_dana_positive_when_client_cash_exceeds_allocation(self):
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.alloc(self.r1, 4000)
        self.assertEqual(ledger.saldo_dana(self.client_obj), 2000)

    def test_saldo_dana_reduced_by_refund(self):
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.alloc(self.r1, 4000)
        self.mov('sby', 'client', 2000, reservation_label=self.r1)
        self.assertEqual(ledger.saldo_dana(self.client_obj), 0)

    def test_piutang_klien_sums_across_reservations(self):
        self.charge(self.r1, 10000)
        self.alloc(self.r1, 6000)
        self.assertEqual(ledger.piutang_klien(self.client_obj), 4000)


class WalletTest(LedgerTestBase):
    def test_kas_surabaya_nets_in_and_out(self):
        self.mov('client', 'sby', 6000)
        self.mov('sby', 'pusat', 4000)
        self.assertEqual(ledger.kas_surabaya('konoz'), 2000)

    def test_kas_pusat_nets_in_and_out(self):
        self.mov('sby', 'pusat', 4000)
        self.mov('client', 'pusat', 1000)
        self.assertEqual(ledger.kas_pusat('konoz'), 5000)

    def test_selisih_kurs_nets_fx_movements(self):
        self.mov('sby', 'fx', 341)
        self.assertEqual(ledger.selisih_kurs('konoz'), 341)

    def test_mengendap_per_res_can_go_negative(self):
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.mov('sby', 'pusat', 8000, reservation_label=self.r1)
        # Surabaya kirim lebih dari yang pernah diterima untuk reservasi ini
        self.assertEqual(ledger.mengendap_per_res(self.r1), -2000)

    def test_mengendap_per_service_item_tracked_separately_from_reservations(self):
        # booking visa/servis lewat SBY juga harus terlacak mengendapnya,
        # terpisah dari reservasi hotel -- bukan cuma hilang dari perhitungan
        svc = ServiceItem.objects.create(invoice=self.invoice, name='Visa', qty=1, price=4432)
        self.mov('client', 'sby', 4432, service_item_label=svc)
        self.assertEqual(ledger.mengendap_per_service_item(svc), 4432)
        self.assertEqual(ledger.kas_surabaya('konoz'), 4432)

    def test_reservation_cash_breakdown_is_per_reservation_not_per_invoice(self):
        r2 = Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=5000)
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.mov('sby', 'pusat', 2000, reservation_label=self.r1)
        self.mov('client', 'pusat', 1000, reservation_label=r2)

        data = ledger.reservation_cash_breakdown('konoz')

        self.assertEqual(data[self.r1.id], {
            'terbayar_sby': 6000, 'terbayar_direct': 0, 'sudah_dikirim': 2000, 'mengendap': 4000,
        })
        self.assertEqual(data[r2.id], {
            'terbayar_sby': 0, 'terbayar_direct': 1000, 'sudah_dikirim': 1000, 'mengendap': 0,
        })

    def test_reservation_cash_breakdown_mengendap_can_go_negative(self):
        self.mov('client', 'sby', 2000, reservation_label=self.r1)
        self.mov('sby', 'pusat', 6000, reservation_label=self.r1)
        data = ledger.reservation_cash_breakdown('konoz')
        self.assertEqual(data[self.r1.id]['mengendap'], -4000)

    def test_kas_surabaya_converts_non_sar_currency_per_row(self):
        # dua pembayaran rupiah dengan kurs beda tidak boleh dijumlah mentah-mentah
        self.mov('client', 'sby', 21_000_000, currency='IDR', exchange_rate=4200)  # 5000 SAR
        self.mov('client', 'sby', 21_500_000, currency='IDR', exchange_rate=4300)  # 5000 SAR
        self.assertEqual(ledger.kas_surabaya('konoz'), 10000)


class InvoiceScopedTest(LedgerTestBase):
    """_invoice_stats (Fase 3) needs wallet/charge totals scoped to a page of
    invoices, not just by company -- CashMovement.invoice exists for this."""

    def setUp(self):
        super().setUp()
        self.other_invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-LEDGER-002', customer_name='PT Lain',
        )
        self.r2 = Reservation.objects.create(invoice=self.other_invoice, reservation_number='R2', total_sar=5000)

    def test_total_charge_scoped_to_invoice_ids_excludes_other_invoices(self):
        self.charge(self.r1, 10000)
        self.charge(self.r2, 5000, invoice=self.other_invoice)
        self.assertEqual(ledger.total_charge(invoice_ids=[self.invoice.id]), 10000)

    def test_client_paid_to_sums_only_client_originated_cash(self):
        self.mov('client', 'sby', 6000)
        self.mov('sby', 'pusat', 4000)  # not client-originated, must be excluded
        self.assertEqual(ledger.client_paid_to(Account.SBY, invoice_ids=[self.invoice.id]), 6000)

    def test_kas_surabaya_scoped_to_invoice_excludes_other_invoice_movements(self):
        self.mov('client', 'sby', 6000, invoice=self.invoice)
        self.mov('client', 'sby', 9000, invoice=self.other_invoice)
        self.assertEqual(ledger.kas_surabaya(invoice_ids=[self.invoice.id]), 6000)


class SurplusKewajibanTest(LedgerTestBase):
    def test_kewajiban_kirim_positive_when_allocated_cash_not_yet_sent(self):
        # tagihan + alokasi ada, tapi belum satu rupiah pun dikirim ke pusat
        self.charge(self.r1, 6000)
        self.mov('client', 'sby', 6000, reservation_label=self.r1)
        self.alloc(self.r1, 6000)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 6000)

    def test_kewajiban_kirim_negative_when_pusat_has_surplus(self):
        # meniru A2: lunas 10.000, dikirim & diterima pusat, lalu turun ke 8.000
        self.charge(self.r1, 10000)
        self.mov('client', 'sby', 10000, reservation_label=self.r1)
        self.alloc(self.r1, 10000)
        self.mov('sby', 'pusat', 10000, reservation_label=self.r1)
        self.charge(self.r1, -2000, reason=ChargeReason.REVISION)
        self.alloc(self.r1, -2000, reason=AllocationReason.REVISION)
        self.mov('sby', 'client', 2000, reservation_label=self.r1)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), -2000)

    def test_surplus_pusat_matches_negative_kewajiban(self):
        self.charge(self.r1, 10000)
        self.mov('client', 'sby', 10000, reservation_label=self.r1)
        self.alloc(self.r1, 10000)
        self.mov('sby', 'pusat', 10000, reservation_label=self.r1)
        self.charge(self.r1, -2000, reason=ChargeReason.REVISION)
        self.alloc(self.r1, -2000, reason=AllocationReason.REVISION)
        self.mov('sby', 'client', 2000, reservation_label=self.r1)
        self.assertEqual(ledger.surplus_pusat('konoz'), 2000)


class LampiranABase(TestCase):
    """Fixture-free base for Lampiran A scenarios -- each test builds its own
    clients/reservations so the numbers in the plan can be transcribed as-is."""

    def make_client(self, name):
        return Client.objects.create(company='konoz', name=name)

    def make_invoice(self, number):
        return Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number=number, customer_name=number,
        )

    def make_reservation(self, invoice, number, total_sar=0):
        return Reservation.objects.create(invoice=invoice, reservation_number=number, total_sar=total_sar)

    def make_service_item(self, invoice, name, price):
        return ServiceItem.objects.create(invoice=invoice, name=name, qty=1, price=price)

    def make_penalty(self, number, confirmation_number):
        cl = ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hotel', guest_name='Guest',
            confirmation_number=confirmation_number,
        )
        return CancellationPenalty.objects.create(
            cl=cl, penalty_number=number, cancellation_date='2026-07-18',
        )

    def charge(self, client, amount, reason=ChargeReason.INITIAL, date='2026-07-01',
               reservation=None, service_item=None, penalty=None):
        return Charge.objects.create(
            company='konoz', client=client, date=date, amount_sar=amount,
            reservation=reservation, service_item=service_item, penalty=penalty, reason=reason,
        )

    def alloc(self, client, amount, reason=AllocationReason.INITIAL, date='2026-07-01',
              reservation=None, service_item=None, penalty=None, transfer_group=None):
        return Allocation.objects.create(
            company='konoz', client=client, date=date, amount_sar=amount,
            reservation=reservation, service_item=service_item, penalty=penalty,
            reason=reason, transfer_group=transfer_group,
        )

    def mov(self, client, from_account, to_account, amount, date='2026-07-01', reservation_label=None,
            currency='SAR', exchange_rate=1, reverses=None, note=''):
        return CashMovement.objects.create(
            company='konoz', client=client, date=date,
            from_account=from_account, to_account=to_account, amount=amount,
            currency=currency, exchange_rate=exchange_rate,
            reservation_label=reservation_label, reverses=reverses, note=note,
        )

    def assert_identities(self, company, clients):
        """Empat identitas wajib dari spesifikasi 'Semua angka jadi turunan'."""
        kas_sby = ledger.kas_surabaya(company)
        kas_pusat = ledger.kas_pusat(company)
        fx = ledger.selisih_kurs(company)
        client_in = sum(
            m.amount_sar for m in CashMovement.objects.filter(company=company, from_account=Account.CLIENT)
        )
        client_out = sum(
            m.amount_sar for m in CashMovement.objects.filter(company=company, to_account=Account.CLIENT)
        )
        self.assertEqual(kas_sby + kas_pusat + fx, client_in - client_out)

        total_saldo_dana = sum(ledger.saldo_dana(c) for c in clients)
        total_alloc = sum(a.amount_sar for a in Allocation.objects.filter(company=company))
        self.assertEqual(total_saldo_dana, kas_sby + kas_pusat + fx - total_alloc)

        labeled_reservations = Reservation.objects.filter(
            pk__in=CashMovement.objects.filter(company=company, reservation_label__isnull=False)
            .values_list('reservation_label', flat=True).distinct()
        )
        labeled_service_items = ServiceItem.objects.filter(
            pk__in=CashMovement.objects.filter(company=company, service_item_label__isnull=False)
            .values_list('service_item_label', flat=True).distinct()
        )
        labeled_penalties = CancellationPenalty.objects.filter(
            pk__in=CashMovement.objects.filter(company=company, penalty_label__isnull=False)
            .values_list('penalty_label', flat=True).distinct()
        )
        total_mengendap = (
            sum(ledger.mengendap_per_res(r) for r in labeled_reservations)
            + sum(ledger.mengendap_per_service_item(s) for s in labeled_service_items)
            + sum(ledger.mengendap_per_penalty(p) for p in labeled_penalties)
        )
        self.assertEqual(total_mengendap, kas_sby)

        self.assertEqual(ledger.kewajiban_kirim_sby(company), kas_sby - total_saldo_dana)


class LampiranA1Test(LampiranABase):
    """Siklus penuh: revisi, pindah alokasi, batal+penalty, booking ulang, refund parsial."""

    def test_full_cycle(self):
        client = self.make_client('PT Barokah Wisata')
        invoice = self.make_invoice('INV-012')
        r101 = self.make_reservation(invoice, 'R-101', 12000)
        r102 = self.make_reservation(invoice, 'R-102', 8000)

        # 03/07 -- invoice terbit
        self.charge(client, 12000, date='2026-07-03', reservation=r101)
        self.charge(client, 8000, date='2026-07-03', reservation=r102)
        self.assert_identities('konoz', [client])

        # 05/07 -- transfer 18.000 ke SBY
        self.alloc(client, 12000, date='2026-07-05', reservation=r101)
        self.alloc(client, 6000, date='2026-07-05', reservation=r102)
        self.mov(client, 'client', 'sby', 12000, date='2026-07-05', reservation_label=r101)
        self.mov(client, 'client', 'sby', 6000, date='2026-07-05', reservation_label=r102)
        self.assert_identities('konoz', [client])

        # 08/07 kirim, 10/07 received -- RMT-007
        self.mov(client, 'sby', 'pusat', 12000, date='2026-07-10', reservation_label=r101)
        self.mov(client, 'sby', 'pusat', 3000, date='2026-07-10', reservation_label=r102)
        self.assert_identities('konoz', [client])

        # 12/07 -- R-101 kurang 2 malam: revisi -6.000, pindah alokasi R-101->R-102, sisa revisi turun
        self.charge(client, -6000, date='2026-07-12', reason=ChargeReason.REVISION, reservation=r101)
        t1 = uuid.uuid4()
        self.alloc(client, -2000, date='2026-07-12', reason=AllocationReason.TRANSFER, reservation=r101, transfer_group=t1)
        self.alloc(client, 2000, date='2026-07-12', reason=AllocationReason.TRANSFER, reservation=r102, transfer_group=t1)
        self.alloc(client, -4000, date='2026-07-12', reason=AllocationReason.REVISION, reservation=r101)
        self.assert_identities('konoz', [client])
        self.assertEqual(ledger.tagihan(r101), 6000)
        self.assertEqual(ledger.terbayar(r101), 6000)

        # 18/07 -- R-102 batal, penalty 1.500
        penalty = self.make_penalty('PNL-003', 'CL-A1')
        self.charge(client, -8000, date='2026-07-18', reason=ChargeReason.CANCELLATION, reservation=r102)
        self.charge(client, 1500, date='2026-07-18', reason=ChargeReason.CANCELLATION, penalty=penalty)
        self.alloc(client, -8000, date='2026-07-18', reason=AllocationReason.CANCELLATION, reservation=r102)
        self.alloc(client, 1500, date='2026-07-18', reason=AllocationReason.CANCELLATION, penalty=penalty)
        self.assert_identities('konoz', [client])
        self.assertEqual(ledger.piutang(r102), 0)

        # 22/07 -- booking ulang R-103
        r103 = self.make_reservation(invoice, 'R-103', 7000)
        self.charge(client, 7000, date='2026-07-22', reservation=r103)
        self.alloc(client, 7000, date='2026-07-22', reservation=r103)
        self.assert_identities('konoz', [client])

        # 25/07 -- refund sisa lewat SBY
        self.mov(client, 'sby', 'client', 3000, date='2026-07-25', reservation_label=r102)
        self.assert_identities('konoz', [client])

        # Assertion penutup
        self.assertEqual(ledger.kas_surabaya('konoz'), 0)
        self.assertEqual(ledger.kas_pusat('konoz'), 15000)
        total_charge = sum(c.amount_sar for c in Charge.objects.filter(company='konoz'))
        total_alloc = sum(a.amount_sar for a in Allocation.objects.filter(company='konoz'))
        self.assertEqual(total_charge, 14500)
        self.assertEqual(total_alloc, 14500)
        self.assertEqual(ledger.piutang_klien(client), 0)
        self.assertEqual(ledger.saldo_dana(client), 500)


class LampiranA2Test(LampiranABase):
    """Surabaya menalangi refund; kelebihan di pusat terpakai reservasi lain."""

    def test_sby_talangi_refund_kredit_terpakai(self):
        amanah = self.make_client('PT Amanah')
        inv_amanah = self.make_invoice('INV-A2-1')
        r201 = self.make_reservation(inv_amanah, 'R-201', 10000)

        # 01/08 booking
        self.charge(amanah, 10000, date='2026-08-01', reservation=r201)

        # 03/08, 07/08 -- bayar penuh
        self.alloc(amanah, 6000, date='2026-08-03', reservation=r201)
        self.mov(amanah, 'client', 'sby', 6000, date='2026-08-03', reservation_label=r201)
        self.alloc(amanah, 4000, date='2026-08-07', reservation=r201)
        self.mov(amanah, 'client', 'sby', 4000, date='2026-08-07', reservation_label=r201)
        self.assert_identities('konoz', [amanah])

        # 10/08 kirim, 12/08 received -- RMT-012
        self.mov(amanah, 'sby', 'pusat', 10000, date='2026-08-12', reservation_label=r201)
        self.assert_identities('konoz', [amanah])

        # 15/08 revisi turun ke 8.000
        self.charge(amanah, -2000, date='2026-08-15', reason=ChargeReason.REVISION, reservation=r201)
        self.alloc(amanah, -2000, date='2026-08-15', reason=AllocationReason.REVISION, reservation=r201)
        self.assert_identities('konoz', [amanah])

        # 18/08 SBY menalangi refund 2.000
        self.mov(amanah, 'sby', 'client', 2000, date='2026-08-18', reservation_label=r201)
        self.assert_identities('konoz', [amanah])

        self.assertEqual(ledger.saldo_dana(amanah), 0)
        self.assertEqual(ledger.kas_pusat('konoz'), 10000)
        self.assertEqual(sum(a.amount_sar for a in Allocation.objects.filter(company='konoz')), 8000)
        self.assertEqual(ledger.mengendap_per_res(r201), -2000)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), -2000)

        # Lanjutan: kredit -2.000 di R-201 terpakai untuk R-301
        salam = self.make_client('PT Salam')
        inv_salam = self.make_invoice('INV-A2-2')
        r301 = self.make_reservation(inv_salam, 'R-301', 5000)

        # 22/08 -- R-301 bayar penuh ke SBY
        self.charge(salam, 5000, date='2026-08-22', reservation=r301)
        self.alloc(salam, 5000, date='2026-08-22', reservation=r301)
        self.mov(salam, 'client', 'sby', 5000, date='2026-08-22', reservation_label=r301)
        self.assert_identities('konoz', [amanah, salam])

        # 25/08 -- RMT-013 kirim cuma 3.000 (Surabaya pakai kredit 2.000 dari R-201)
        self.mov(salam, 'sby', 'pusat', 3000, date='2026-08-25', reservation_label=r301)
        self.assert_identities('konoz', [amanah, salam])

        self.assertEqual(ledger.kas_surabaya('konoz'), 0)
        self.assertEqual(ledger.kas_pusat('konoz'), 13000)
        self.assertEqual(sum(a.amount_sar for a in Allocation.objects.filter(company='konoz')), 13000)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 0)
        self.assertEqual(ledger.mengendap_per_res(r201), -2000)
        self.assertEqual(ledger.mengendap_per_res(r301), 2000)
        self.assertEqual(ledger.mengendap_per_res(r201) + ledger.mengendap_per_res(r301), 0)


class LampiranA3Test(LampiranABase):
    """Extend setelah lunas, klien bayar lebih langsung ke pusat."""

    def test_extend_direct_to_pusat_surplus_milik_klien(self):
        hidayah = self.make_client('PT Hidayah')
        invoice = self.make_invoice('INV-A3')
        r401 = self.make_reservation(invoice, 'R-401', 9000)

        self.charge(hidayah, 9000, date='2026-09-01', reservation=r401)
        self.alloc(hidayah, 9000, date='2026-09-03', reservation=r401)
        self.mov(hidayah, 'client', 'sby', 9000, date='2026-09-03', reservation_label=r401)
        self.mov(hidayah, 'sby', 'pusat', 9000, date='2026-09-05', reservation_label=r401)
        self.assert_identities('konoz', [hidayah])

        # 10/09 -- extend 2 malam
        self.charge(hidayah, 6000, date='2026-09-10', reason=ChargeReason.REVISION, reservation=r401)
        self.assert_identities('konoz', [hidayah])

        # 12/09 -- klien transfer 7.000 langsung ke pusat, hanya 6.000 yang teralokasi (piutang R-401)
        self.alloc(hidayah, 6000, date='2026-09-12', reservation=r401)
        self.mov(hidayah, 'client', 'pusat', 7000, date='2026-09-12', reservation_label=r401)
        self.assert_identities('konoz', [hidayah])

        self.assertEqual(ledger.kas_surabaya('konoz'), 0)
        self.assertEqual(ledger.kas_pusat('konoz'), 16000)
        self.assertEqual(sum(a.amount_sar for a in Allocation.objects.filter(company='konoz')), 15000)
        self.assertEqual(ledger.piutang(r401), 0)
        self.assertEqual(ledger.surplus_pusat('konoz'), 1000)
        self.assertEqual(ledger.saldo_dana(hidayah), 1000)

        # 20/09 -- layanan tambahan R-402, dibayar dari surplus yang sudah ada di pusat
        service = self.make_service_item(invoice, 'Layanan tambahan', 1000)
        self.charge(hidayah, 1000, date='2026-09-20', service_item=service)
        self.alloc(hidayah, 1000, date='2026-09-20', service_item=service)
        self.assert_identities('konoz', [hidayah])

        total_alloc = sum(a.amount_sar for a in Allocation.objects.filter(company='konoz'))
        self.assertEqual(total_alloc, 16000)
        self.assertEqual(total_alloc, ledger.kas_pusat('konoz'))
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 0)
        self.assertEqual(ledger.saldo_dana(hidayah), 0)


class LampiranA4Test(LampiranABase):
    """Dua jenis koreksi setelah remittance received: peruntukan salah vs kas salah."""

    def test_dua_jenis_koreksi_setelah_received(self):
        rahmah = self.make_client('PT Rahmah')
        invoice = self.make_invoice('INV-A4')
        r501 = self.make_reservation(invoice, 'R-501', 5000)
        r502 = self.make_reservation(invoice, 'R-502', 7000)
        self.charge(rahmah, 5000, date='2026-10-01', reservation=r501)
        self.charge(rahmah, 7000, date='2026-10-01', reservation=r502)

        # 03/10 -- bayar 12.000, staf tertukar peruntukannya
        self.alloc(rahmah, 7000, date='2026-10-03', reservation=r501)
        self.alloc(rahmah, 5000, date='2026-10-03', reservation=r502)
        self.mov(rahmah, 'client', 'sby', 7000, date='2026-10-03', reservation_label=r501)
        self.mov(rahmah, 'client', 'sby', 5000, date='2026-10-03', reservation_label=r502)
        self.assert_identities('konoz', [rahmah])

        # 05/10 kirim, 07/10 received -- RMT-030
        m_pusat_501 = self.mov(rahmah, 'sby', 'pusat', 7000, date='2026-10-07', reservation_label=r501)
        m_pusat_502 = self.mov(rahmah, 'sby', 'pusat', 5000, date='2026-10-07', reservation_label=r502)
        self.assert_identities('konoz', [rahmah])

        # Koreksi 1 (15/10) -- peruntukan salah, kas benar
        k1 = uuid.uuid4()
        self.alloc(rahmah, -2000, date='2026-10-15', reason=AllocationReason.CORRECTION, reservation=r501, transfer_group=k1)
        self.alloc(rahmah, 2000, date='2026-10-15', reason=AllocationReason.CORRECTION, reservation=r502, transfer_group=k1)
        self.assert_identities('konoz', [rahmah])

        self.assertEqual(ledger.piutang(r501), 0)
        self.assertEqual(ledger.piutang(r502), 0)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 0)

        # Koreksi 2 (20/10) -- nominal kas salah, cuma 11.000 yang sampai pusat
        self.mov(
            rahmah, 'pusat', 'sby', 1000, date='2026-10-20', reservation_label=r502,
            reverses=m_pusat_502, note='koreksi RMT-030',
        )
        self.assert_identities('konoz', [rahmah])

        self.assertEqual(ledger.kas_surabaya('konoz'), 1000)
        self.assertEqual(ledger.kas_pusat('konoz'), 11000)
        self.assertEqual(sum(a.amount_sar for a in Allocation.objects.filter(company='konoz')), 12000)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 1000)
        # movement asli RMT-030 tidak diubah/dihapus
        m_pusat_501.refresh_from_db()
        m_pusat_502.refresh_from_db()
        self.assertEqual(m_pusat_501.amount, 7000)
        self.assertEqual(m_pusat_502.amount, 5000)


class LampiranA5Test(LampiranABase):
    """Pembayaran rupiah dengan kurs bergerak, selisih kurs saat remittance ditampung dompet FX."""

    def test_kurs_bergerak_dan_selisih_kurs_ditampung_fx(self):
        salam = self.make_client('PT Salam')
        invoice = self.make_invoice('INV-A5')
        r601 = self.make_reservation(invoice, 'R-601', 10000)
        self.charge(salam, 10000, date='2026-11-01', reservation=r601)

        # 05/11, 20/11 -- bayar rupiah dengan kurs berbeda, alokasi selalu SAR
        self.mov(salam, 'client', 'sby', 21_000_000, date='2026-11-05', reservation_label=r601, currency='IDR', exchange_rate=4200)
        self.alloc(salam, 5000, date='2026-11-05', reservation=r601)
        self.mov(salam, 'client', 'sby', 21_500_000, date='2026-11-20', reservation_label=r601, currency='IDR', exchange_rate=4300)
        self.alloc(salam, 5000, date='2026-11-20', reservation=r601)
        self.assert_identities('konoz', [salam])
        self.assertEqual(ledger.piutang(r601), 0)

        # 25/11 -- Surabaya tukar Rp42.500.000 @4400, sampai di pusat 9.659 SAR, selisih 341 ke FX
        self.mov(salam, 'sby', 'pusat', 9659, date='2026-11-25', reservation_label=r601)
        self.mov(salam, 'sby', 'fx', 341, date='2026-11-25', reservation_label=r601, note='selisih kurs')
        self.assert_identities('konoz', [salam])

        self.assertEqual(ledger.kas_surabaya('konoz'), 0)
        self.assertEqual(ledger.kas_pusat('konoz'), 9659)
        self.assertEqual(ledger.selisih_kurs('konoz'), 341)
        self.assertEqual(sum(a.amount_sar for a in Allocation.objects.filter(company='konoz')), 10000)
        self.assertEqual(ledger.kewajiban_kirim_sby('konoz'), 0)
        self.assertEqual(ledger.saldo_dana(salam), 0)


class ClientStatementTest(LampiranABase):
    def test_charge_then_payment_balance_reaches_zero(self):
        client = self.make_client('PT Statement')
        invoice = self.make_invoice('INV-STMT-1')
        r1 = self.make_reservation(invoice, 'R1', 5000)
        self.charge(client, 5000, date='2026-01-01', reservation=r1)
        self.mov(client, 'client', 'sby', 5000, date='2026-01-05', reservation_label=r1)

        rows = ledger.client_statement(client)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['debit'], 5000)
        self.assertEqual(rows[0]['credit'], 0)
        self.assertEqual(rows[0]['balance'], 5000)
        self.assertEqual(rows[1]['debit'], 0)
        self.assertEqual(rows[1]['credit'], 5000)
        self.assertEqual(rows[1]['balance'], 0)

    def test_refund_appears_as_debit_and_increases_balance(self):
        client = self.make_client('PT Refund')
        invoice = self.make_invoice('INV-STMT-2')
        r1 = self.make_reservation(invoice, 'R1', 5000)
        self.charge(client, 5000, date='2026-01-01', reservation=r1)
        self.mov(client, 'client', 'sby', 6000, date='2026-01-05', reservation_label=r1)
        self.mov(client, 'sby', 'client', 1000, date='2026-01-10', reservation_label=r1)

        rows = ledger.client_statement(client)
        self.assertEqual(rows[-1]['balance'], 0)  # 5000 - 6000 + 1000 = 0
        refund_row = rows[-1]
        self.assertEqual(refund_row['debit'], 1000)
        self.assertEqual(refund_row['credit'], 0)

    def test_transfer_pair_shown_as_memo_without_changing_balance(self):
        client = self.make_client('PT Transfer')
        invoice = self.make_invoice('INV-STMT-3')
        r1 = self.make_reservation(invoice, 'R1', 5000)
        r2 = self.make_reservation(invoice, 'R2', 5000)
        group = uuid.uuid4()
        self.alloc(client, -1000, date='2026-01-02', reservation=r1, reason=AllocationReason.TRANSFER, transfer_group=group)
        self.alloc(client, 1000, date='2026-01-02', reservation=r2, reason=AllocationReason.TRANSFER, transfer_group=group)

        rows = ledger.client_statement(client)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['type'], 'memo')
        self.assertEqual(rows[0]['debit'], 0)
        self.assertEqual(rows[0]['credit'], 0)
        self.assertIn('R1', rows[0]['description'])
        self.assertIn('R2', rows[0]['description'])

    def test_date_range_filters_by_event_date(self):
        client = self.make_client('PT Range')
        invoice = self.make_invoice('INV-STMT-4')
        r1 = self.make_reservation(invoice, 'R1', 5000)
        self.charge(client, 3000, date='2026-01-01', reservation=r1)
        self.charge(client, 2000, date='2026-02-01', reservation=r1)

        rows = ledger.client_statement(client, date_from='2026-02-01')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['debit'], 2000)

    def test_as_of_locks_out_later_backdated_corrections(self):
        client = self.make_client('PT AsOf')
        invoice = self.make_invoice('INV-STMT-5')
        r1 = self.make_reservation(invoice, 'R1', 5000)
        c1 = self.charge(client, 5000, date='2026-01-01', reservation=r1)
        c1.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        c1.save(update_fields=['created_at'])
        as_of_jan = datetime(2026, 1, 31, 23, 59, 59, tzinfo=dt_timezone.utc)

        first_statement = ledger.client_statement(client, as_of=as_of_jan)
        self.assertEqual(first_statement[-1]['balance'], 5000)

        # koreksi backdated, dicatat (created_at) belakangan
        c2 = self.charge(client, 500, date='2026-01-15', reason=ChargeReason.CORRECTION, reservation=r1)
        c2.created_at = datetime(2026, 2, 5, 10, 0, tzinfo=dt_timezone.utc)
        c2.save(update_fields=['created_at'])

        # cetak ulang periode Januari dengan as_of lama -> identik
        reprint = ledger.client_statement(client, date_to='2026-01-31', as_of=as_of_jan)
        self.assertEqual(reprint[-1]['balance'], 5000)

        # statement baru tanpa as_of lama melihat koreksi itu
        later = ledger.client_statement(client)
        self.assertEqual(later[-1]['balance'], 5500)
