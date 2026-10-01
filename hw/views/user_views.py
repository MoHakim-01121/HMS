import re
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.db.models import ProtectedError
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from inertia import render as inertia_render

from ..models import ActivityLog, RoleDefinition, UserProfile, log_activity
from ..models.user import Role
from ..permissions import (
    get_role, is_valid_role, require_perm,
    role_choices, role_label, role_labels,
)


class CompanyLoginView(LoginView):
    template_name = 'hw/partials/login.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        # "Ingat perangkat ini" (login form): keep the session past browser
        # close, otherwise expire it when the browser is closed.
        self.request.session.set_expiry(None if self.request.POST.get('remember') else 0)
        self.request.session.modified = True
        return response

    def get_success_url(self):
        return '/dashboard/?logged_in=1'


def axes_lockout(request, credentials, *args, **kwargs):
    return HttpResponseRedirect('/login/?locked=1')


def _role_choices():
    # Roles are rows now, so the picker and its hints come from the database.
    return role_choices()


def _clean_role(value, fallback=Role.STAFF.value):
    return value if is_valid_role(value) else fallback


def _grants_django_staff(role_slug):
    """Whether holding this role also implies Django admin access.

    A property of the role now, not a hardcoded {admin, manager} test, so a
    custom role can be created without silently landing in Django admin.
    """
    row = RoleDefinition.objects.filter(slug=role_slug).first()
    if row is not None:
        return row.grants_django_staff
    return role_slug in (Role.ADMIN.value, Role.MANAGER.value)


def _safe_redirect(request):
    """Return a same-host redirect target from HTTP_REFERER, falling back to '/'."""
    referer = request.META.get('HTTP_REFERER', '/')
    try:
        parsed = urlparse(referer)
        if parsed.netloc and parsed.netloc != request.get_host():
            return '/'
        return parsed.path + (f'?{parsed.query}' if parsed.query else '')
    except Exception:
        return '/'


@require_perm('users', 'view')
def user_list(request):
    users = User.objects.select_related('profile').order_by('username')
    labels = role_labels()
    data = [{
        "id": u.pk, "username": u.username,
        "full_name": u.get_full_name() or u.username,
        "is_staff": u.is_staff,
        "is_superuser": u.is_superuser, "is_active": u.is_active,
        "is_self": u.pk == request.user.pk,
        "role": get_role(u),
        "role_label": role_label(u),
    } for u in users]
    return inertia_render(request, "User/List", props={
        "users": data,
        "role_choices": _role_choices(),
        "role_labels": labels,
    })


@require_perm('users', 'create')
def user_new(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('password_confirm', '')
        role = _clean_role(request.POST.get('role'))
        # is_staff is kept in sync with the role so Django admin access lines up
        # with what HMS itself grants.
        is_staff = _grants_django_staff(role)

        errors = {}
        if not username:
            errors['username'] = "Username is required."
        else:
            try:
                User.username_validator(username)
            except ValidationError:
                errors['username'] = "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."
            else:
                if User.objects.filter(username=username).exists():
                    errors['username'] = f"Username '{username}' is already taken."
        if len(full_name) > 150:
            errors['full_name'] = "Full name must be 150 characters or fewer."
        if not password:
            errors['password'] = "Password is required."
        elif password != confirm:
            errors['password_confirm'] = "Passwords do not match."

        if errors:
            return inertia_render(request, "User/Form", props={
                "form_data": {
                    "username": username, "full_name": full_name,
                    "role": role,
                },
                "errors": errors,
                "role_choices": _role_choices(),
            })

        parts = full_name.split(None, 1)
        first_name = parts[0][:30] if full_name else ""
        last_name = parts[1][:150] if len(parts) > 1 else ""
        user = User.objects.create_user(
            username=username, password=password, is_staff=is_staff,
            first_name=first_name, last_name=last_name,
        )
        UserProfile.objects.update_or_create(
            user=user, defaults={'role': role},
        )
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'User', user.username, [{'field': 'role', 'new': role}])
        messages.success(request, f"User '{user.username}' created successfully.")
        return redirect('user_list')

    return inertia_render(request, "User/Form", props={
        "form_data": None,
        "role_choices": _role_choices(),
    })


