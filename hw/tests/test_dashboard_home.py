"""The Manager dashboard's period rules (dashboard.home_period)."""
from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from hw.dashboard import _sales_side, home_period
from hw.models import ConfirmationLetter


class HomePeriodTest(TestCase):
    def test_running_month_compares_the_same_days_of_the_month_before(self):
        per = home_period(date(2026, 10, 19))
        self.assertEqual((per['start'], per['end']), (date(2026, 10, 1), date(2026, 10, 19)))
        self.assertEqual((per['prev_start'], per['prev_end']), (date(2026, 9, 1), date(2026, 9, 19)))
        self.assertEqual(per['prev_label'], '1 to 19 Sep')
        self.assertTrue(per['running'])

    def test_running_month_stops_at_the_end_of_a_shorter_month_before(self):
        per = home_period(date(2026, 3, 31))
        self.assertEqual(per['prev_end'], date(2026, 2, 28))

    def test_past_month_compares_the_whole_month_before(self):
        per = home_period(date(2026, 10, 19), month=date(2026, 8, 1))
        self.assertEqual((per['start'], per['end']), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual((per['prev_start'], per['prev_end']), (date(2026, 7, 1), date(2026, 7, 31)))
        self.assertEqual(per['prev_label'], 'July')
        self.assertFalse(per['running'])

    def test_a_future_month_falls_back_to_this_one(self):
        per = home_period(date(2026, 10, 19), month=date(2027, 1, 1))
        self.assertEqual(per['start'], date(2026, 10, 1))

    def test_season_without_a_season_on_file_reads_the_month(self):
        per = home_period(date(2026, 10, 19), season=True)
        self.assertEqual(per['kind'], 'month')


class RoomNightsSoldTest(TestCase):
    """Room nights on the dashboard are the nights sold: every night of a CL
    counts in the period it was sold, whenever the stay is (user decision
    2026-11-01)."""

    def setUp(self):
        from hw.models import RoomType
        from hw.tests.factories import make_cl
        self.cl = make_cl(check_in=date(2027, 1, 10), check_out=date(2027, 1, 14))
        room_type = RoomType.objects.create(hotel=self.cl.hotel, name='Quad', capacity=4)
        self.cl.rooms.create(room_type_ref=room_type, quantity=2, price=100)
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(
            created_at=timezone.make_aware(datetime(2026, 10, 5, 10)))

    def side(self, start, end):
        return _sales_side(ConfirmationLetter.objects.all(), start, end)

    def test_all_nights_count_in_the_month_sold(self):
        out = self.side(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(out['rn'], 8)
        self.assertEqual(out['spark']['rn'][-1], 8)

    def test_nothing_counts_in_the_month_of_the_stay(self):
        self.assertEqual(self.side(date(2027, 1, 1), date(2027, 1, 31))['rn'], 0)

    def test_a_cancelled_cl_sells_no_nights(self):
        ConfirmationLetter.objects.filter(pk=self.cl.pk).update(reservation_status='CANCELLED')
        self.assertEqual(self.side(date(2026, 10, 1), date(2026, 10, 31))['rn'], 0)


class HomeVariantTest(TestCase):
    """One dashboard per role (HMS Dashboard canvas: Manager, Finance, Admin,
    Staff and Viewer), each reading only what the role may view."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from hw.models import UserProfile
        from hw.models.user import Role

        def user(name, role, superuser=False):
            u = User.objects.create_user(name, password='pw12345', is_superuser=superuser, is_staff=superuser)
            UserProfile.objects.update_or_create(user=u, defaults={'role': role, 'all_branches': True})
            u.refresh_from_db()
            return u

        cls.admin = user('adm', Role.ADMIN.value, superuser=True)
        cls.finance = user('fin', Role.FINANCE.value)
        cls.manager = user('mgr', Role.MANAGER.value)
        cls.staff = user('stf', Role.STAFF.value)
        cls.viewer = user('vwr', Role.VIEWER.value)
        from hw.tests.factories import make_cl
        make_cl(salesperson=cls.staff)
        make_cl()

    def home(self, user):
        from hw.dashboard import home
        return home(user, date.today())

    def test_each_role_gets_its_own_dashboard(self):
        for user, variant in ((self.admin, 'admin'), (self.finance, 'finance'), (self.manager, 'manager'),
                              (self.staff, 'staff'), (self.viewer, 'viewer')):
            self.assertEqual(self.home(user)['variant'], variant, user.username)

    def test_staff_count_every_cl_of_their_branch(self):
        self.assertEqual(self.home(self.staff)['sales']['cur']['cl'], 2)
        self.assertEqual(self.home(self.viewer)['sales']['cur']['cl'], 2)

    def test_viewer_reads_only_and_has_no_to_do(self):
        out = self.home(self.viewer)
        self.assertNotIn('todo', out)
        self.assertNotIn('my_payments', out)
        self.assertIn('todo', self.home(self.staff))

    def test_finance_gets_money_blocks_not_sales(self):
        out = self.home(self.finance)
        self.assertNotIn('sales', out)
        for key in ('received', 'cash', 'flow', 'receivable', 'chase', 'todo'):
            self.assertIn(key, out)

    def test_only_the_administrator_sees_users_and_access(self):
        self.assertIn('people', self.home(self.admin))
        self.assertNotIn('people', self.home(self.manager))


class StaffTodoTest(TestCase):
    """A staff member's To do tells the same story as the bell: today's
    check-ins and the hotel invoices due this week (2026-10-22)."""

    def setUp(self):
        from datetime import timedelta

        from django.contrib.auth.models import User

        from hw.models import UserProfile
        from hw.models.user import Role
        from hw.tests.factories import make_cl, make_hotel_line, make_invoice
        self.today = date.today()
        self.staff = User.objects.create_user('stf2', password='pw12345')
        UserProfile.objects.update_or_create(user=self.staff, defaults={'role': Role.STAFF.value, 'all_branches': True})
        self.staff.refresh_from_db()
        make_cl(guest_name='Arrives Today', check_in=self.today, check_out=self.today + timedelta(days=3))
        inv = make_invoice(customer_name='Owes Soon', due_date=self.today + timedelta(days=3))
        make_hotel_line(inv, total_sar=1000, check_in=self.today + timedelta(days=20))

    def todo(self):
        from hw.dashboard import home
        return {x['key']: x for x in home(self.staff, self.today)['todo']}

    def test_check_ins_today_are_on_the_list(self):
        item = self.todo()['checkin_today']
        self.assertEqual((item['count'], item['first']), (1, 'Arrives Today'))

    def test_invoices_due_this_week_are_on_the_list(self):
        item = self.todo()['due_week']
        self.assertEqual((item['count'], item['nearest']['client']), (1, 'Owes Soon'))
        self.assertGreater(item['amount'], 0)
