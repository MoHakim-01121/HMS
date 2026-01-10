"""
Utility functions for invoice processing
"""
from datetime import datetime


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
