from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value):
    """Round to the nearest whole number, ties rounding up — matches Django's
    `floatformat` template filter, unlike Python's built-in round() which
    rounds ties to even (e.g. round(1040.5) == 1040, round_half_up(1040.5) == 1041).
    """
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


# Currencies money can be recorded in. convert_to_sar treats anything that is
# not SAR/IDR as a multiply-rate currency, so an unknown code must be refused
# at the boundary instead of silently converted like USD.
CURRENCIES = ('SAR', 'IDR', 'USD')


def convert_to_sar(amount, currency, exchange_rate):
    """Nilai SAR utuh dari `amount` (satuan utuh `currency`).

    Dihitung dengan Decimal dan dibulatkan setengah ke atas — bukan float dan
    bukan round() bawaan (ties-to-even: IDR 2.450 / 4.900 = 0,5 → 0, harusnya 1).
    Rupiah dikutip per 1 SAR (dibagi), mata uang lain dalam SAR per unit (dikali).
    """
    amount = Decimal(str(amount))
    rate = Decimal(str(exchange_rate))
    if currency == "SAR":
        value = amount
    elif currency == "IDR":
        if rate == 0:
            return 0
        value = amount / rate
    else:  # USD or others
        value = amount * rate
    return round_half_up(value)


def format_currency(amount):
    return f"{round_half_up(amount):,}"
