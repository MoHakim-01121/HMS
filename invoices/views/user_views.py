from functools import wraps
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import ActivityLog, UserProfile


class CompanyLoginView(LoginView):
    template_name = 'invoices/partials/login.html'

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


def superuser_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Akses ditolak.")
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
    return render(request, 'invoices/users/user_list.html', {'users': users})


@superuser_required
def user_new(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('password_confirm', '')
        is_staff = request.POST.get('is_staff') == 'on'

        if not username or not password:
            messages.error(request, "Username dan password wajib diisi.")
            return render(request, 'invoices/users/user_form.html', {'form_data': request.POST})
        if password != confirm:
            messages.error(request, "Password tidak cocok.")
            return render(request, 'invoices/users/user_form.html', {'form_data': request.POST})
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' sudah digunakan.")
            return render(request, 'invoices/users/user_form.html', {'form_data': request.POST})

        user = User.objects.create_user(username=username, password=password, is_staff=is_staff)
        messages.success(request, f"User '{user.username}' berhasil dibuat.")
        return redirect('user_list')

    return render(request, 'invoices/users/user_form.html', {})


@superuser_required
def user_edit(request, pk):
    edit_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'reset_password':
            password = request.POST.get('password', '')
            confirm  = request.POST.get('password_confirm', '')
            if not password:
                messages.error(request, "Password baru wajib diisi.")
            elif password != confirm:
                messages.error(request, "Password tidak cocok.")
            else:
                edit_user.set_password(password)
                edit_user.save()
                messages.success(request, f"Password '{edit_user.username}' berhasil direset.")
                return redirect('user_list')

        elif action == 'toggle_active':
            if edit_user == request.user:
                messages.error(request, "Tidak bisa menonaktifkan akun sendiri.")
            else:
                edit_user.is_active = not edit_user.is_active
                edit_user.save()
                status = "diaktifkan" if edit_user.is_active else "dinonaktifkan"
                messages.success(request, f"User '{edit_user.username}' berhasil {status}.")
                return redirect('user_list')

        elif action == 'toggle_staff':
            edit_user.is_staff = not edit_user.is_staff
            edit_user.save()
            messages.success(request, f"Hak akses '{edit_user.username}' berhasil diubah.")
            return redirect('user_list')

    return render(request, 'invoices/users/user_form.html', {'edit_user': edit_user, 'edit': True})


@superuser_required
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "Tidak bisa menghapus akun sendiri.")
        return redirect('user_list')
    if target.is_superuser:
        messages.error(request, "Tidak bisa menghapus superuser.")
        return redirect('user_list')
    if request.method == 'POST':
        username = target.username
        target.delete()
        messages.success(request, f"User '{username}' berhasil dihapus.")
        return redirect('user_list')
    return render(request, 'invoices/partials/confirm_delete.html', {
        'object': target, 'type': 'User',
    })


@login_required
def account_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    activities  = ActivityLog.objects.filter(user=request.user)[:20]
    return render(request, 'invoices/account/profile.html', {'profile': profile, 'activities': activities})


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
