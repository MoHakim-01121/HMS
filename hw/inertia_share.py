"""Share common props with every Inertia response.

Django context processors don't run for Inertia JSON responses, so the data the
shell needs on every page (the authenticated user + the due-soon notifications)
is shared here instead. Must run after InertiaMiddleware (which sets up the
share storage) and after AuthenticationMiddleware (which sets request.user).
"""
from django.contrib.messages import get_messages
from inertia import share

from .context_processors import due_soon


def _flash(request):
    success = error = None
    for m in get_messages(request):  # iterating consumes the message store
        if m.level_tag == "error":
            error = m.message
        elif m.level_tag in ("success", "info"):
            success = m.message
    return {"success": success, "error": error}


def _avatar_url(user):
    profile = getattr(user, "profile", None)
    avatar = getattr(profile, "avatar", None)
    try:
        return avatar.url if avatar else None
    except ValueError:
        return None


class InertiaShareMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            share(
                request,
                auth={
                    "user": {
                        "username": user.username,
                        "is_superuser": user.is_superuser,
                        "is_staff": user.is_staff,
                        "avatar": _avatar_url(user),
                    }
                },
                active_company=request.session.get("active_company"),
                flash=lambda: _flash(request),
                **due_soon(request),
            )
        return self.get_response(request)
