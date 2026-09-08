from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse

from inertia import render as inertia_render

from ..permissions import hide_unless


# Internal-only design-system preview. `hide_unless` answers 404 rather than a
# flash+redirect so the route's existence isn't advertised to non-admins, and
# still bounces anonymous visitors to the login page — same shape as
# health_check below.
@hide_unless('dev', 'view')
def style_guide(request):
    return inertia_render(request, "Dev/StyleGuide", props={})


def _db_ok():
    try:
        connection.ensure_connection()
        return True, None
    except Exception as exc:
        return False, str(exc)


def _cache_ok():
    try:
        from django.core.cache import cache
        cache.set('__healthcheck__', '1', 5)
        return cache.get('__healthcheck__') == '1', None
    except Exception as exc:
        return False, str(exc)


def _migrations_pending():
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return len(plan), None
    except Exception as exc:
        return None, str(exc)


def health_check(request):
    """Unauthenticated liveness probe for load balancers / uptime monitors.

    Checks the database connection, the cache backend, and whether any
    migrations are pending. Returns HTTP 200 when healthy, 500 otherwise.
    Deliberately exposes no business data.
    """
    db_ok, db_err = _db_ok()
    cache_ok, cache_err = _cache_ok()
    pending, mig_err = _migrations_pending()

    payload = {
        "status": "ok" if (db_ok and cache_ok and pending in (None, 0)) else "error",
        "db": "ok" if db_ok else "unreachable",
        "cache": "ok" if cache_ok else "unreachable",
        "migrations_pending": pending,
    }
    if db_err:
        payload["db_error"] = db_err
    if cache_err:
        payload["cache_error"] = cache_err
    if mig_err:
        payload["migrations_error"] = mig_err

    status = 200 if payload["status"] == "ok" else 500
    return JsonResponse(payload, status=status)
