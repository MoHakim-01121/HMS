"""Dashboard (home) view.

One feature only: the signed-in landing screen at /dashboard/, the Manager
dashboard of the HMS Dashboard canvas (ManagerHomlu). The data comes from
dashboard.home(); marketing pages live in landing_views.py.
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from inertia import render as inertia_render

from .. import dashboard


def _month_param(value):
    try:
        y, m = value.split('-')
        return date(int(y), int(m), 1)
    except (AttributeError, ValueError):
        return None


@login_required
def home(request):
    """Dashboard for the month (`?month=YYYY-MM`, default this one) or the
    running season (`?season=1`). Each block is computed only for a user who
    may view the module it comes from, over the branch being looked at; the
    rest are left out and not drawn."""
    today = timezone.localdate()
    data = dashboard.home(
        request.user, today,
        month=_month_param(request.GET.get('month')),
        season=request.GET.get('season') == '1',
    )
    return inertia_render(request, "Home/Index", props={'today': today.isoformat(), **data})
