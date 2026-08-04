"""Role management screens.

The permission matrix used to be a constant; these views put it behind a form.
Guarded by the ``users`` module — editing a role *is* account administration,
and splitting it into its own module would let someone hand out the power to
grant permissions without the power to assign them, which is the same power
with an extra step.

Every write goes through :func:`_read_permissions`, so a posted matrix can only
ever contain modules and actions this build actually guards.
"""
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.utils.text import slugify

from inertia import render as inertia_render

from ..models.role import RoleDefinition
from ..models.user import Role, UserProfile
from ..permissions import ACTIONS, MODULES, get_role, require_perm

# Human labels for the matrix header. Keys must stay in sync with MODULES.
MODULE_LABELS = {
    'cl': 'Confirmation Letters',
    'invoice': 'Invoices',
    'services': 'Services',
    'hotels': 'Hotels',
    'clients': 'Clients',
    'remittance': 'Remittance',
    'calendar': 'Calendar',
    'penalty': 'Cancellation Penalty',
    'users': 'Users & Roles',
    'dev': 'Dev / Style Guide',
}

ACTION_LABELS = {
    'view': 'View',
    'create': 'Create',
    'edit': 'Edit',
    'delete': 'Delete',
    'export': 'Export / PDF',
}


def _matrix_meta():
    """Shape of the grid, shared by the list and the form."""
    return {
        "modules": [{"key": m, "label": MODULE_LABELS.get(m, m)} for m in MODULES],
        "actions": [{"key": a, "label": ACTION_LABELS.get(a, a)} for a in ACTIONS],
    }


def _read_permissions(request):
    """Turn posted 'module:action' checkboxes into {module: [actions]}.

    Unknown pairs are dropped rather than rejected: the form is generated from
    MODULES/ACTIONS, so anything else is a stale tab or a hand-crafted POST and
    silently ignoring it is the safe reading.
    """
    result = {}
    for token in request.POST.getlist('permissions'):
        module, _, action = token.partition(':')
        if module in MODULES and action in ACTIONS:
            result.setdefault(module, []).append(action)
    return {m: sorted(set(a)) for m, a in result.items()}


def _serialise(role, user_counts):
    return {
        "slug": role.slug,
        "label": role.label,
        "description": role.description,
        "permissions": role.permissions or {},
        "grants_django_staff": role.grants_django_staff,
        "is_system": role.is_system,
        "locked": role.locked,
        "user_count": user_counts.get(role.slug, 0),
    }


def _user_counts():
    rows = (UserProfile.objects.values('role')
            .annotate(n=Count('id')).order_by())
    return {r['role']: r['n'] for r in rows}


def _unique_slug(base, exclude_pk=None):
    slug = slugify(base)[:32] or 'role'
    qs = RoleDefinition.objects.exclude(pk=exclude_pk) if exclude_pk else RoleDefinition.objects.all()
    if not qs.filter(slug=slug).exists():
        return slug
    stem = slug[:29]
    for n in range(2, 100):
        candidate = f"{stem}-{n}"
        if not qs.filter(slug=candidate).exists():
            return candidate
    return f"{stem}-{RoleDefinition.objects.count() + 1}"


@require_perm('users', 'view')
def role_list(request):
    counts = _user_counts()
    roles = [_serialise(r, counts) for r in RoleDefinition.objects.all()]
    return inertia_render(request, "Role/List", props={
        "roles": roles,
        **_matrix_meta(),
        "current_role": get_role(request.user),
    })


@require_perm('users', 'create')
def role_new(request):
    if request.method == 'POST':
        label = request.POST.get('label', '').strip()
        description = request.POST.get('description', '').strip()
        permissions = _read_permissions(request)

        errors = {}
        if not label:
            errors['label'] = "Role name is required."
        if not permissions:
            errors['permissions'] = "Grant at least one permission."

        if errors:
            return inertia_render(request, "Role/Form", props={
                "role": {
                    "slug": None, "label": label, "description": description,
                    "permissions": permissions, "grants_django_staff": False,
                    "is_system": False, "locked": False, "user_count": 0,
                },
                "errors": errors,
                **_matrix_meta(),
            })

        role = RoleDefinition.objects.create(
            slug=_unique_slug(label),
            label=label,
            description=description,
            permissions=permissions,
            grants_django_staff=bool(request.POST.get('grants_django_staff')),
            is_system=False,
            order=100,
        )
        messages.success(request, f"Role '{role.label}' created successfully.")
        return redirect('role_list')

    return inertia_render(request, "Role/Form", props={
        "role": None,
        **_matrix_meta(),
    })


@require_perm('users', 'edit')
def role_edit(request, slug):
    role = get_object_or_404(RoleDefinition, slug=slug)

    if role.locked:
        messages.error(
            request,
            "The Administrator role always has full access and cannot be edited.",
        )
        return redirect('role_list')

    # Editing the role you are standing on can revoke the permission needed to
    # undo the edit. Superusers bypass the matrix entirely, so they are safe.
    if role.slug == get_role(request.user) and not request.user.is_superuser:
        messages.error(request, "You cannot edit the permissions of your own role.")
        return redirect('role_list')

    if request.method == 'POST':
        label = request.POST.get('label', '').strip()
        permissions = _read_permissions(request)

        errors = {}
        if not label:
            errors['label'] = "Role name is required."
        if not permissions:
            errors['permissions'] = "Grant at least one permission."

        if errors:
            counts = _user_counts()
            payload = _serialise(role, counts)
            payload.update({"label": label, "permissions": permissions})
            return inertia_render(request, "Role/Form", props={
                "role": payload, "errors": errors, **_matrix_meta(),
            })

        role.label = label
        role.description = request.POST.get('description', '').strip()
        role.permissions = permissions
        role.grants_django_staff = bool(request.POST.get('grants_django_staff'))
        role.save()

        # Django admin access is a property of the role, so re-apply it to
        # everyone holding this role instead of waiting for their next edit.
        User.objects.filter(profile__role=role.slug).exclude(is_superuser=True).update(
            is_staff=role.grants_django_staff
        )

        messages.success(request, f"Role '{role.label}' updated successfully.")
        return redirect('role_list')

    counts = _user_counts()
    return inertia_render(request, "Role/Form", props={
        "role": _serialise(role, counts),
        **_matrix_meta(),
    })


@require_perm('users', 'delete')
def role_delete(request, slug):
    role = get_object_or_404(RoleDefinition, slug=slug)

    if role.is_system:
        messages.error(request, f"'{role.label}' is a built-in role and cannot be deleted.")
        return redirect('role_list')
    if role.slug == get_role(request.user):
        messages.error(request, "You cannot delete the role you are currently using.")
        return redirect('role_list')

    if request.method != 'POST':
        # Confirmation happens client-side; a GET just bounces back.
        return redirect('role_list')

    # Members have to land somewhere. The picker offers the remaining roles;
    # anything unrecognised falls back to Staff, never to a dangling slug.
    fallback = request.POST.get('reassign_to') or Role.STAFF.value
    if not RoleDefinition.objects.filter(slug=fallback).exclude(pk=role.pk).exists():
        fallback = Role.STAFF.value
    moved = UserProfile.objects.filter(role=role.slug).update(role=fallback)

    label = role.label
    role.delete()

    if moved:
        messages.success(
            request,
            f"Role '{label}' deleted. {moved} account(s) moved to '{fallback}'.",
        )
    else:
        messages.success(request, f"Role '{label}' deleted successfully.")
    return redirect('role_list')
