import logging

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse

logger = logging.getLogger(__name__)


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
    # The probe is public: error details (hosts, users, paths) go to the log,
    # never into the response.
    for name, err in (('db', db_err), ('cache', cache_err), ('migrations', mig_err)):
        if err:
            logger.error('health_check %s: %s', name, err)

    status = 200 if payload["status"] == "ok" else 500
    return JsonResponse(payload, status=status)
