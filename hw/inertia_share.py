"""Share common props with every Inertia response.

Django context processors don't run for Inertia JSON responses, so the data the
shell needs on every page (the authenticated user + the due-soon notifications)
is shared here instead. Must run after InertiaMiddleware (which sets up the
share storage) and after AuthenticationMiddleware (which sets request.user).
"""
from django.contrib.messages import get_messages
from inertia import share

from .context_processors import due_soon
from .branch_scope import coverage, covers_all
from .permissions import get_role, perms_payload, role_label


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


def _branch(request):
    """The branch the shell names under the logo, and the ones it can switch
    to (empty: nothing to switch)."""
    from .models.branch import Branch
    rows = getattr(request, "branch_choices", [])
    active = getattr(request.user, "_active_branch", None)
    if active:
        current = next(b for b in rows if b.code == active)
    elif rows:
        current = rows[0]
    else:
        codes = coverage(request.user)
        qs = Branch.objects.filter(is_active=True)
        if codes is not None:
            qs = qs.filter(code__in=codes)
        current = qs.order_by("-is_hq", "name").first()
    row = lambda b: {"code": b.code, "name": b.name, "is_hq": b.is_hq}
    return {
        "current": row(current) if current else None,
        "choices": [row(b) for b in rows],
    }



def _has_report_branches(user):
    from .finance.branch_report import report_branches
    return report_branches(user).exists()


def _language(user):
    profile = getattr(user, "profile", None)
    return getattr(profile, "language", "en") or "en"


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
                        "name": user.get_full_name() or user.username,
                        "is_superuser": user.is_superuser,
                        "is_staff": user.is_staff,
                        "avatar": _avatar_url(user),
                        # RBAC props. `perms` is {module: [actions]} and drives
                        # every gate in the React shell; it mirrors the server
                        # matrix but never replaces it as the enforcement point.
                        "role": get_role(user),
                        "role_label": role_label(user),
                        "perms": perms_payload(user),
                        # Head office (every branch): its own steps — e.g.
                        # recording a remittance receipt — show only then.
                        "all_branches": covers_all(user),
                        # Branch report: hidden when the user covers no branch
                        # that runs on HMS (head office / inactive only).
                        "report_branches": _has_report_branches(user),
                    }
                },
                branch=lambda: _branch(request),
                locale=_language(user),
                flash=lambda: _flash(request),
                **due_soon(request),
            )
        return self.get_response(request)
