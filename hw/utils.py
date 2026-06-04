"""
Utility functions for invoice processing
"""
from datetime import date, datetime

from django.db import transaction


def parse_date(date_str):
    """
    Parse date string from HTML date input (YYYY-MM-DD) to DD/MM/YYYY format
    
    Args:
        date_str (str): Date string in YYYY-MM-DD format
        
    Returns:
        str or None: Formatted date string or None if invalid
    """
    if not date_str or not date_str.strip():
        return None
    
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return None


def convert_to_sar(amount, currency, exchange_rate):
    """
    Convert amount to SAR based on currency
    
    Args:
        amount (float): Amount to convert
        currency (str): Currency code (SAR, USD, IDR)
        exchange_rate (float): Exchange rate
        
    Returns:
        float: Amount in SAR
    """
    if currency == "SAR":
        return amount
    elif currency == "IDR":
        return amount / exchange_rate if exchange_rate != 0 else 0
    else:  # USD or others
        return amount * exchange_rate


def format_currency(amount):
    """
    Format amount with thousand separators

    Args:
        amount (int/float): Amount to format

    Returns:
        str: Formatted amount string
    """
    return f"{int(round(amount)):,}"


def next_sequence_number(qs, field, prefix):
    """Return next sequential string like '{prefix}-YYYYMM-NNN'.

    Wrapped in transaction.atomic() + select_for_update() to prevent duplicate
    numbers under concurrent requests (effective on PostgreSQL; no-op on SQLite).
    """
    with transaction.atomic():
        ym = date.today().strftime('%Y%m')
        pattern = f"{prefix}-{ym}-"
        nums = []
        for obj in qs.select_for_update().filter(**{f"{field}__startswith": pattern}):
            try:
                nums.append(int(getattr(obj, field).split('-')[-1]))
            except (ValueError, IndexError):
                pass
        return f"{prefix}-{ym}-{(max(nums) + 1 if nums else 1):03d}"
