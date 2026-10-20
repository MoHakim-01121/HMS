from django.test import TestCase


class SharedCacheBackendTest(TestCase):
    def test_cache_backend_is_shared_across_processes(self):
        from django.conf import settings
        backend = settings.CACHES['default']['BACKEND']
        self.assertEqual(
            backend, 'django.core.cache.backends.db.DatabaseCache',
            "The app cache must be shared "
            "across gunicorn workers, not per-process LocMemCache."
        )
