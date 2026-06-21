"""Handle expired-session redirects for Inertia (XHR) requests.

When a user's session expires, ``@login_required`` answers with a 302 redirect
to ``LOGIN_URL``. For a normal browser navigation that is fine, but for an
Inertia request (``X-Inertia`` header) axios silently follows the redirect and
receives the plain-HTML login page, which has no ``X-Inertia`` header. The
Inertia client then throws "All Inertia requests must receive a valid Inertia
response" and the user is stuck on a broken screen instead of being sent to the
login page.

This middleware converts that one case into a ``409 Conflict`` carrying an
``X-Inertia-Location`` header, which tells the Inertia client to perform a full
page visit to the login page — a clean redirect. Only redirects whose target is
the login page are touched; ordinary Inertia redirects (e.g. after saving a
form) are left untouched so the client follows them normally.

Must run *before* ``InertiaMiddleware`` in ``MIDDLEWARE`` so that, on the
response trip, it sees the final response after InertiaMiddleware has handled it.
"""
from django.conf import settings
from django.http import HttpResponse

REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class InertiaAuthRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._login_path = str(settings.LOGIN_URL).split("?")[0].rstrip("/")

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.headers.get("X-Inertia")
            and response.status_code in REDIRECT_STATUSES
            and response.has_header("Location")
        ):
            location = response["Location"]
            target_path = location.split("?")[0].rstrip("/")
            if target_path == self._login_path:
                conflict = HttpResponse(status=409)
                conflict["X-Inertia-Location"] = location
                return conflict

        return response
