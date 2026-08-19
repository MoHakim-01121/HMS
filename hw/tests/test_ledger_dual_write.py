import json

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import (
    Invoice, Reservation, ServiceItem, Payment,
    Charge, Allocation, CashMovement, Remittance,
)
from hw import ledger


class DualWriteTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.user.profile.role = 'manager'  # staff role is remittance-read-only
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()


class InvoiceNewDualWriteTest(DualWriteTestBase):
    def test_creating_invoice_writes_both_payment_and_ledger(self):
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-001",
            "customer_name": "PT Dual Write",
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
        res = Reservation.objects.get(invoice=invoice, reservation_number="R1")

        # Payment (old) still written -- Invoice Detail's payment list depends on it
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)

        # Ledger (new) also written
        self.assertEqual(ledger.tagihan(res), 5000)
        self.assertEqual(ledger.terbayar(res), 3000)
        movement = CashMovement.objects.get(invoice=invoice)
        self.assertEqual(movement.from_account, 'client')
        self.assertEqual(movement.to_account, 'sby')
        self.assertEqual(movement.reservation_label, res)

    def test_direct_payment_routes_to_pusat_in_ledger_too(self):
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-DW-002",
            "customer_name": "PT Direct",
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
        invoice = Invoice.objects.get(invoice_number="INV-DW-002")
        movement = CashMovement.objects.get(invoice=invoice)
        self.assertEqual(movement.to_account, 'pusat')


class InvoiceEditDualWriteTest(DualWriteTestBase):
    def setUp(self):
        super().setUp()
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-DW-EDIT", customer_name="PT Edit", currency="SAR",
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number="R1", total_sar=5000)
        Charge.objects.create(
            company="konoz", client=None, invoice=self.invoice, date="2026-01-01",
            amount_sar=5000, reservation=self.res, reason="initial",
        )

    def _edit(self, reservations, payments):
        return self.client.post(f"/invoice/{self.invoice.pk}/edit/", {
            "invoice_number": "INV-DW-EDIT",
            "customer_name": "PT Edit",
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
        new_res = Reservation.objects.get(invoice=self.invoice, reservation_number="R1")
        # Old Reservation row (and its Charge, via cascade) is gone; exactly
        # one fresh Charge for the new total -- not both old and new summed.
        self.assertEqual(ledger.tagihan(new_res), 8000)
        self.assertEqual(Charge.objects.filter(invoice=self.invoice).count(), 1)

    def test_edit_does_not_touch_remittance_movements(self):
        # Simulate money already collected and sent to HQ before this edit.
        CashMovement.objects.create(
            company="konoz", invoice=self.invoice, reservation_label=self.res,
            from_account="client", to_account="sby",
            amount=5000, currency="SAR", exchange_rate=1, date="2026-01-02",
            note="pre-existing payment sync",
        )
        rem = Remittance.objects.create(company="konoz", date="2026-01-03", remittance_number="RMT-DW-01")
        sent = CashMovement.objects.create(
            company="konoz", invoice=self.invoice, reservation_label=self.res, remittance=rem,
            from_account="sby", to_account="pusat",
            amount=5000, currency="SAR", exchange_rate=1, date="2026-01-03",
        )

        self._edit(
            [{"reservation_number": "R1", "hotel": "Hotel A", "check_in": "", "check_out": "", "reservation_total": "5000"}],
            [{"ref": "R1", "date": "2026-01-05", "method": "Cash", "amount": "0"}],
        )

        sent.refresh_from_db()  # must not have been deleted or altered
        self.assertEqual(sent.amount, 5000)
        self.assertEqual(CashMovement.objects.filter(from_account='sby', to_account='pusat').count(), 1)


class ServicesDualWriteTest(DualWriteTestBase):
    def test_creating_services_invoice_writes_charge_for_service_item(self):
        resp = self.client.post("/services/new/", {
            "invoice_number": "SVC-DW-001",
            "customer_name": "PT Visa",
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
        item = ServiceItem.objects.get(invoice=invoice)
        self.assertEqual(sum(c.amount_sar for c in Charge.objects.filter(service_item=item)), 1000)
        movement = CashMovement.objects.get(invoice=invoice)
        self.assertEqual(movement.service_item_label, item)
        self.assertEqual(Allocation.objects.filter(service_item=item).count(), 1)


class RemittanceDualWriteTest(DualWriteTestBase):
    def setUp(self):
        super().setUp()
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-RMT-DW", customer_name="PT Remit",
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number="R1", total_sar=5000)

    def test_new_remittance_writes_both_remittanceline_and_cashmovement(self):
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

        movement = CashMovement.objects.get(from_account='sby', to_account='pusat')
        self.assertEqual(movement.amount, 3000)
        self.assertEqual(movement.reservation_label, self.res)
        self.assertEqual(ledger.mengendap_per_res(self.res), -3000)

    def test_editing_remittance_amount_resyncs_cashmovement_not_duplicates(self):
        rem = Remittance.objects.create(company="konoz", date="2026-01-10", remittance_number="RMT-DW-01")
        from hw.models import RemittanceLine
        line = RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number="R1", amount_sar=3000)
        CashMovement.objects.create(
            company="konoz", invoice=self.invoice, remittance=rem, reservation_label=self.res,
            from_account="sby", to_account="pusat", amount=3000, currency="SAR", exchange_rate=1, date="2026-01-10",
        )

        resp = self.client.post(f"/remittance/{rem.pk}/edit/", {
            "date": "2026-01-10", "status": "pending", "receipt_reference": "", "note": "",
            "lines": json.dumps([{"line_id": line.pk, "amount_sar": "4500"}]),
        })
        self.assertEqual(resp.status_code, 302)

        movements = CashMovement.objects.filter(remittance=rem)
        self.assertEqual(movements.count(), 1)  # resynced, not duplicated
        self.assertEqual(movements.get().amount, 4500)

    def test_deleting_remittance_line_removes_its_cashmovement(self):
        rem = Remittance.objects.create(company="konoz", date="2026-01-10", remittance_number="RMT-DW-02")
        from hw.models import RemittanceLine
        line = RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number="R1", amount_sar=3000)
        CashMovement.objects.create(
            company="konoz", invoice=self.invoice, remittance=rem, reservation_label=self.res,
            from_account="sby", to_account="pusat", amount=3000, currency="SAR", exchange_rate=1, date="2026-01-10",
        )

        resp = self.client.post(f"/remittance/{rem.pk}/edit/", {
            "date": "2026-01-10", "status": "pending", "receipt_reference": "", "note": "",
            "lines": json.dumps([]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CashMovement.objects.filter(remittance=rem).count(), 0)
