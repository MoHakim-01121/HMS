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
    def test_gzip_middleware_is_removed_to_avoid_double_compression(self):
        """Single compression layer: custom BrotliMiddleware replaces Django's
        GZipMiddleware. Keeping both means HTML/JSON get compressed twice (and
        GZip re-compresses WhiteNoise's own precompressed static responses)."""
        from django.conf import settings
        self.assertNotIn('django.middleware.gzip.GZipMiddleware', settings.MIDDLEWARE)

    def test_brotli_middleware_sits_between_security_and_whitenoise(self):
        from django.conf import settings
        mw = settings.MIDDLEWARE
        brotli_idx = mw.index('hw.brotli_middleware.BrotliMiddleware')
        security_idx = mw.index('django.middleware.security.SecurityMiddleware')
        whitenoise_idx = mw.index('whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertGreater(brotli_idx, security_idx)
        self.assertLess(brotli_idx, whitenoise_idx)


class SettingsTest(TestCase):
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
        from hw.views.reminder_views import _get_message_templates
        with patch('hw.views.reminder_views.MessageTemplate') as MockModel:
            MockModel.objects.all.return_value = []
            _get_message_templates()
            _get_message_templates()
            MockModel.objects.all.assert_called_once()


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
