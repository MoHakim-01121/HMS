"""The branch a user is looking at.

A user covering more than one branch sees one branch at a time: every list,
picker and report narrows to the branch picked in the sidebar (branch_scope.
branch_codes). The pick lives in the session; without one, their first
branch other than head office: head office does not run HMS itself, only the
branches do (2026-10-20), so opening on it shows an empty system. A user with a single branch has
nothing to pick and is unaffected.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .branch_scope import switchable_branches

SESSION_KEY = 'active_branch'


def resolve(request):
    """(active branch row, switchable rows) for request.user; (None, []) when
    there is nothing to switch."""
    rows = switchable_branches(request.user)
    if not rows:
        return None, []
    picked = request.session.get(SESSION_KEY)
    by_code = {b.code: b for b in rows}
    if picked not in by_code and not getattr(settings, 'HMS_DEFAULT_BRANCH_PICK', True):
        return None, rows
    active = by_code.get(picked) or next((b for b in rows if not b.is_hq), rows[0])
    return active, rows


class ActiveBranchMiddleware:
    """Pin the picked branch on request.user (after AuthenticationMiddleware)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            active, rows = resolve(request)
            request.branch_choices = rows
            if active is not None:
                user._active_branch = active.code
                user._active_is_hq = active.is_hq
        return self.get_response(request)


@login_required
@require_POST
def switch_branch(request):
    """Look at another of the user's branches, then reload where they were."""
    code = request.POST.get('branch', '')
    rows = switchable_branches(request.user)
    if code not in {b.code for b in rows}:
        return JsonResponse({'error': 'Unknown branch.'}, status=400)
    request.session[SESSION_KEY] = code
    nxt = request.POST.get('next') or '/'
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        nxt = '/'
    return HttpResponseRedirect(nxt)
