from datetime import date, datetime, timezone as dt_timezone

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, Charge, CashMovement, ChargeReason
from hw import ledger


class ClientStatementWithOpeningTest(TestCase):
    """hw/ledger.py::client_statement_with_opening -- period exports must carry
    forward whatever happened before `date_from` as a single opening-balance
    line, so a period's closing balance always reconciles with a full one."""

    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Statement Test')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-STMT-OPEN', customer_name='PT Statement Test',
        )
        self.r1 = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=5000)

    def _charge(self, amount, d, reason=ChargeReason.INITIAL):
        return Charge.objects.create(
            company='konoz', client=self.client_obj, date=d, amount_sar=amount,
            invoice=self.invoice, reservation=self.r1, reason=reason,
        )

    def _mov(self, from_account, to_account, amount, d):
        return CashMovement.objects.create(
            company='konoz', client=self.client_obj, date=d, invoice=self.invoice,
            from_account=from_account, to_account=to_account, amount=amount,
            currency='SAR', exchange_rate=1, reservation_label=self.r1,
        )

    def test_no_date_from_has_zero_opening_balance(self):
        self._charge(5000, '2026-01-01')
        result = ledger.client_statement_with_opening(self.client_obj)
        self.assertEqual(result['opening_balance'], 0)
        self.assertEqual(result['closing_balance'], 5000)

    def test_period_carries_forward_prior_balance_of_zero(self):
        # Januari: ditagih 5000, dibayar lunas -- saldo balik 0 di akhir bulan
        self._charge(5000, '2026-01-01')
        self._mov('client', 'sby', 5000, '2026-01-05')
        # Februari: tagihan baru, belum dibayar
        self._charge(3000, '2026-02-10')

        result = ledger.client_statement_with_opening(
            self.client_obj, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28),
        )
        self.assertEqual(result['opening_balance'], 0)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['balance'], 3000)
        self.assertEqual(result['closing_balance'], 3000)

    def test_period_with_nonzero_opening_balance_reconciles_with_full_statement(self):
        # Januari: ditagih 5000, baru dibayar 2000 -- sisa 3000 terbawa ke Februari
        self._charge(5000, '2026-01-01')
        self._mov('client', 'sby', 2000, '2026-01-05')
        # Februari: lunasi sisanya
        self._mov('client', 'sby', 3000, '2026-02-10')

        result = ledger.client_statement_with_opening(
            self.client_obj, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28),
        )
        self.assertEqual(result['opening_balance'], 3000)
        self.assertEqual(result['rows'][0]['balance'], 0)
        self.assertEqual(result['closing_balance'], 0)

        full = ledger.client_statement(self.client_obj)
        self.assertEqual(full[-1]['balance'], result['closing_balance'])

    def test_reprint_with_as_of_matches_original_despite_later_backdated_correction(self):
        c1 = self._charge(5000, '2026-01-01')
        c1.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        c1.save(update_fields=['created_at'])
        as_of_jan = datetime(2026, 1, 31, 23, 59, 59, tzinfo=dt_timezone.utc)

        first = ledger.client_statement_with_opening(self.client_obj, as_of=as_of_jan)
        self.assertEqual(first['closing_balance'], 5000)

        # koreksi backdated ke Januari, tapi baru dicatat (created_at) di Februari
        c2 = self._charge(500, '2026-01-15', reason=ChargeReason.CORRECTION)
        c2.created_at = datetime(2026, 2, 5, 10, 0, tzinfo=dt_timezone.utc)
        c2.save(update_fields=['created_at'])

        reprint = ledger.client_statement_with_opening(
            self.client_obj, date_to=date(2026, 1, 31), as_of=as_of_jan,
        )
        self.assertEqual(reprint['closing_balance'], 5000)   # identik dengan cetakan pertama

        later = ledger.client_statement_with_opening(self.client_obj)
        self.assertEqual(later['closing_balance'], 5500)     # koreksi muncul di statement baru


class ClientStatementPdfViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('stmt_manager', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()

        self.client_obj = Client.objects.create(company='konoz', name='PT PDF Test')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-STMT-PDF', customer_name='PT PDF Test',
        )
        r1 = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=5000)
        Charge.objects.create(
            company='konoz', client=self.client_obj, date='2026-01-01', amount_sar=5000,
            invoice=self.invoice, reservation=r1, reason=ChargeReason.INITIAL,
        )

    def test_returns_pdf(self):
        resp = self.client.get(f'/clients/{self.client_obj.pk}/statement/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_period_query_params_are_accepted(self):
        resp = self.client.get(
            f'/clients/{self.client_obj.pk}/statement/pdf/?from=2026-01-01&to=2026-01-31'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(f'/clients/{self.client_obj.pk}/statement/pdf/')
        self.assertEqual(resp.status_code, 302)

    def test_scoped_to_active_company(self):
        other = Client.objects.create(company='ijabah', name='PT Other Co')
        resp = self.client.get(f'/clients/{other.pk}/statement/pdf/')
        self.assertEqual(resp.status_code, 404)
