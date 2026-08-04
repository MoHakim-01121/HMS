from inertia import render as inertia_render

from ..permissions import hide_unless


# Internal-only design-system preview. `hide_unless` answers 404 rather than a
# flash+redirect so the route's existence isn't advertised to non-admins, and
# still bounces anonymous visitors to the login page — same shape as
# health_check in hw/views/__init__.py.
@hide_unless('dev', 'view')
def style_guide(request):
    return inertia_render(request, "Dev/StyleGuide", props={})
