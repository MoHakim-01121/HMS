import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Invoice, Reservation, ServiceItem, Client, Remittance
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.finance import queries as fq


class DualWriteTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.user.profile.role = 'manager'  # staff role is remittance-read-only
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()
        FinancialPeriod.objects.create(
            name="2020-2030", company="konoz",
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(company="konoz", name="PT Dual Write")


class InvoiceNewDualWriteTest(DualWriteTestBase):
    def test_creating_invoice_posts_charge_and_payment_to_journal(self):
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-001",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "reservations": json.dumps([
                {"reservation_number": "R1", "hotel": "Hotel A", "check_in": "2026-02-01", "check_out": "2026-02-03", "reservation_total": "5000"},
            ]),
            "payments": json.dumps([
                {"ref": "R1", "date": "2026-01-05", "method": "Cash", "amount": "3000", "currency": "SAR", "exchange": "1"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)
        invoice = Invoice.objects.get(invoice_number="INV-DW-001")
        self.assertEqual(PaymentRecord.objects.filter(invoice=invoice).count(), 1)
        self.assertEqual(fq.invoice_charged_sar(invoice.id), 5000)
        self.assertEqual(fq.invoice_paid_sar(invoice.id), 3000)

    def test_direct_payment_routes_to_kas_pusat(self):
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-002",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "reservations": json.dumps([
                {"reservation_number": "R1", "hotel": "Hotel A", "check_in": "", "check_out": "", "reservation_total": "5000"},
            ]),
            "payments": json.dumps([
                {"ref": "R1", "date": "2026-01-05", "method": "Direct", "amount": "5000", "currency": "SAR", "exchange": "1"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fq.kas_pusat("konoz"), 5000)


class InvoiceEditDualWriteTest(DualWriteTestBase):
    def setUp(self):
        super().setUp()
        from hw.finance import posting
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel", invoice_number="INV-DW-EDIT",
            customer_name="PT Dual Write", client=self.client_obj, currency="SAR",
            issued_date=date(2026, 1, 1),
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number="R1", total_sar=5000)
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _edit(self, reservations, payments):
        return self.client.post(f"/invoice/{self.invoice.pk}/edit/", {
            "invoice_number": "INV-DW-EDIT",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "reservations": json.dumps(reservations),
            "payments": json.dumps(payments),
        })

    def test_edit_resyncs_charge_to_new_total_not_old_plus_new(self):
        resp = self._edit(
            [{"reservation_number": "R1", "hotel": "Hotel A", "check_in": "", "check_out": "", "reservation_total": "8000"}],
            [],
        )
        self.assertEqual(resp.status_code, 302)
        # Charge lama di-reverse, charge baru diposting — net Piutang = 8000.
        self.assertEqual(fq.invoice_charged_sar(self.invoice.id), 8000)

    def test_repeated_payment_edits_leave_one_effective_payment_record(self):
        res = [{"reservation_number": "R1", "hotel": "Hotel A", "check_in": "", "check_out": "", "reservation_total": "5000"}]
        for amt in ("1000", "2000", "3000"):
            self._edit(res, [{"ref": "R1", "date": "2026-01-05", "method": "Cash", "amount": amt, "currency": "SAR", "exchange": "1"}])
        # PaymentRecord append-only: baris lama ditandai REVERSED, bukan menumpuk.
        eff = PaymentRecord.objects.filter(invoice=self.invoice, status__in=PaymentRecord.EFFECTIVE_STATUSES)
        self.assertEqual(eff.count(), 1)
        self.assertEqual(fq.invoice_paid_sar(self.invoice.id), 3000)
        self.assertEqual(len(fq.payment_history_rows(self.invoice)), 1)


class ServicesDualWriteTest(DualWriteTestBase):
    def test_creating_services_invoice_posts_service_income(self):
        resp = self.client.post("/services/new/", {
            "invoice_number": "SVC-DW-001",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "currency": "SAR",
            "service_items": json.dumps([
                {"name": "Visa Umrah", "qty": "2", "price": "500"},
            ]),
            "payments": json.dumps([
                {"ref": "1", "date": "2026-01-05", "method": "Cash", "amount": "600", "currency": "SAR", "exchange": "1"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)
        invoice = Invoice.objects.get(invoice_number="SVC-DW-001")
        self.assertEqual(fq.invoice_charged_sar(invoice.id), 1000)
        self.assertEqual(fq.invoice_paid_sar(invoice.id), 600)


class RemittanceDualWriteTest(DualWriteTestBase):
    def setUp(self):
        super().setUp()
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-RMT-DW", customer_name="PT Remit",
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number="R1", total_sar=5000)

    def test_new_remittance_writes_line_and_journal_send_leg(self):
        resp = self.client.post("/remittance/new/", {
            "date": "2026-01-10",
            "receipt_reference": "REF-1",
            "note": "",
            "lines": json.dumps([
                {"linked_number": "R1", "invoice_id": self.invoice.pk, "amount_sar": "3000"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)

        from hw.models import RemittanceLine
        self.assertEqual(RemittanceLine.objects.filter(linked_number="R1").count(), 1)
        # Journal: kirim 3000 dari Kas Surabaya ke Transit (per reservasi);
        # tidak ada lagi shadow CashMovement (Fase 7).
        self.assertEqual(fq.transit("konoz"), 3000)
        self.assertEqual(fq.kas_surabaya("konoz"), -3000)

    def test_editing_remittance_amount_resyncs_journal_not_duplicates(self):
        rem = Remittance.objects.create(company="konoz", date="2026-01-10", remittance_number="RMT-DW-01")
        from hw.models import RemittanceLine
        line = RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number="R1", amount_sar=3000)

        resp = self.client.post(f"/remittance/{rem.pk}/edit/", {
            "date": "2026-01-10", "status": "pending", "receipt_reference": "", "note": "",
            "lines": json.dumps([{"line_id": line.pk, "amount_sar": "4500"}]),
        })
        self.assertEqual(resp.status_code, 302)

        # Idempotent-by-content: jumlah di-resync, tidak ditumpuk.
        self.assertEqual(fq.transit("konoz"), 4500)
        self.assertEqual(fq.kas_surabaya("konoz"), -4500)

    def test_deleting_remittance_line_reverses_its_journal_leg(self):
        rem = Remittance.objects.create(company="konoz", date="2026-01-10", remittance_number="RMT-DW-02")
        from hw.models import RemittanceLine
        line = RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number="R1", amount_sar=3000)

        resp = self.client.post(f"/remittance/{rem.pk}/edit/", {
            "date": "2026-01-10", "status": "pending", "receipt_reference": "", "note": "",
            "lines": json.dumps([]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(RemittanceLine.objects.filter(remittance=rem).count(), 0)
        self.assertEqual(fq.transit("konoz"), 0)
