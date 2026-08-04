from django_vite.core.asset_loader import DjangoViteAppClient, DjangoViteConfig
from urllib.parse import urljoin
from django.conf import settings


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