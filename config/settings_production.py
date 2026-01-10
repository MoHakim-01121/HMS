"""
Production security configuration
Load this in production: export DJANGO_SETTINGS_MODULE=config.settings_production
"""
from .settings import *

# Override for production
DEBUG = False
ALLOWED_HOSTS = get_list_env('ALLOWED_HOSTS', [])

# Force HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# Disable browsable API in production
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    )
}

# Admin URL - change in production
ADMIN_URL = get_env_variable('ADMIN_URL', 'admin/')
