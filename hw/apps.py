from django.apps import AppConfig


class HwConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hw'
    verbose_name = 'H Workspace'

    def ready(self):
        import hw.signals  # noqa: F401 — registers signal handlers