@require_perm('users', 'edit')
def user_edit(request, pk):
    edit_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'set_access':
            role = _clean_role(request.POST.get('role'), get_role(edit_user))
            if edit_user == request.user:
                # Demoting yourself would revoke the very permission needed to
                # undo it — the only way back would be a shell.
                messages.error(request, "You cannot change your own role.")
            elif edit_user.is_superuser and not request.user.is_superuser:
                messages.error(request, "Only a superuser can change a superuser's access.")
            else:
                old_role = get_role(edit_user)
                UserProfile.objects.update_or_create(
                    user=edit_user,
                    defaults={'role': role},
                )
                if old_role != role:
                    log_activity(request.user, ActivityLog.ACTION_EDIT, 'User', edit_user.username,
                                 [{'field': 'role', 'old': old_role, 'new': role}])
                edit_user.is_staff = _grants_django_staff(role)
                edit_user.save(update_fields=['is_staff'])
                messages.success(
                    request, f"Access for '{edit_user.username}' updated successfully."
                )
                return redirect('user_list')

        elif action == 'reset_password':
            password = request.POST.get('password', '')
            confirm  = request.POST.get('password_confirm', '')
            if not password:
                messages.error(request, "New password is required.")
            elif password != confirm:
                messages.error(request, "Passwords do not match.")
            else:
                edit_user.set_password(password)
                edit_user.save()
                log_activity(request.user, ActivityLog.ACTION_EDIT, 'User', edit_user.username,
                             [{'field': 'password', 'new': 'reset'}])
                messages.success(request, f"Password for '{edit_user.username}' has been reset.")
                return redirect('user_list')

        elif action == 'toggle_active':
            if edit_user == request.user:
                messages.error(request, "You cannot deactivate your own account.")
            else:
                edit_user.is_active = not edit_user.is_active
                edit_user.save()
                log_activity(request.user, ActivityLog.ACTION_EDIT, 'User', edit_user.username,
                             [{'field': 'is_active', 'old': not edit_user.is_active, 'new': edit_user.is_active}])
                status = "activated" if edit_user.is_active else "deactivated"
                messages.success(request, f"User '{edit_user.username}' {status} successfully.")
                return redirect('user_list')

    # The old 'toggle_staff' action is gone: is_staff is now derived from the
    # role by 'set_access', so flipping it on its own would desync the two.

    # Action-based view: every branch above either redirects on success or sets
    # a messages.error (shown as a flash toast). Always return to the Inertia list.
    return redirect('user_list')


@require_perm('users', 'delete')
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('user_list')
    if target.is_superuser:
        messages.error(request, "You cannot delete a superuser.")
        return redirect('user_list')
    if request.method == 'POST':
        username = target.username
        try:
            with transaction.atomic():
                target.delete()
        except ProtectedError:
            # Dokumen keuangan yang dibuatnya menunjuk akun ini; riwayat tidak boleh hilang.
            messages.error(
                request,
                f"User '{username}' sudah membuat dokumen keuangan dan tidak bisa dihapus — nonaktifkan saja.",
            )
            return redirect('user_list')
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'User', username)
        messages.success(request, f"User '{username}' deleted successfully.")
        return redirect('user_list')
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect('user_list')


