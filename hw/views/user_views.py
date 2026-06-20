from functools import wraps
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, UserProfile


class CompanyLoginView(LoginView):
    template_name = 'hw/partials/login.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        company = self.request.POST.get('company', 'konoz')
        if company not in ('konoz', 'ijabah'):
            company = 'konoz'
        self.request.session['active_company'] = company
        self.request.session.modified = True
        return response

    def get_success_url(self):
        return '/?logged_in=1'


def axes_lockout(request, credentials, *args, **kwargs):
    return HttpResponseRedirect('/login/?locked=1')


def superuser_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Access denied.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


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


@superuser_required
def user_list(request):
    users = User.objects.all().order_by('username')
    data = [{
        "id": u.pk, "username": u.username, "is_staff": u.is_staff,
        "is_superuser": u.is_superuser, "is_active": u.is_active,
        "is_self": u.pk == request.user.pk,
    } for u in users]
    return inertia_render(request, "User/List", props={"users": data})


@superuser_required
def user_new(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('password_confirm', '')
        is_staff = request.POST.get('is_staff') == 'on'

        errors = {}
        if not username:
            errors['username'] = "Username is required."
        elif User.objects.filter(username=username).exists():
            errors['username'] = f"Username '{username}' is already taken."
        if not password:
            errors['password'] = "Password is required."
        elif password != confirm:
            errors['password_confirm'] = "Passwords do not match."

        if errors:
            return inertia_render(request, "User/Form", props={
                "form_data": {"username": username, "is_staff": is_staff}, "errors": errors,
            })

        user = User.objects.create_user(username=username, password=password, is_staff=is_staff)
        messages.success(request, f"User '{user.username}' created successfully.")
        return redirect('user_list')

    return inertia_render(request, "User/Form", props={"form_data": None})


@superuser_required
def user_edit(request, pk):
    edit_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'reset_password':
            password = request.POST.get('password', '')
            confirm  = request.POST.get('password_confirm', '')
            if not password:
                messages.error(request, "New password is required.")
            elif password != confirm:
                messages.error(request, "Passwords do not match.")
            else:
                edit_user.set_password(password)
                edit_user.save()
                messages.success(request, f"Password for '{edit_user.username}' has been reset.")
                return redirect('user_list')

        elif action == 'toggle_active':
            if edit_user == request.user:
                messages.error(request, "You cannot deactivate your own account.")
            else:
                edit_user.is_active = not edit_user.is_active
                edit_user.save()
                status = "activated" if edit_user.is_active else "deactivated"
                messages.success(request, f"User '{edit_user.username}' {status} successfully.")
                return redirect('user_list')

        elif action == 'toggle_staff':
            edit_user.is_staff = not edit_user.is_staff
            edit_user.save()
            messages.success(request, f"Permissions for '{edit_user.username}' updated successfully.")
            return redirect('user_list')

    # Action-based view: every branch above either redirects on success or sets
    # a messages.error (shown as a flash toast). Always return to the Inertia list.
    return redirect('user_list')


@superuser_required
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
        target.delete()
        messages.success(request, f"User '{username}' deleted successfully.")
        return redirect('user_list')
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect('user_list')


@login_required
def account_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    activities  = ActivityLog.objects.filter(user=request.user)[:20]
    u = request.user
    if u.is_superuser:
        role, role_badge = "Administrator", "Admin"
    elif u.is_staff:
        role, role_badge = "Staff", "Staff"
    else:
        role, role_badge = "Standard User", "User"
    return inertia_render(request, "Account/Profile", props={
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
            "company":    a.company,
            "changes":    a.changes or [],
        } for a in activities],
    })


@login_required
@require_POST
def avatar_upload(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    f = request.FILES.get('avatar')
    if f:
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar = f
        profile.save()
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
