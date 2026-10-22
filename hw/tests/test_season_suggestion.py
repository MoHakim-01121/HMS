"""Musim berikutnya dihitung dari kalender Umm al-Qura (keputusan user
2026-10-20): mulai 14 Dzulhijjah, tepat setelah haji, dan bersambung sampai
sehari sebelum musim berikutnya."""
from datetime import date

from django.test import TestCase

from hw.finance.seasons import save_season, suggest_next_season


class SeasonSuggestionTest(TestCase):
    def test_first_season_is_the_one_running_today(self):
        s = suggest_next_season(today=date(2026, 10, 20))     # 9 Jumadil Awal 1448
        self.assertEqual(s, {'name': 'Musim 1448H', 'date_from': date(2026, 5, 31), 'date_to': date(2027, 5, 19)})

    def test_before_the_season_opens_it_is_last_years(self):
        s = suggest_next_season(today=date(2026, 5, 30))      # 13 Dzulhijjah 1447
        self.assertEqual((s['name'], s['date_from']), ('Musim 1447H', date(2025, 6, 10)))

    def test_next_season_follows_the_last_one(self):
        save_season(name='Musim 1448H', date_from=date(2026, 5, 31), date_to=date(2027, 5, 19))
        s = suggest_next_season(today=date(2026, 10, 20))
        self.assertEqual(s, {'name': 'Musim 1449H', 'date_from': date(2027, 5, 20), 'date_to': date(2028, 5, 8)})

    def test_follows_a_season_whose_end_was_moved(self):
        save_season(name='1448', date_from=date(2026, 5, 31), date_to=date(2027, 4, 7))   # ended at 30 Syawal
        s = suggest_next_season(today=date(2026, 10, 20))
        self.assertEqual((s['name'], s['date_from']), ('Musim 1449H', date(2027, 4, 8)))


class PeriodPageSuggestsSeasonTest(TestCase):
    def test_period_page_carries_the_suggestion(self):
        import json

        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('season-admin', password='pw12345'))
        props = json.loads(self.client.get('/finance/periods/').context['page'])['props']
        self.assertRegex(props['next_season']['name'], r'^Musim 14\d\dH$')
        self.assertLess(props['next_season']['date_from'], props['next_season']['date_to'])
