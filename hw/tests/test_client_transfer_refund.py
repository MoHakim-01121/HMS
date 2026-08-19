from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, Charge, Allocation, CashMovement
from hw import ledger


class ClientTransferRefundTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.client_obj = Client.objects.create(company="konoz", name="PT Transfer Test")
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-XFER-001", customer_name="PT Transfer Test",
        )
        self.r1 = Reservation.objects.create(invoice=self.invoice, reservation_number="R1", total_sar=5000)
        self.r2 = Reservation.objects.create(invoice=self.invoice, reservation_number="R2", total_sar=3000)
        for r, amt in ((self.r1, 5000), (self.r2, 3000)):
            Charge.objects.create(
                company="konoz", client=self.client_obj, invoice=self.invoice, date="2026-01-01",
                amount_sar=amt, reservation=r, reason="initial",
            )


class ClientTransferTest(ClientTransferRefundTestBase):
    def test_transfer_moves_allocation_between_reservations(self):
        Allocation.objects.create(
            company="konoz", client=self.client_obj, invoice=self.invoice, date="2026-01-02",
            amount_sar=5000, reservation=self.r1, reason="initial",
        )
        self.assertEqual(ledger.piutang(self.r1), 0)
        self.assertEqual(ledger.piutang(self.r2), 3000)

        resp = self.client.post(f"/clients/{self.client_obj.pk}/transfer/", {
            "from_reservation": self.r1.pk, "to_reservation": self.r2.pk, "amount_sar": "2000",
        })
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(ledger.piutang(self.r1), 2000)
        self.assertEqual(ledger.piutang(self.r2), 1000)

        allocs = Allocation.objects.filter(reason='transfer')
        self.assertEqual(allocs.count(), 2)
        self.assertIsNotNone(allocs.first().transfer_group)
        self.assertEqual(allocs.first().transfer_group, allocs.last().transfer_group)

    def test_transfer_rejects_same_reservation(self):
        resp = self.client.post(f"/clients/{self.client_obj.pk}/transfer/", {
            "from_reservation": self.r1.pk, "to_reservation": self.r1.pk, "amount_sar": "1000",
        }, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("to_reservation", resp.json()["props"]["errors"])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_transfer_rejects_zero_amount(self):
        resp = self.client.post(f"/clients/{self.client_obj.pk}/transfer/", {
            "from_reservation": self.r1.pk, "to_reservation": self.r2.pk, "amount_sar": "0",
        }, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("amount_sar", resp.json()["props"]["errors"])
        self.assertEqual(Allocation.objects.count(), 0)

    def test_form_lists_this_clients_reservations_with_piutang(self):
        resp = self.client.get(f"/clients/{self.client_obj.pk}/transfer/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        options = resp.json()["props"]["reservations"]
        self.assertEqual({o["id"] for o in options}, {self.r1.pk, self.r2.pk})

    def test_transfer_rejects_reservation_belonging_to_another_client(self):
        other_client = Client.objects.create(company="konoz", name="PT Other Client")
        other_invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-XFER-OTHER", customer_name="PT Other Client",
        )
        other_res = Reservation.objects.create(invoice=other_invoice, reservation_number="R-OTHER", total_sar=4000)
        Charge.objects.create(
            company="konoz", client=other_client, invoice=other_invoice, date="2026-01-01",
            amount_sar=4000, reservation=other_res, reason="initial",
        )

        resp = self.client.post(f"/clients/{self.client_obj.pk}/transfer/", {
            "from_reservation": self.r1.pk, "to_reservation": other_res.pk, "amount_sar": "1000",
        }, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("to_reservation", resp.json()["props"]["errors"])
        self.assertEqual(Allocation.objects.count(), 0)
        self.assertEqual(ledger.piutang(other_res), 4000)


class ClientRefundTest(ClientTransferRefundTestBase):
    def test_refund_writes_cashmovement_to_client(self):
        resp = self.client.post(f"/clients/{self.client_obj.pk}/refund/", {
            "from_account": "sby", "amount_sar": "1500", "note": "kelebihan bayar",
        })
        self.assertEqual(resp.status_code, 302)

        mov = CashMovement.objects.get(client=self.client_obj)
        self.assertEqual(mov.from_account, 'sby')
        self.assertEqual(mov.to_account, 'client')
        self.assertEqual(mov.amount, 1500)
        self.assertEqual(mov.note, 'kelebihan bayar')

    def test_refund_rejects_zero_amount(self):
        resp = self.client.post(f"/clients/{self.client_obj.pk}/refund/", {
            "from_account": "sby", "amount_sar": "0",
        }, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("amount_sar", resp.json()["props"]["errors"])
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_refund_reduces_saldo_dana(self):
        CashMovement.objects.create(
            company="konoz", client=self.client_obj, invoice=self.invoice, date="2026-01-05",
            from_account="client", to_account="sby", amount=2000, currency="SAR", exchange_rate=1,
        )
        self.assertEqual(ledger.saldo_dana(self.client_obj), 2000)

        self.client.post(f"/clients/{self.client_obj.pk}/refund/", {
            "from_account": "sby", "amount_sar": "800",
        })
        self.assertEqual(ledger.saldo_dana(self.client_obj), 1200)
