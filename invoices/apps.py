"""
Invoice App Configuration
"""
from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    """Configuration for the invoices application"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invoices'
    verbose_name = 'Invoice Generator'