@require_perm('users', 'edit')
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def user_credential_card(request, pk):
    """Return a printable credential-card PDF (username + password + warning).

    The password printed on the card is typed by the admin — the stored hash
    is one-way, so the current password can never be recovered. The account's
    password is never touched: this just prints a card.
    """
    from .pdf import _logo_file_url
    from weasyprint import HTML

    target = get_object_or_404(User, pk=pk)

    password = request.POST.get('password', '').strip()
    confirm = request.POST.get('password_confirm', '').strip()
    if not password:
        return JsonResponse({"ok": False, "error": "Password is required to print the card."}, status=400)
    if len(password) > 128:
        return JsonResponse({"ok": False, "error": "Password must be 128 characters or fewer."}, status=400)
    if password != confirm:
        return JsonResponse({"ok": False, "error": "Passwords do not match."}, status=400)

    context = {
        "username": target.username,
        "password": password,
        "company_name": "KONOZ UNITED",
        "logo_rel_path": _logo_file_url(),
    }
    html = render_to_string('hw/user/credential_card.html', context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    # Username is sanitized before use in a header value so a legacy username
    # can never smuggle quotes/newlines into Content-Disposition (header injection).
    safe_username = re.sub(r'[^\w@.+-]', '_', target.username)[:64] or 'user'
    response['Content-Disposition'] = f'inline; filename="credentials-{safe_username}.pdf"'
    response['Cache-Control'] = 'no-store'
    return response


def _profile_props(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    activities = ActivityLog.objects.filter(user=request.user)[:20]
    u = request.user
    role = role_label(u)
    # Custom roles have no short form, so the badge falls back to the full
    # label rather than mislabelling an unknown role as 'Viewer'.
    role_badge = {'admin': 'Admin', 'manager': 'Manager', 'staff': 'Staff',
                  'viewer': 'Viewer'}.get(get_role(u), role)
    return {
        "profile": {"avatar_url": profile.avatar.url if profile.avatar else None},
        "account": {
            "full_name":    u.get_full_name() or u.username,
            "username":     u.username,
            "email":        u.email,
            "uid":          f"UID-{u.pk:04d}",
            "is_superuser": u.is_superuser,
            "is_staff":     u.is_staff,
            "is_active":    u.is_active,
            "role":         role,
            "role_badge":   role_badge,
            "date_joined":  u.date_joined.isoformat() if u.date_joined else None,
            "last_login":   u.last_login.isoformat() if u.last_login else None,
        },
        "activities": [{
            "timestamp":  a.timestamp.isoformat(),
            "action":     a.action,
            "model_name": a.model_name,
            "object_ref": a.object_ref,
            "changes":    a.changes or [],
        } for a in activities],
    }


@login_required
def account_profile(request):
    return inertia_render(request, "Account/Profile", props=_profile_props(request))


@login_required
@require_POST
def account_profile_update(request):
    u = request.user
    data = request.POST
    errors = {}

    # Only the fields actually sent are touched, so each section on the page
    # can save independently without blanking the others.
    full_name = data.get("full_name", "").strip() if "full_name" in data else None
    if full_name is not None:
        if not full_name:
            errors["full_name"] = "Display name is required."
        elif len(full_name) > 150:
            errors["full_name"] = "Display name must be 150 characters or fewer."

    email = data.get("email", "").strip() if "email" in data else None
    if email is not None and email:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = "Enter a valid email address."
        else:
            if User.objects.filter(email__iexact=email).exclude(pk=u.pk).exists():
                errors["email"] = "This email is already in use."

    # Usernames identify an account, so only an administrator may change them —
    # enforced server-side, not just hidden in the UI.
    username = None
    if "username" in data:
        if not u.is_superuser:
            errors["username"] = "Only an administrator can change the username."
        else:
            username = data.get("username", "").strip()
            if not username:
                errors["username"] = "Username is required."
            elif len(username) > 150:
                errors["username"] = "Username must be 150 characters or fewer."
            else:
                try:
                    User.username_validator(username)
                except ValidationError:
                    errors["username"] = "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."
                else:
                    if User.objects.filter(username__iexact=username).exclude(pk=u.pk).exists():
                        errors["username"] = f"Username '{username}' is already taken."

    if errors:
        props = _profile_props(request)
        props["errors"] = errors
        return inertia_render(request, "Account/Profile", props=props)

    update_fields = []
    if full_name is not None:
        parts = full_name.split(None, 1)
        u.first_name = parts[0][:30]
        u.last_name = parts[1][:150] if len(parts) > 1 else ""
        update_fields += ["first_name", "last_name"]
    if email is not None:
        u.email = email
        update_fields.append("email")
    if username is not None:
        u.username = username
        update_fields.append("username")
    u.save(update_fields=update_fields)
    messages.success(request, "Profile updated successfully.")
    return redirect("account_profile")


@login_required
@require_POST
def avatar_upload(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    f = request.FILES.get('avatar')
    if f:
        # Re-encode through Pillow so a malicious file that merely *claims* to
        # be an image (or an SVG/HTML served as image) is neutralized — the
        # stored file is always a freshly-written JPEG/PNG with a safe name.
        # The model field alone is not enough: it only validates via a form's
        # clean(), and this endpoint assigns the file directly.
        from io import BytesIO
        from .helpers import PROOF_MAX_SIZE
        if f.size > PROOF_MAX_SIZE:
            messages.error(request, "Avatar terlalu besar (maks 10 MB).")
            return redirect(_safe_redirect(request))
        try:
            from PIL import Image
            img = Image.open(f)
            img.load()
            fmt = (img.format or '').upper()
            if fmt not in ('JPEG', 'PNG', 'WEBP', 'GIF'):
                messages.error(request, "File type not allowed. Use JPG/PNG/WEBP/GIF.")
                return redirect(_safe_redirect(request))
            img = img.convert('RGB') if fmt != 'GIF' else img
        except Exception:
            messages.error(request, "File is not a valid image.")
            return redirect(_safe_redirect(request))

        out = BytesIO()
        target_fmt = 'JPEG' if fmt in ('JPEG', 'WEBP', 'GIF') else 'PNG'
        if img.mode in ('RGBA', 'LA', 'P') and target_fmt == 'JPEG':
            img = img.convert('RGB')
        img.save(out, format=target_fmt)
        out.seek(0)

        from django.core.files.base import ContentFile
        safe_name = f'avatar_{profile.user.pk}.{"jpg" if target_fmt == "JPEG" else "png"}'
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar.save(safe_name, ContentFile(out.getvalue()), save=True)
        messages.success(request, "Avatar diperbarui.")
    return redirect(_safe_redirect(request))


@login_required
@require_POST
def avatar_delete(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if profile and profile.avatar:
        profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save()
    return redirect(_safe_redirect(request))


@login_required
@require_POST
def set_language(request):
    lang = request.POST.get("language", "").strip()
    if lang not in ("en", "id"):
        return JsonResponse({"ok": False, "error": "Invalid language."}, status=400)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.language = lang
    profile.save(update_fields=["language"])
    return JsonResponse({"ok": True, "locale": lang})
