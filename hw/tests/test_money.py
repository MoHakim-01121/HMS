"""hw.money — satuan terkecil, arah kurs, dan pembulatan setengah ke atas."""
from decimal import Decimal

from django.test import SimpleTestCase

from hw.money import (
    FROM_PER_TO, TO_PER_FROM, MoneyError, convert, from_minor, market_quote, to_minor,
)


class MinorUnitTest(SimpleTestCase):
    def test_to_minor_per_currency(self):
        self.assertEqual(to_minor(Decimal('7200.50'), 'SAR'), 720050)
        self.assertEqual(to_minor(Decimal('35280000'), 'IDR'), 35280000)
        self.assertEqual(to_minor(Decimal('150.25'), 'USD'), 15025)

    def test_to_minor_rounds_half_up(self):
        self.assertEqual(to_minor(Decimal('0.005'), 'SAR'), 1)
        self.assertEqual(to_minor(Decimal('1040.5'), 'IDR'), 1041)

    def test_from_minor(self):
        self.assertEqual(from_minor(720050, 'SAR'), Decimal('7200.50'))
        self.assertEqual(from_minor(35280000, 'IDR'), Decimal('35280000'))

    def test_unknown_currency_refused(self):
        with self.assertRaises(MoneyError):
            to_minor(1, 'EUR')


class ConvertTest(SimpleTestCase):
    def test_idr_to_sar_divides_by_market_quote(self):
        # Rp35.280.000 dengan kurs 4.900 IDR per SAR = SAR 7.200,00 tepat.
        self.assertEqual(convert(35280000, 'IDR', 'SAR', rate=4900), 720000)

    def test_idr_to_sar_rounds_half_up_on_halala(self):
        # Rp100 / 3 = SAR 33,333… → 3.333 halala; Rp5 / 1000 = 0,005 → 1 halala.
        self.assertEqual(convert(100, 'IDR', 'SAR', rate=3), 3333)
        self.assertEqual(convert(5, 'IDR', 'SAR', rate=1000), 1)

    def test_usd_to_sar_multiplies(self):
        self.assertEqual(convert(10000, 'USD', 'SAR', rate=Decimal('3.75')), 37500)

    def test_usd_to_idr_multiplies(self):
        self.assertEqual(convert(10000, 'USD', 'IDR', rate=17500), 1750000)

    def test_sar_to_idr_multiplies_market_quote(self):
        # Biaya menyetor SAR 7.200 dengan kurs beli 4.750.
        self.assertEqual(convert(720000, 'SAR', 'IDR', rate=4750), 34200000)

    def test_same_currency(self):
        self.assertEqual(convert(500, 'SAR', 'SAR', rate=1), 500)
        with self.assertRaises(MoneyError):
            convert(500, 'SAR', 'SAR', rate=2)

    def test_explicit_direction_overrides_market_quote(self):
        self.assertEqual(convert(10000, 'USD', 'SAR', rate=Decimal('3.75'), rate_is=TO_PER_FROM), 37500)
        self.assertEqual(convert(37500, 'SAR', 'USD', rate=Decimal('3.75'), rate_is=FROM_PER_TO), 10000)

    def test_rejects_bad_input(self):
        with self.assertRaises(MoneyError):
            convert(100, 'IDR', 'SAR', rate=0)
        with self.assertRaises(MoneyError):
            convert(100.0, 'IDR', 'SAR', rate=4900)

    def test_market_quote_directions(self):
        self.assertEqual(market_quote('IDR', 'SAR'), FROM_PER_TO)
        self.assertEqual(market_quote('USD', 'IDR'), TO_PER_FROM)
        self.assertEqual(market_quote('USD', 'SAR'), TO_PER_FROM)
        self.assertEqual(market_quote('SAR', 'USD'), FROM_PER_TO)


class ConvertToSarTest(SimpleTestCase):
    """hw.utils.convert_to_sar — jalur nilai SAR utuh pembayaran & expense."""

    def test_idr_tie_rounds_half_up(self):
        from hw.utils import convert_to_sar
        # round() bawaan (ties-to-even) memberi 0 dan 2.
        self.assertEqual(convert_to_sar(2450, 'IDR', 4900), 1)
        self.assertEqual(convert_to_sar(7350, 'IDR', 4900), 2)
        self.assertEqual(convert_to_sar(12250, 'IDR', 4900), 3)

    def test_exact_and_float_rates(self):
        from hw.utils import convert_to_sar
        self.assertEqual(convert_to_sar(35280000, 'IDR', 4900), 7200)
        self.assertEqual(convert_to_sar(35280000, 'IDR', Decimal('4900.0000')), 7200)
        self.assertEqual(convert_to_sar(100, 'USD', 3.75), 375)
        self.assertEqual(convert_to_sar(2, 'USD', Decimal('3.75')), 8)   # 7,5 → 8
        self.assertEqual(convert_to_sar(500, 'SAR', 1), 500)

    def test_zero_idr_rate_gives_zero(self):
        from hw.utils import convert_to_sar
        self.assertEqual(convert_to_sar(1000, 'IDR', 0), 0)
