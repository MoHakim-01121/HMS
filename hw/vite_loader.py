from urllib.parse import urljoin

from django.conf import settings
from django_vite.core.asset_loader import DjangoViteAppClient


class FixedDjangoViteAppClient(DjangoViteAppClient):
    def get_dev_server_url(self, path: str) -> str:
        if self.static_url_prefix:
            static_url_base = urljoin(settings.STATIC_URL, self.static_url_prefix)
            if not static_url_base.endswith("/"):
                static_url_base += "/"
            base = urljoin(static_url_base, path)
        else:
            base = path if path.startswith("/") else f"/{path}"

        return urljoin(
            f"{self.dev_server_protocol}://{self.dev_server_host}:{self.dev_server_port}",
            base,
        )
    def get_production_server_url(self, path: str) -> str:
        # Vite names already carry a content hash, and its chunks import each
        # other by those names ("./main-XXXX.js"). Asking the static storage
        # would hand the page WhiteNoise's second hash (main-XXXX.<md5>.js), so
        # the browser loads main twice as two modules: two React copies, two
        # LocaleContexts, and pages read "{c}, {n} accounts" untranslated
        # (prod 2026-11-03). Serve Vite's own names.
        static_url_base = urljoin(settings.STATIC_URL, self.static_url_prefix)
        if not static_url_base.endswith("/"):
            static_url_base += "/"
        return urljoin(static_url_base, path)
