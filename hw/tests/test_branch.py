"""FASE A — Branch foundation."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch, Client
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance.hashing import verify_chain
from hw.tests.factories import make_hotel_line, make_invoice


class BranchSeedTest(TestCase):
    def test_migration_seeded_three_branches(self):
        self.assertEqual(
            set(Branch.objects.values_list('code', flat=True)),
            {'sby', 'jkt', 'pusat'},
        )

    def test_only_surabaya_and_pusat_active(self):
        self.assertTrue(Branch.objects.get(code='sby').is_active)
        self.assertTrue(Branch.objects.get(code='pusat').is_active)
        self.assertFalse(Branch.objects.get(code='jkt').is_active)


class BranchAccessTest(TestCase):
    def test_all_returns_every_active_branch(self):
        u = User.objects.create_user('a', password='pw12345')
        self.assertEqual(u.profile.branch_access, 'all')
        self.assertCountEqual(u.profile.branches, ['sby', 'pusat'])
        self.assertTrue(u.profile.has_all_branches)

    def test_scoped_profile_sees_one_branch(self):
        u = User.objects.create_user('b', password='pw12345')
        u.profile.branch_access = 'sby'
        u.profile.save(update_fields=['branch_access'])
        self.assertEqual(u.profile.branches, ['sby'])
        self.assertFalse(u.profile.has_all_branches)


class ReservationOwnerBranchTest(TestCase):
    def test_line_belongs_to_the_issuing_branch_of_its_invoice(self):
        inv = make_invoice(invoice_number='INV-B-1', customer_name='X')
        r = make_hotel_line(invoice=inv, reservation_number='R1', total_sar=1000)
        self.assertEqual((inv.branch_id, r.owner_branch_id), ('sby', 'sby'))


class JournalBranchDimensionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('t', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT Branch')

    def test_post_entry_persists_branch_dimension(self):
        entry = posting.post_entry(
            entry_type=posting.JournalEntry.TYPE_ADJUSTMENT,
            description='branch dim test',
            entry_date=date(2026, 1, 10),
            lines=[
                {'account': 'cash_sby', 'debit': 500, 'branch': 'sby'},
                {'account': 'equity', 'credit': 500, 'branch': 'sby'},
            ],
            created_by=self.user,
        )
        self.assertTrue(all(l.branch_id == 'sby' for l in entry.lines.all()))

    def test_branch_tagged_entry_keeps_hash_chain_intact(self):
        posting.post_entry(
            entry_type=posting.JournalEntry.TYPE_ADJUSTMENT,
            description='chain test',
            entry_date=date(2026, 1, 11),
            lines=[
                {'account': 'cash_sby', 'debit': 100, 'branch': 'sby'},
                {'account': 'equity', 'credit': 100},
            ],
            created_by=self.user,
        )
        self.assertEqual(verify_chain(), [])
