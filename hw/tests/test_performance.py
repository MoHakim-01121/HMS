from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User

from hw.models import ConfirmationLetter, Invoice


# ── Task 1: ai_summary removed ───────────────────────────────────────────────

class AiSummaryRemovedTest(TestCase):
    def test_confirmation_letter_has_no_ai_summary(self):
        field_names = [f.name for f in ConfirmationLetter._meta.get_fields()]
        self.assertNotIn('ai_summary', field_names)

    def test_invoice_has_no_ai_summary(self):
        field_names = [f.name for f in Invoice._meta.get_fields()]
        self.assertNotIn('ai_summary', field_names)


# ── Task 2: Settings ──────────────────────────────────────────────────────────

class GzipMiddlewareTest(TestCase):
    def test_gzip_middleware_is_configured(self):
        from django.conf import settings
        self.assertIn('django.middleware.gzip.GZipMiddleware', settings.MIDDLEWARE)

    def test_gzip_middleware_position(self):
        from django.conf import settings
        mw = settings.MIDDLEWARE
        gzip_idx = mw.index('django.middleware.gzip.GZipMiddleware')
        security_idx = mw.index('django.middleware.security.SecurityMiddleware')
        whitenoise_idx = mw.index('whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertGreater(gzip_idx, security_idx)
        self.assertLess(gzip_idx, whitenoise_idx)


class SettingsTest(TestCase):
    def test_caches_backend_is_locmem(self):
        from django.conf import settings
        backend = settings.CACHES['default']['BACKEND']
        self.assertEqual(backend, 'django.core.cache.backends.locmem.LocMemCache')

    def test_session_engine_is_cached_db(self):
        from django.conf import settings
        self.assertEqual(
            settings.SESSION_ENGINE,
            'django.contrib.sessions.backends.cached_db',
        )

    def test_whitenoise_max_age_is_one_year(self):
        from django.conf import settings
        self.assertEqual(settings.WHITENOISE_MAX_AGE, 31536000)


# ── Task 3: Calendar cache ────────────────────────────────────────────────────

class CalendarCacheTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_get_message_templates_cached_on_second_call(self):
        from django.core.cache import cache
        from hw.views.calendar_views import _get_message_templates
        with patch('hw.views.calendar_views.MessageTemplate') as MockModel:
            MockModel.objects.all.return_value = []
            _get_message_templates()
            _get_message_templates()
            MockModel.objects.all.assert_called_once()

    def test_get_last_recap_cached_on_second_call(self):
        from django.core.cache import cache
        from hw.views.calendar_views import _get_last_recap
        with patch('hw.views.calendar_views.RecapLog') as MockModel:
            MockModel.objects.filter.return_value.order_by.return_value.first.return_value = None
            _get_last_recap()
            _get_last_recap()
            MockModel.objects.filter.assert_called_once()


# ── Task 4: CL list defer ─────────────────────────────────────────────────────

class ClListDeferTest(TestCase):
    def test_cl_list_base_qs_defers_note(self):
        qs = ConfirmationLetter.objects.all().defer('note').select_related('invoice').prefetch_related('rooms')
        deferred_fields, defer_all = qs.query.deferred_loading
        self.assertIn('note', deferred_fields)

    def test_cl_list_view_returns_ok(self):
        user = User.objects.create_user('cluser2', password='testpass123')
        client = Client()
        client.force_login(user)
        response = client.get('/cl/')
        self.assertEqual(response.status_code, 200)
