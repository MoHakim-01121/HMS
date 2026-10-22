"""Dev-only helper for scripts/ui-shots.mjs: prints a logged-in session key per
role plus one sample record id per detail page, as JSON.

Run against the local database only:
    .venv-linux/bin/python3 manage.py shell < scripts/ui_shots_sessions.py

Roles with no real user locally (manager, finance) get a `ui_<role>` user with
an unusable password; they exist only so the per-role dashboards can be shot.
"""
import json

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore

from hw.models import Client, ConfirmationLetter, Expense, Hotel, Invoice, PaymentRecord, Remittance, UserProfile

assert settings.DEBUG, "ui shots run against the local dev database only"

User = get_user_model()


def user_for(role):
    found = User.objects.filter(is_active=True, profile__role=role).order_by("pk").first()
    if found:
        return found
    user, _ = User.objects.get_or_create(username=f"ui_{role}", defaults={"first_name": f"UI {role.title()}"})
    user.set_unusable_password()
    user.save()
    UserProfile.objects.update_or_create(user=user, defaults={"role": role})
    return user


def session_for(user):
    store = SessionStore()
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store.create()
    return store.session_key


def last_id(model):
    obj = model.objects.order_by("-pk").first()
    return obj.pk if obj else None


print(json.dumps({
    "cookie": settings.SESSION_COOKIE_NAME,
    "sessions": {role: session_for(user_for(role)) for role in ("admin", "manager", "finance", "staff")},
    "ids": {
        "cl": last_id(ConfirmationLetter), "invoice": last_id(Invoice), "payment": last_id(PaymentRecord),
        "expense": last_id(Expense), "client": last_id(Client), "hotel": last_id(Hotel),
        "remittance": last_id(Remittance),
    },
}))
