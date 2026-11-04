"""Umrah seasons: a named date range for reports over monthly periods.

The books close month by month (FinancialPeriod); a Season only names the
range. Saving one adds the monthly periods it needs, since every posting date
must fall in a period.
"""
from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from hw.finance import seasons
from hw.models.period import FinancialPeriod, Season
from hw.tests.factories import make_invoice


def _names():
    return list(FinancialPeriod.objects.order_by('date_from').values_list('name', flat=True))


class EnsureMonthlyPeriodsTest(TestCase):
    def test_creates_every_month_the_range_touches(self):
        created = seasons.ensure_monthly_periods(date(2026, 6, 15), date(2026, 9, 10))
        self.assertEqual([p.name for p in created], ['2026-06', '2026-07', '2026-08', '2026-09'])
        june = FinancialPeriod.objects.get(name='2026-06')
        self.assertEqual((june.date_from, june.date_to), (date(2026, 6, 1), date(2026, 6, 30)))

    def test_leaves_existing_periods_alone_whatever_their_name(self):
        FinancialPeriod.objects.create(name='May 2026', date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
        created = seasons.ensure_monthly_periods(date(2026, 5, 1), date(2026, 6, 30))
        self.assertEqual([p.name for p in created], ['2026-06'])
        self.assertEqual(_names(), ['May 2026', '2026-06'])


class SaveSeasonTest(TestCase):
    def _save(self, season=None, name='Musim 1448H', date_from=date(2026, 6, 1), date_to=date(2027, 3, 31)):
        return seasons.save_season(season, name=name, date_from=date_from, date_to=date_to)

    def test_create_adds_the_months_it_needs(self):
        s = self._save()
        self.assertEqual((s.name, s.date_from, s.date_to), ('Musim 1448H', date(2026, 6, 1), date(2027, 3, 31)))
        self.assertEqual(len(_names()), 10)
        self.assertEqual((_names()[0], _names()[-1]), ('2026-06', '2027-03'))

    def test_widening_a_season_adds_the_new_months_only(self):
        s = self._save()
        self._save(s, date_to=date(2027, 5, 15))
        self.assertEqual(_names()[-2:], ['2027-04', '2027-05'])
        self.assertEqual(Season.objects.count(), 1)

    def test_refuses_overlap_bad_range_blank_and_duplicate_name(self):
        self._save()
        for kwargs in (
            {'name': 'Musim lain', 'date_from': date(2027, 3, 1), 'date_to': date(2027, 12, 31)},  # overlap
            {'name': 'Mundur', 'date_from': date(2028, 5, 1), 'date_to': date(2028, 1, 1)},
            {'name': '  ', 'date_from': date(2028, 1, 1), 'date_to': date(2028, 5, 1)},
            {'name': 'musim 1448h', 'date_from': date(2028, 1, 1), 'date_to': date(2028, 5, 1)},
            {'name': 'Tanpa tanggal', 'date_from': None, 'date_to': date(2028, 5, 1)},
        ):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                with self.assertRaises(ValidationError):
                    self._save(**kwargs)
        self.assertEqual(Season.objects.count(), 1)

    def test_refused_season_creates_no_months(self):
        self._save()
        with self.assertRaises(ValidationError):
            self._save(name='Tumpang', date_from=date(2027, 3, 1), date_to=date(2027, 8, 31))
        self.assertNotIn('2027-08', _names())


class SeasonOwnsItsDocumentsTest(TestCase):
    """A season made after invoices exist (prod right after cutover) takes
    them in, so numbering goes on from the last one instead of INV-001."""

    def test_existing_invoices_join_and_numbering_goes_on(self):
        from hw.models.invoice import Invoice
        old = make_invoice(invoice_number='INV-107', issued_date=date(2026, 10, 2))
        before = make_invoice(invoice_number='INV-050', issued_date=date(2026, 4, 1))
        season = seasons.save_season(name='Musim 1448H', date_from=date(2026, 5, 31), date_to=date(2027, 5, 19))
        old.refresh_from_db()
        before.refresh_from_db()
        self.assertEqual((old.season_id, before.season_id), (season.pk, None))
        self.assertEqual(Invoice.suggest_number('hotel', date(2026, 11, 3)), 'INV-108')
        # Narrowing the season lets go of what is now outside it.
        seasons.save_season(season, name='Musim 1448H', date_from=date(2026, 11, 1), date_to=date(2027, 5, 19))
        old.refresh_from_db()
        self.assertIsNone(old.season_id)


class SeasonViewsTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('sv', password='pw12345'))

    def test_create_edit_delete(self):
        self.client.post('/finance/seasons/create/', {'name': 'Musim 1448H', 'date_from': '2026-06-01', 'date_to': '2027-03-31'})
        s = Season.objects.get()
        self.client.post(f'/finance/seasons/{s.pk}/edit/', {'name': 'Musim 1448 H', 'date_from': '2026-06-01', 'date_to': '2027-04-30'})
        s.refresh_from_db()
        self.assertEqual((s.name, s.date_to), ('Musim 1448 H', date(2027, 4, 30)))
        self.client.post(f'/finance/seasons/{s.pk}/delete/')
        self.assertFalse(Season.objects.exists())
        # The months stay: they hold the books.
        self.assertEqual(len(_names()), 11)

    def test_a_season_with_invoices_cannot_be_deleted(self):
        season = Season.objects.create(
            name='Musim 1448H', date_from=date(2026, 6, 1), date_to=date(2027, 5, 31),
        )
        make_invoice(invoice_number='INV-001', issued_date=date(2026, 6, 2))

        response = self.client.post(f'/finance/seasons/{season.pk}/delete/')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Season.objects.filter(pk=season.pk).exists())
        flash = self.client.get('/finance/periods/', HTTP_X_INERTIA='true').json()['props']['flash']
        self.assertIn('cannot be deleted', flash['error'])

    def test_refused_season_flashes_the_reason(self):
        self.client.post('/finance/seasons/create/', {'name': 'X', 'date_from': '2026-06-01', 'date_to': '2026-05-01'})
        self.assertFalse(Season.objects.exists())
        flash = self.client.get('/finance/periods/', HTTP_X_INERTIA='true').json()['props']['flash']
        self.assertIn('setelah tanggal mulai', flash['error'])

    def test_reports_offer_the_seasons(self):
        seasons.save_season(name='Musim 1448H', date_from=date(2026, 6, 1), date_to=date(2027, 3, 31))
        want = [{'id': Season.objects.get().pk, 'name': 'Musim 1448H', 'date_from': '2026-06-01', 'date_to': '2027-03-31'}]
        for url in ('/finance/trial-balance/', '/finance/fund-flow/', '/finance/periods/'):
            with self.subTest(url=url):
                props = self.client.get(url, HTTP_X_INERTIA='true').json()['props']
                self.assertEqual(props['seasons'], want)

    def test_cl_and_invoice_lists_read_a_whole_season(self):
        seasons.save_season(name='Musim 1448H', date_from=date(2026, 6, 1), date_to=date(2027, 3, 31))
        for url in ('/cl/', '/invoice/'):
            with self.subTest(url=url):
                props = self.client.get(url, {'season': 'Musim 1448H'}, HTTP_X_INERTIA='true').json()['props']
                self.assertEqual(props['seasons'], [{'name': 'Musim 1448H', 'from': '2026-06-01', 'to': '2027-03-31'}])
                self.assertEqual((props['filters']['season'], props['filters']['month']), ('Musim 1448H', ''))
                self.assertIn('date_from=2026-06-01', props['export_qs'])
                self.assertIn('date_to=2027-03-31', props['export_qs'])
                # An unknown season falls back to the current month.
                props = self.client.get(url, {'season': 'Nope'}, HTTP_X_INERTIA='true').json()['props']
                self.assertEqual(props['filters']['season'], '')
                self.assertTrue(props['filters']['month'])


class PeriodCreateTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('pcr', password='pw12345'))

    def test_year_fills_in_around_periods_named_otherwise(self):
        # Used to 500: the month was looked up by name, its dates then clashed.
        FinancialPeriod.objects.create(name='May 2026', date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
        resp = self.client.post('/finance/periods/create/', {'year': '2026'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FinancialPeriod.objects.count(), 12)
        self.client.post('/finance/periods/create/', {'year': '2026'})
        self.assertEqual(FinancialPeriod.objects.count(), 12)

    def test_bad_year_is_refused(self):
        self.client.post('/finance/periods/create/', {'year': '99999'})
        self.assertFalse(FinancialPeriod.objects.exists())
