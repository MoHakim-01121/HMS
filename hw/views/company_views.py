"""Company-scope switching — the top-bar company selector POSTs here.

Session-only state: sets request.session['active_company'] and bounces back
to the referring page. Access rules live in hw/permissions.py.
"""
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..models.choices import Company
from ..permissions import can_use_company
from .helpers import get_active_company


@login_required
@require_POST
def company_quick_set(request):
    company = request.POST.get("company")
    # Silently ignore a company the user has no access to — the switcher never
    # offers it, so a request for one is either a stale tab or a hand-crafted
    # POST. Either way the session must not adopt it.
    if company in Company.values and can_use_company(request.user, company):
        request.session["active_company"] = company
        request.session.modified = True
    else:
        company = get_active_company(request)

    referer = request.META.get("HTTP_REFERER", "/dashboard/")
    try:
        parsed = urlparse(referer)
        # Reject external redirects — only allow same host
        if parsed.netloc and parsed.netloc != request.get_host():
            safe_url = "/dashboard/"
        else:
            safe_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    except Exception:
        safe_url = "/dashboard/"

    sep = "&" if "?" in safe_url else "?"
    return redirect(f"{safe_url}{sep}company_changed={company}")
