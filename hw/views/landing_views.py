"""Manage Landing views: team members and pricelist for the public site.

CRUD follows the same plain request.POST-dict pattern as hw/views/visit_views.py
— no Django Forms, no DRF. GET renders a form (used by the form modal), POST
saves and redirects back to the manage screen; validation failures re-render
the form echoing submitted values + errors.
"""
import os

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Pricelist, TeamMember, log_activity
from ..permissions import require_perm
from .helpers import get_active_company


def _team_echo(data):
    return {
        'name': data.get('name', ''),
        'position': data.get('position', ''),
        'wa': data.get('wa', ''),
        'order': data.get('order', ''),
        'is_active': data.get('is_active') == 'on',
    }


def _validate_team(data):
    errors = {}
    if not data.get('name', '').strip():
        errors['name'] = 'Nama anggota wajib diisi.'
    return errors


def _team_member_payload(m):
    return {
        'id': m.id, 'name': m.name, 'position': m.position,
        'wa': m.wa, 'order': m.order, 'is_active': m.is_active,
        'photo_url': m.photo.url if m.photo else None,
    }


def _pricelist_payload(p):
    return {
        'id': p.id, 'title': p.title, 'is_active': p.is_active,
        'file_url': p.file.url if p.file else None,
        'filename': os.path.basename(p.file.name) if p.file else '',
        'updated_at': p.updated_at.isoformat(),
    }


def _manage_props(request):
    company = get_active_company(request)
    members = TeamMember.objects.filter(company=company).order_by('order', 'id')
    pricelist = Pricelist.objects.filter(company=company, is_active=True).order_by('-updated_at').first()
    return {
        'team_members': [_team_member_payload(m) for m in members],
        'pricelist': _pricelist_payload(pricelist) if pricelist else None,
    }


@require_perm('landing', 'view')
def landing_manage(request):
    return inertia_render(request, 'Landing/Manage', props=_manage_props(request))


@require_perm('landing', 'create')
def team_new(request):
    company = get_active_company(request)
    if request.method == 'POST':
        errors = _validate_team(request.POST)
        if errors:
            return inertia_render(request, 'Landing/TeamForm', props={
                'team': _team_echo(request.POST), 'edit': False, 'errors': errors,
            })
        data = _team_echo(request.POST)
        m = TeamMember.objects.create(
            company=company, name=data['name'], position=data['position'],
            wa=data['wa'],
            photo=request.FILES.get('photo'),
            order=int(data['order']) if str(data['order']).isdigit() else 0,
            is_active=data['is_active'],
        )
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'TeamMember', m.name, m.company)
        messages.success(request, 'Anggota tim ditambahkan.')
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/TeamForm', props={
        'team': None, 'edit': False,
    })


@require_perm('landing', 'edit')
def team_edit(request, pk):
    m = get_object_or_404(TeamMember, pk=pk, company=get_active_company(request))
    if request.method == 'POST':
        errors = _validate_team(request.POST)
        if errors:
            return inertia_render(request, 'Landing/TeamForm', props={
                'team': {**_team_echo(request.POST), 'id': m.pk}, 'edit': True, 'errors': errors,
            })
        data = _team_echo(request.POST)
        m.name = data['name']
        m.position = data['position']
        m.wa = data['wa']
        if request.FILES.get('photo'):
            m.photo = request.FILES['photo']
        m.order = int(data['order']) if str(data['order']).isdigit() else m.order
        m.is_active = data['is_active']
        m.save()
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'TeamMember', m.name, m.company)
        messages.success(request, 'Anggota tim diperbarui.')
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/TeamForm', props={
        'team': _team_member_payload(m), 'edit': True,
    })


@require_perm('landing', 'delete')
@require_POST
def team_delete(request, pk):
    m = get_object_or_404(TeamMember, pk=pk, company=get_active_company(request))
    name = m.name
    m.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'TeamMember', name, m.company)
    return redirect('landing_manage')


@require_perm('landing', 'create')
def pricelist_new(request):
    company = get_active_company(request)
    if request.method == 'POST':
        errors = {}
        title = request.POST.get('title', '').strip()
        file = request.FILES.get('file')
        if not title:
            errors['title'] = 'Judul pricelist wajib diisi.'
        if not file:
            errors['file'] = 'Pilih file pricelist untuk diunggah.'
        if errors:
            return inertia_render(request, 'Landing/PricelistForm', props={
                'pricelist': {'title': title, 'is_active': request.POST.get('is_active') == 'on'},
                'edit': False, 'errors': errors,
            })
        p = Pricelist.objects.create(
            company=company, title=title, file=file,
            is_active=request.POST.get('is_active') == 'on',
        )
        # Only one pricelist may exist at a time — a new upload replaces any
        # previous one so the public page always serves the latest file.
        Pricelist.objects.filter(company=company).exclude(pk=p.pk).delete()
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Pricelist', p.title, p.company)
        messages.success(request, 'Pricelist diunggah.')
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/PricelistForm', props={
        'pricelist': None, 'edit': False,
    })


@require_perm('landing', 'edit')
def pricelist_edit(request, pk):
    p = get_object_or_404(Pricelist, pk=pk, company=get_active_company(request))
    if request.method == 'POST':
        errors = {}
        title = request.POST.get('title', '').strip()
        file = request.FILES.get('file')
        if not title:
            errors['title'] = 'Judul pricelist wajib diisi.'
        if errors:
            return inertia_render(request, 'Landing/PricelistForm', props={
                'pricelist': {'id': p.pk, 'title': title, 'filename': _pricelist_payload(p)['filename'],
                              'is_active': request.POST.get('is_active') == 'on'},
                'edit': True, 'errors': errors,
            })
        p.title = title
        if file:
            p.file = file
        p.is_active = request.POST.get('is_active') == 'on'
        p.save()
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Pricelist', p.title, p.company)
        messages.success(request, 'Pricelist diperbarui.')
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/PricelistForm', props={
        'pricelist': _pricelist_payload(p), 'edit': True,
    })


@require_perm('landing', 'delete')
@require_POST
def pricelist_delete(request, pk):
    p = get_object_or_404(Pricelist, pk=pk, company=get_active_company(request))
    title = p.title
    p.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Pricelist', title, p.company)
    return redirect('landing_manage')
