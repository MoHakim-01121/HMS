def convert_to_sar(amount, currency, exchange_rate):
    if currency == "SAR":
        return amount
    elif currency == "IDR":
        return amount / exchange_rate if exchange_rate != 0 else 0
    else:  # USD or others
        return amount * exchange_rate


def format_currency(amount):
    return f"{int(round(amount)):,}"
