from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invoices'
    verbose_name = 'Invoice Generator'

    def ready(self):
        import invoices.signals  # noqa: F401 — registers signal handlers
