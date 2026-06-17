from .settings import *

DEBUG = False
ALLOWED_HOSTS = get_list_env('ALLOWED_HOSTS', [])

# Always use the built Vite manifest in production (never the dev server),
# regardless of the DEBUG value present when settings.py was imported.
DJANGO_VITE['default']['dev_mode'] = False

# Nginx handles HTTPS termination, Django does not redirect
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

ADMIN_URL = get_env_variable('ADMIN_URL', 'admin/')
