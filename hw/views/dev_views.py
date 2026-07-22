from django.http import Http404
from django.shortcuts import redirect

from inertia import render as inertia_render


def style_guide(request):
    # Same shape as health_check (hw/views/__init__.py:134-139): manual
    # is_authenticated check + redirect, rather than @login_required —
    # @login_required's own redirect-anonymous-to-login behavior is fine,
    # but this keeps both checks (auth, then superuser) visible in one
    # place and consistent with the one other internal-only view in HMS.
    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/dev/style-guide/")
    if not request.user.is_superuser:
        raise Http404()
    return inertia_render(request, "Dev/StyleGuide", props={})
