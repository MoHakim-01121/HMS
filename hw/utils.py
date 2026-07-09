from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value):
    """Round to the nearest whole number, ties rounding up — matches Django's
    `floatformat` template filter, unlike Python's built-in round() which
    rounds ties to even (e.g. round(1040.5) == 1040, round_half_up(1040.5) == 1041).
    """
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def convert_to_sar(amount, currency, exchange_rate):
    if currency == "SAR":
        return amount
    elif currency == "IDR":
        return amount / exchange_rate if exchange_rate != 0 else 0
    else:  # USD or others
        return amount * exchange_rate


def format_currency(amount):
    return f"{int(round(amount)):,}"
