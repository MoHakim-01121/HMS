"""Schema v2 F4: satu tabel baris invoice, invoice tanpa salinan, riwayat revisi."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from hw.finance import credit_note_service as cns
from hw.finance import posting, queries as fq
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import (
    Client, ConfirmationLetter, Invoice, InvoiceLine, Reservation, Room, ServiceItem,
)
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import (
    make_cl, make_client, make_hotel_line, make_invoice, make_room, make_service_line,
)


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('f4', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.client_obj = Client.objects.create(name='PT Maju Jaya', brand='Amanah Tour')
        self.client.force_login(self.user)

    def _cl(self, number, price=1000, nights=2, **kw):
        cl = make_cl(client=kw.pop('client', self.client_obj), confirmation_number=number,
                     check_in=date(2026, 3, 1), check_out=date(2026, 3, 1 + nights), hotel_name='Al Safwah', **kw)
        make_room(cl=cl, room_type='Quad', quantity=1, price=price)
        return cl

    def _pay(self, invoice, line, sar):
        p = create_payment_record(invoice, invoice.client, date(2026, 3, 5), sar, method='Transfer',
                                  created_by=self.user, reservation=line)
        confirm_payment(p, self.user)
        return p


class InvoiceWithoutCopiesTest(_Base):
    def test_invoice_name_is_read_from_the_client(self):
        inv = make_invoice(client=self.client_obj)
        self.assertEqual(inv.customer_name, 'Amanah Tour')
        self.assertNotIn('customer_name', {f.name for f in Invoice._meta.get_fields()})
        Client.objects.filter(pk=self.client_obj.pk).update(brand='Amanah Wisata')
        self.assertEqual(Invoice.objects.get(pk=inv.pk).customer_name, 'Amanah Wisata')

    def test_client_is_required_and_protected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invoice.objects.create(invoice_number='X1', client=None, branch_id='sby')
        make_invoice(client=self.client_obj)
        with self.assertRaises(ProtectedError):
            self.client_obj.delete()

    def test_branch_defaults_to_the_client_owner_branch_and_then_stays(self):
        self.client_obj.owner_branch_id = 'jkt'
        self.client_obj.save()
        inv = make_invoice(client=self.client_obj)
        self.assertEqual(inv.branch_id, 'jkt')
        # The client moves; the invoice keeps the branch that issued it.
        Client.objects.filter(pk=self.client_obj.pk).update(owner_branch_id='sby')
        inv = Invoice.objects.get(pk=inv.pk)
        inv.save()
        self.assertEqual(Invoice.objects.get(pk=inv.pk).branch_id, 'jkt')

    def test_invoice_number_is_unique_across_types(self):
        make_invoice(client=self.client_obj, invoice_number='INV-1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_invoice(client=self.client_obj, invoice_number='INV-1', invoice_type='visa', currency='USD')

    def test_constraints(self):
        bad = [
            dict(invoice_type='hotel', currency='USD'),                       # hotel is always SAR
            dict(invoice_type='visa', currency='EUR'),                        # unknown currency
            dict(invoice_type='services'),                                    # unknown type
            dict(status='paid'),                                              # payment state is not stored
            dict(status='void'),                                              # void needs its timestamp
            dict(issued_date=date(2026, 3, 10), due_date=date(2026, 3, 1)),   # due before issued
        ]
        for i, kw in enumerate(bad):
            with self.assertRaises(IntegrityError, msg=kw), transaction.atomic():
                make_invoice(client=self.client_obj, invoice_number=f'BAD-{i}', **kw)
        make_invoice(client=self.client_obj, invoice_number='OK-1', invoice_type='visa', currency='IDR')
        make_invoice(client=self.client_obj, invoice_number='OK-2', status='void', voided_at=timezone.now())

    def test_search_matches_number_company_and_brand(self):
        inv = make_invoice(client=self.client_obj, invoice_number='INV-7788')
        for token in ('7788', 'maju', 'amanah'):
            self.assertEqual(list(Invoice.objects.filter(Invoice.objects.name_matches(token))), [inv], token)


class HotelLineTest(_Base):
    def test_line_stores_no_figures_and_follows_the_reservation(self):
        cl = self._cl('7001', price=1000, nights=2)
        inv = make_invoice(client=self.client_obj)
        line = inv.add_hotel_line(cl)
        stored = {f.name for f in InvoiceLine._meta.get_fields()}
        self.assertFalse({'total_sar', 'hotel', 'check_in', 'check_out', 'reservation_number', 'client'} & stored)
        self.assertEqual((line.reservation_number, line.hotel, line.amount), ('7001', 'Al Safwah', 2000))
        self.assertEqual(inv.total_sar, 2000)

        Room.objects.filter(cl=cl).update(price=1500)
        ConfirmationLetter.objects.filter(pk=cl.pk).update(check_out=date(2026, 3, 4))
        self.assertEqual(Invoice.objects.get(pk=inv.pk).total_sar, 4500)

    def test_cancelled_reservation_bills_nothing(self):
        cl = self._cl('7002')
        inv = make_invoice(client=self.client_obj)
        inv.add_hotel_line(cl)
        ConfirmationLetter.objects.filter(pk=cl.pk).update(reservation_status='CANCELLED')
        self.assertEqual(Invoice.objects.get(pk=inv.pk).total_sar, 0)

    def test_a_reservation_is_billed_on_one_live_line_only(self):
        cl = self._cl('7003')
        inv = make_invoice(client=self.client_obj)
        inv.add_hotel_line(cl)
        other = make_invoice(client=self.client_obj)
        with self.assertRaisesMessage(ValueError, 'already billed'):
            other.add_hotel_line(cl)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InvoiceLine.objects.create(invoice=other, line_no=1, kind='hotel', confirmation_letter=cl)

    def test_reservation_of_another_client_is_refused(self):
        cl = self._cl('7004', client=make_client('PT Lain'))
        inv = make_invoice(client=self.client_obj)
        with self.assertRaisesMessage(ValueError, 'One invoice bills one client'):
            inv.add_hotel_line(cl)

    def test_reservation_reads_its_invoice_through_the_line(self):
        cl = self._cl('7005')
        self.assertIsNone(cl.invoice)
        self.assertNotIn('invoice', {f.name for f in ConfirmationLetter._meta.fields})
        inv = make_invoice(client=self.client_obj)
        inv.add_hotel_line(cl)
        self.assertEqual(cl.invoice, inv)
        self.assertEqual(list(inv.confirmation_letters), [cl])
        self.assertEqual(list(ConfirmationLetter.objects.invoiced()), [cl])
        self.assertEqual(list(ConfirmationLetter.objects.uninvoiced()), [])
        loaded = ConfirmationLetter.objects.with_invoice().get(pk=cl.pk)
        with self.assertNumQueries(0):
            self.assertEqual(loaded.invoice_id, inv.pk)

    def test_billed_reservation_cannot_be_deleted(self):
        cl = self._cl('7006')
        make_invoice(client=self.client_obj).add_hotel_line(cl)
        with self.assertRaises(ProtectedError):
            cl.delete()
        resp = self.client.post(f'/cl/{cl.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ConfirmationLetter.objects.filter(pk=cl.pk).exists())

    def test_line_shape_is_enforced_per_kind(self):
        cl = self._cl('7007')
        hotel_inv = make_invoice(client=self.client_obj)
        svc_inv = make_invoice(client=self.client_obj, invoice_type='visa', currency='USD')
        bad = [
            dict(invoice=hotel_inv, kind='hotel'),                                          # no reservation
            dict(invoice=hotel_inv, kind='hotel', confirmation_letter=cl, quantity=1, unit_price=5),
            dict(invoice=svc_inv, kind='service', description='', quantity=1, unit_price=5),
            dict(invoice=svc_inv, kind='service', description='Visa', quantity=0, unit_price=5),
            dict(invoice=svc_inv, kind='service', description='Visa'),                      # no quantity/price
            dict(invoice=hotel_inv, kind='penalty'),                                        # no penalty
            dict(invoice=svc_inv, kind='other', description='x', quantity=1, unit_price=1),
        ]
        for i, kw in enumerate(bad):
            with self.assertRaises(IntegrityError, msg=kw), transaction.atomic():
                InvoiceLine.objects.create(line_no=50 + i, **kw)

    def test_line_kinds_belong_to_their_invoice_type(self):
        hotel_inv = make_invoice(client=self.client_obj)
        svc_inv = make_invoice(client=self.client_obj, invoice_type='visa', currency='USD')
        with self.assertRaises(ValueError):
            hotel_inv.add_service_line('Visa', 1, 100)
        with self.assertRaises(ValueError):
            svc_inv.add_hotel_line(self._cl('7008'))


class InvoiceFollowsReservationTest(_Base):
    def setUp(self):
        super().setUp()
        self.cl = self._cl('7100', price=1000, nights=2)
        self.inv = make_invoice(client=self.client_obj, issued_date=date(2026, 3, 1))
        self.line = self.inv.add_hotel_line(self.cl)
        posting.post_invoice_charge(self.inv, created_by=self.user)

    def test_issue_records_the_first_revision(self):
        rev = self.inv.revisions.get()
        self.assertEqual((rev.revision_no, rev.reason, rev.total), (1, 'issue', 2000))
        self.assertEqual(rev.lines_snapshot[0]['amount'], 2000)
        self.assertEqual(rev.lines_snapshot[0]['line_id'], self.line.pk)

    def test_changing_a_room_reposts_the_charge_and_records_a_revision(self):
        room = self.cl.rooms.get()
        room.price = 1250
        room.save()
        self.assertEqual(fq.invoice_charged_sar(self.inv.pk), 2500)
        rev = self.inv.revisions.order_by('-revision_no').first()
        self.assertEqual((rev.revision_no, rev.reason, rev.total), (2, 'cl_change', 2500))

    def test_editing_the_cl_form_syncs_once(self):
        from hw.tests.factories import cl_form_payload
        room = self.cl.rooms.get()
        payload = cl_form_payload(self.cl, rooms=[
            {'quantity': 2, 'price': 900, 'room_type_id': room.room_type_ref_id},
            {'quantity': 1, 'price': 700, 'room_type_id': room.room_type_ref_id},
        ])
        before = JournalEntry.objects.count()
        resp = self.client.post(f'/cl/{self.cl.pk}/edit/', payload)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fq.invoice_charged_sar(self.inv.pk), (2 * 900 + 700) * 2)
        # One reversal and one new charge, not a pair per room written.
        self.assertEqual(JournalEntry.objects.count() - before, 2)
        self.assertEqual(self.inv.revisions.count(), 2)

    def test_nothing_changes_when_the_value_is_the_same(self):
        room = self.cl.rooms.get()
        room.note = 'late check-out'
        room.save()
        self.assertEqual(self.inv.revisions.count(), 1)
        self.assertEqual(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_CHARGE).count(), 1)

    def test_client_of_a_billed_reservation_cannot_be_changed(self):
        from hw.tests.factories import cl_form_payload
        other = make_client('PT Lain')
        resp = self.client.post(f'/cl/{self.cl.pk}/edit/', cl_form_payload(self.cl, client_id=str(other.pk)),
                                HTTP_X_INERTIA='true')
        self.assertIn('guest_name', resp.json()['props']['errors'])
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.client_id, self.client_obj.pk)


class VoidAndRemoveTest(_Base):
    def setUp(self):
        super().setUp()
        self.cl_a = self._cl('7200', price=1000, nights=2)
        self.cl_b = self._cl('7201', price=500, nights=2)
        self.inv = make_invoice(client=self.client_obj, issued_date=date(2026, 3, 1))
        self.line_a = self.inv.add_hotel_line(self.cl_a)
        self.line_b = self.inv.add_hotel_line(self.cl_b)
        posting.post_invoice_charge(self.inv, created_by=self.user)

    def _edit(self, cl_ids, **extra):
        data = {
            'client_id': str(self.client_obj.pk), 'invoice_number': self.inv.invoice_number,
            'issued_date': '2026-03-01', 'due_date': '2026-03-20',
            'linked_cl_ids': json.dumps(cl_ids),
        }
        data.update(extra)
        return self.client.post(f'/invoice/{self.inv.pk}/edit/', data, HTTP_X_INERTIA='true')

    def test_void_frees_the_reservations_and_keeps_what_was_billed(self):
        cns.void_invoice(self.inv, reason='salah client', created_by=self.user)
        inv = Invoice.objects.get(pk=self.inv.pk)
        self.assertTrue(inv.is_void)
        self.assertEqual((inv.total_sar, inv.due_sar), (3000, 0))
        self.assertEqual(list(inv.confirmation_letters), [])
        self.assertIsNone(ConfirmationLetter.objects.get(pk=self.cl_a.pk).invoice)
        rev = inv.revisions.order_by('-revision_no').first()
        self.assertEqual((rev.reason, rev.total), ('void', 0))
        # The CL changes later; the void invoice still shows what it billed.
        Room.objects.filter(cl=self.cl_a).update(price=9999)
        self.assertEqual(Invoice.objects.get(pk=inv.pk).total_sar, 3000)
        # And the reservation can be billed again on a new invoice.
        new = make_invoice(client=self.client_obj)
        new.add_hotel_line(self.cl_a)
        self.assertEqual(ConfirmationLetter.objects.get(pk=self.cl_a.pk).invoice, new)

    def test_taking_a_charged_reservation_off_voids_its_line(self):
        resp = self._edit([self.cl_a.pk])
        self.assertEqual(resp.status_code, 302, getattr(resp, 'content', b'')[:300])
        line_b = InvoiceLine.objects.get(pk=self.line_b.pk)
        self.assertIsNotNone(line_b.voided_at)
        self.assertEqual(line_b.amount, 1000)          # what it billed, kept
        inv = Invoice.objects.get(pk=self.inv.pk)
        self.assertEqual(inv.total_sar, 2000)
        self.assertEqual(fq.invoice_charged_sar(inv.pk), 2000)
        self.assertIsNone(ConfirmationLetter.objects.get(pk=self.cl_b.pk).invoice)
        # The journal lines of the old charge still point at the voided line.
        self.assertTrue(JournalLine.objects.filter(invoice_line_id=self.line_b.pk).exists())

    def test_reservation_with_money_on_it_cannot_leave_the_invoice(self):
        self._pay(self.inv, Reservation.objects.get(pk=self.line_b.pk), 400)
        resp = self._edit([self.cl_a.pk])
        self.assertIn('finance', resp.json()['props']['errors'])
        self.assertIsNone(InvoiceLine.objects.get(pk=self.line_b.pk).voided_at)
        self.assertEqual(Invoice.objects.get(pk=self.inv.pk).total_sar, 3000)

    def test_uncharged_line_is_simply_deleted(self):
        cl = self._cl('7202', price=0)
        line = self.inv.add_hotel_line(cl)       # bills 0, so the ledger never saw it
        self._edit([self.cl_a.pk, self.cl_b.pk])
        self.assertFalse(InvoiceLine.objects.filter(pk=line.pk).exists())

    def test_an_invoice_needs_a_client_and_a_reservation(self):
        resp = self._edit([])
        self.assertIn('reservations', resp.json()['props']['errors'])
        resp = self._edit([self.cl_a.pk], client_id='')
        # The client is resolved from the CL when the form leaves it blank.
        self.assertEqual(resp.status_code, 302)
        other = self._cl('7203', client=make_client('PT Lain'))
        resp = self._edit([self.cl_a.pk, other.pk])
        self.assertIn('reservations', resp.json()['props']['errors'])

    def test_invoice_with_lines_is_protected_from_deletion(self):
        with self.assertRaises(ProtectedError):
            self.inv.delete()


class ServiceLineTest(_Base):
    def setUp(self):
        super().setUp()
        self.inv = make_invoice(client=self.client_obj, invoice_type='visa', currency='USD',
                                invoice_number='SVC-1', issued_date=date(2026, 3, 1))
        self.visa = make_service_line(self.inv, name='Visa', qty=40, price=150)
        self.bus = make_service_line(self.inv, name='Bus', qty=1, price=500)
        posting.post_invoice_charge(self.inv, created_by=self.user)

    def _edit(self, rows, **extra):
        data = {
            'client_id': str(self.client_obj.pk), 'invoice_number': 'SVC-1', 'invoice_currency': 'USD',
            'issued_date': '2026-03-01', 'due_date': '2026-03-20', 'service_items': json.dumps(rows),
        }
        data.update(extra)
        return self.client.post(f'/services/{self.inv.pk}/edit/', data, HTTP_X_INERTIA='true')

    def test_service_lines_live_in_the_same_table(self):
        self.assertEqual(ServiceItem.objects.filter(invoice=self.inv).count(), 2)
        self.assertEqual(InvoiceLine.objects.filter(invoice=self.inv, kind='service').count(), 2)
        self.assertEqual((self.visa.service_number, self.visa.name, self.visa.qty, self.visa.price, self.visa.total),
                         (1, 'Visa', 40, 150, 6000))
        self.assertEqual(self.inv.total_sar, 6500)

    def test_edit_updates_lines_in_place(self):
        resp = self._edit([
            {'service_number': 1, 'name': 'Visa Umrah', 'qty': 42, 'price': 150},
            {'service_number': 2, 'name': 'Bus', 'qty': 1, 'price': 500},
        ])
        self.assertEqual(resp.status_code, 302)
        visa = InvoiceLine.objects.get(pk=self.visa.pk)
        self.assertEqual((visa.description, visa.quantity), ('Visa Umrah', 42))
        self.assertEqual(fq.invoice_charged_sar(self.inv.pk), 42 * 150 + 500)
        rev = self.inv.revisions.order_by('-revision_no').first()
        self.assertEqual((rev.reason, rev.total), ('line_change', 6800))

    def test_removing_the_first_row_does_not_shift_the_others(self):
        resp = self._edit([{'service_number': 2, 'name': 'Bus', 'qty': 1, 'price': 500}])
        self.assertEqual(resp.status_code, 302)
        self.assertIsNotNone(InvoiceLine.objects.get(pk=self.visa.pk).voided_at)   # charged, so voided
        bus = InvoiceLine.objects.get(pk=self.bus.pk)
        self.assertEqual((bus.description, bus.voided_at), ('Bus', None))
        self.assertEqual(Invoice.objects.get(pk=self.inv.pk).total_sar, 500)

    def test_new_rows_get_the_next_number(self):
        self._edit([
            {'service_number': 1, 'name': 'Visa', 'qty': 40, 'price': 150},
            {'service_number': 2, 'name': 'Bus', 'qty': 1, 'price': 500},
            {'name': 'Handling', 'qty': 40, 'price': 10},
        ])
        self.assertEqual(
            list(self.inv.service_items.values_list('line_no', 'description')),
            [(1, 'Visa'), (2, 'Bus'), (3, 'Handling')],
        )

    def test_services_invoice_needs_a_client_and_a_known_currency(self):
        resp = self._edit([{'name': 'Visa', 'qty': 1, 'price': 1}], client_id='')
        self.assertIn('client_id', resp.json()['props']['errors'])
        resp = self._edit([{'name': 'Visa', 'qty': 1, 'price': 1}], invoice_currency='EUR')
        self.assertIn('invoice_currency', resp.json()['props']['errors'])

    def test_new_services_invoice_is_issued_by_the_client_owner_branch(self):
        Client.objects.filter(pk=self.client_obj.pk).update(owner_branch_id='jkt')
        resp = self.client.post('/services/new/', {
            'client_id': str(self.client_obj.pk), 'invoice_number': 'SVC-2', 'invoice_currency': 'IDR',
            'issued_date': '2026-03-01', 'due_date': '2026-03-20',
            'service_items': json.dumps([{'name': 'Visa', 'qty': 2, 'price': 3_000_000}]),
        })
        self.assertEqual(resp.status_code, 302)
        inv = Invoice.objects.get(invoice_number='SVC-2')
        self.assertEqual((inv.branch_id, inv.currency, inv.total_sar), ('jkt', 'IDR', 6_000_000))


class CreditNoteLineTest(_Base):
    def test_credit_note_points_at_one_invoice_line(self):
        inv = make_invoice(client=self.client_obj, issued_date=date(2026, 3, 1))
        line = make_hotel_line(invoice=inv, reservation_number='7300', total_sar=5000)
        posting.post_invoice_charge(inv, created_by=self.user)
        cn = cns.issue_credit_note(
            inv, lines=[{'kind': 'reservation', 'id': line.pk, 'amount_sar': 1200}],
            reason='1 kamar batal', issued_date=date(2026, 3, 5), created_by=self.user,
        )
        cn_line = cn.lines.get()
        self.assertEqual(cn_line.invoice_line_id, line.pk)
        self.assertEqual(Invoice.objects.get(pk=inv.pk).due_sar, 3800)
        rev = inv.revisions.order_by('-revision_no').first()
        self.assertEqual((rev.reason, rev.total), ('credit_note', 3800))
        with self.assertRaises(ProtectedError):
            InvoiceLine.objects.get(pk=line.pk).delete()
