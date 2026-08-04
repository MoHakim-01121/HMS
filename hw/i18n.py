"""Tiny request-scoped translation helper for UI-visible backend messages.

The React app owns the labels; backend messages that surface in the UI
(toasts, calendar titles, colour badges) follow the user's chosen language
through ``tr(request, english, indonesian)``. English is the canonical source
string; Indonesian is supplied explicitly so the small message set stays close
to the views that use it.
"""


def user_language(request):
    profile = getattr(request, 'user', None)
    profile = getattr(profile, 'profile', None)
    return getattr(profile, 'language', 'en')


def tr(request, en, id_=None):
    """Return English or Indonesian text for the request user's language."""
    if id_ is None or user_language(request) != 'id':
        return en
    return id_
