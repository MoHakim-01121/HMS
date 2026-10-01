import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Invoice, Client, Remittance
from hw.finance.accounts import cash_ledger_for
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.finance import queries as fq
from hw.tests.factories import make_hotel_line, make_invoice, make_priced_cl, set_line_total


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
            name="2020-2030",            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Dual Write")


class InvoiceNewDualWriteTest(DualWriteTestBase):
    def test_creating_invoice_posts_charge_and_payment_to_journal(self):
        cl = make_priced_cl(self.client_obj, "R1", 5000, check_in=date(2026, 2, 1), check_out=date(2026, 2, 3))
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-001",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "linked_cl_ids": json.dumps([cl.pk]),
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
        cl = make_priced_cl(self.client_obj, "R1", 5000)
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-002",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "linked_cl_ids": json.dumps([cl.pk]),
            "payments": json.dumps([
                {"ref": "R1", "date": "2026-01-05", "method": "Direct", "amount": "5000", "currency": "SAR", "exchange": "1"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fq.kas_pusat(), 5000)


class InvoiceEditDualWriteTest(DualWriteTestBase):
    def setUp(self):
        super().setUp()
        from hw.finance import posting
        self.invoice = make_invoice(
 invoice_type="hotel", invoice_number="INV-DW-EDIT",
            customer_name="PT Dual Write", client=self.client_obj, currency="SAR",
            issued_date=date(2026, 1, 1),
        )
        self.res = make_hotel_line(invoice=self.invoice, reservation_number="R1", total_sar=5000)
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _edit(self, reservations, payments):
        # The invoice bills the CL; "changing the reservation total" means the
        # CL changed. set_line_total changes it without re-posting, so the
        # invoice save below is what has to bring the ledger in line.
        for row in reservations:
            self.res = set_line_total(self.res, int(row["reservation_total"]))
        return self.client.post(f"/invoice/{self.invoice.pk}/edit/", {
            "invoice_number": "INV-DW-EDIT",
            "customer_name": "PT Dual Write",
            "client_id": str(self.client_obj.pk),
            "issued_date": "2026-01-01",
            "due_date": "",
            "linked_cl_ids": json.dumps([self.res.confirmation_letter_id]),
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
        self.invoice = make_invoice(
 invoice_type="hotel",
            invoice_number="INV-RMT-DW", customer_name="PT Remit",
        )
        self.res = make_hotel_line(invoice=self.invoice, reservation_number="R1", total_sar=5000)

    def _idr_account(self):
        from hw.models import BankAccount, LedgerAccount
        return BankAccount.objects.create(
            branch_id="sby", name="Ops IDR", currency="IDR", bank_name="Mandiri",
            account_identifier="1400", ledger_account_id=cash_ledger_for('sby', 'IDR'),
        )

    def test_new_remittance_is_lump_sum_send_leg(self):
        # Transfer baru tidak memilih reservasi (alokasi saat Pusat menerima,
        # lihat test_remittance_allocation): baris kiriman diabaikan.
        acc = self._idr_account()
        resp = self.client.post("/remittance/new/", {
            "from_bank_account": str(acc.pk),
            "date": "2026-01-10",
            "receipt_reference": "REF-1",
            "note": "",
            "amount_idr": "14400000",
            "exchange_rate": "4800",
            "lines": json.dumps([
                {"linked_number": "R1", "invoice_id": self.invoice.pk, "amount_sar": "3000"},
            ]),
        })
        self.assertEqual(resp.status_code, 302)

        from hw.models import RemittanceLine
        self.assertFalse(RemittanceLine.objects.exists())
        # Journal: kirim 3000 dari Kas Surabaya ke Transit, lump-sum;
        # tidak ada lagi shadow CashMovement (Fase 7).
        self.assertEqual(fq.transit(), 3000)
        self.assertEqual(fq.kas_surabaya(), -3000)
        # Cash book: the rupiah left the chosen IDR account.
        from hw.models import BankTransaction, Remittance
        rem = Remittance.objects.get()
        self.assertEqual(rem.from_account_id, acc.pk)
        tx = BankTransaction.objects.get(source_type="Remittance", source_id=rem.pk)
        self.assertEqual((tx.account_id, tx.direction, tx.currency, tx.amount, tx.amount_sar),
                         (acc.pk, "out", "IDR", 14_400_000, 3000))

    def test_new_remittance_requires_from_account(self):
        self._idr_account()
        resp = self.client.post("/remittance/new/", {
            "date": "2026-01-10", "amount_idr": "14400000", "exchange_rate": "4800",
        }, HTTP_X_INERTIA="true")
        from hw.models import Remittance
        self.assertFalse(Remittance.objects.exists())
        self.assertIn("IDR bank account", resp.json()["props"]["error"])

    def test_new_remittance_requires_idr_and_rate(self):
        resp = self.client.post("/remittance/new/", {"date": "2026-01-10", "amount_idr": "14400000"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Remittance.objects.exists())
