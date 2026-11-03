"""Landing / public-marketing views.

Two parts, one feature (the public site):
  - public render: `landing`, `public_hotels` — the pages anonymous visitors see
  - manage CRUD: team members and pricelist that feed those pages

CRUD uses plain request.POST dicts — no Django Forms, no DRF. GET renders a form (used by the form modal), POST
saves and redirects back to the manage screen; validation failures re-render
the form echoing submitted values + errors.
"""
import os
import zipfile
from io import BytesIO

from django.contrib import messages
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..i18n import tr
from ..models import ActivityLog, Pricelist, TeamMember, log_activity
from ..permissions import require_perm

LANDING_UPLOAD_MAX_SIZE = 10 * 1024 * 1024
_PRICELIST_EXTENSIONS = {'.pdf', '.xls', '.xlsx', '.doc', '.docx'}
_OLE_SIGNATURE = bytes.fromhex('d0cf11e0a1b11ae1')
_ZIP_SIGNATURES = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')


def _clean_team_photo(upload):
    """Validate and re-encode a public team photo to a safe JPEG."""
    if upload.size > LANDING_UPLOAD_MAX_SIZE:
        return None, 'Photo is too large (max 10 MB).'
    try:
        from PIL import Image, ImageOps

        image = Image.open(upload)
        if (image.format or '').upper() not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
            return None, 'Use a JPG, PNG, WEBP, or GIF image.'
        if image.width * image.height > 20_000_000:
            return None, 'Photo dimensions are too large.'
        image.load()
        image = ImageOps.exif_transpose(image).convert('RGB')
        output = BytesIO()
        image.save(output, format='JPEG', optimize=True)
    except Exception:
        return None, 'The uploaded photo is not a valid image.'
    return ContentFile(output.getvalue(), name='photo.jpg'), None


def _pricelist_error(upload):
    """Accept only the document formats offered by the form, by file content."""
    if upload.size > LANDING_UPLOAD_MAX_SIZE:
        return 'File is too large (max 10 MB).'

    extension = os.path.splitext(upload.name)[1].lower()
    if extension not in _PRICELIST_EXTENSIONS:
        return 'Use a PDF, XLS, XLSX, DOC, or DOCX file.'

    header = upload.read(2048)
    upload.seek(0)
    if extension == '.pdf':
        return None if header.startswith(b'%PDF-') else 'File content does not match its extension.'
    if extension in {'.doc', '.xls'}:
        return None if header.startswith(_OLE_SIGNATURE) else 'File content does not match its extension.'
    if not header.startswith(_ZIP_SIGNATURES):
        return 'File content does not match its extension.'

    expected_member = 'word/document.xml' if extension == '.docx' else 'xl/workbook.xml'
    try:
        with zipfile.ZipFile(upload) as archive:
            names = archive.namelist()
            if len(names) > 2000 or expected_member not in names or '[Content_Types].xml' not in names:
                return 'File content does not match its extension.'
    except (OSError, ValueError, zipfile.BadZipFile):
        return 'The uploaded document is not valid.'
    finally:
        upload.seek(0)
    return None


def landing(request):
    """The public landing page is not used: "/" opens the login, or the
    dashboard for someone already signed in (user, 2026-11-03)."""
    return redirect('home' if request.user.is_authenticated else 'login')


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
    members = TeamMember.objects.order_by('order', 'id')
    pricelist = Pricelist.objects.filter(is_active=True).order_by('-updated_at').first()
    return {
        'team_members': [_team_member_payload(m) for m in members],
        'pricelist': _pricelist_payload(pricelist) if pricelist else None,
    }


@require_perm('landing', 'view')
def landing_manage(request):
    return inertia_render(request, 'Landing/Manage', props=_manage_props(request))


@require_perm('landing', 'create')
def team_new(request):
    if request.method == 'POST':
        errors = _validate_team(request.POST)
        photo = request.FILES.get('photo')
        if photo:
            photo, photo_error = _clean_team_photo(photo)
            if photo_error:
                errors['photo'] = photo_error
        if errors:
            return inertia_render(request, 'Landing/TeamForm', props={
                'team': _team_echo(request.POST), 'edit': False, 'errors': errors,
            })
        data = _team_echo(request.POST)
        m = TeamMember.objects.create(
            name=data['name'], position=data['position'],
            wa=data['wa'],
            photo=photo,
            order=int(data['order']) if str(data['order']).isdigit() else 0,
            is_active=data['is_active'],
        )
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'TeamMember', m.name)
        messages.success(request, tr(request, 'Team member added.', 'Anggota tim ditambahkan.'))
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/TeamForm', props={
        'team': None, 'edit': False,
    })


@require_perm('landing', 'edit')
def team_edit(request, pk):
    m = get_object_or_404(TeamMember, pk=pk)
    if request.method == 'POST':
        errors = _validate_team(request.POST)
        photo = request.FILES.get('photo')
        if photo:
            photo, photo_error = _clean_team_photo(photo)
            if photo_error:
                errors['photo'] = photo_error
        if errors:
            return inertia_render(request, 'Landing/TeamForm', props={
                'team': {**_team_echo(request.POST), 'id': m.pk}, 'edit': True, 'errors': errors,
            })
        data = _team_echo(request.POST)
        m.name = data['name']
        m.position = data['position']
        m.wa = data['wa']
        if photo:
            m.photo = photo
        m.order = int(data['order']) if str(data['order']).isdigit() else m.order
        m.is_active = data['is_active']
        m.save()
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'TeamMember', m.name)
        messages.success(request, tr(request, 'Team member updated.', 'Anggota tim diperbarui.'))
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/TeamForm', props={
        'team': _team_member_payload(m), 'edit': True,
    })


@require_perm('landing', 'delete')
@require_POST
def team_delete(request, pk):
    m = get_object_or_404(TeamMember, pk=pk)
    name = m.name
    m.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'TeamMember', name)
    messages.success(request, tr(request, f'{name} removed from the team.', f'{name} dihapus dari tim.'))
    return redirect('landing_manage')


@require_perm('landing', 'create')
def pricelist_new(request):
    if request.method == 'POST':
        errors = {}
        title = request.POST.get('title', '').strip()
        file = request.FILES.get('file')
        if not title:
            errors['title'] = 'Judul pricelist wajib diisi.'
        if not file:
            errors['file'] = 'Pilih file pricelist untuk diunggah.'
        elif (file_error := _pricelist_error(file)):
            errors['file'] = file_error
        if errors:
            return inertia_render(request, 'Landing/PricelistForm', props={
                'pricelist': {'title': title, 'is_active': request.POST.get('is_active') == 'on'},
                'edit': False, 'errors': errors,
            })
        p = Pricelist.objects.create(
            title=title, file=file,
            is_active=request.POST.get('is_active') == 'on',
        )
        # Only one pricelist may exist at a time — a new upload replaces any
        # previous one so the public page always serves the latest file.
        Pricelist.objects.exclude(pk=p.pk).delete()
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Pricelist', p.title)
        messages.success(request, tr(request, 'Pricelist uploaded.', 'Pricelist diunggah.'))
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/PricelistForm', props={
        'pricelist': None, 'edit': False,
    })


@require_perm('landing', 'edit')
def pricelist_edit(request, pk):
    p = get_object_or_404(Pricelist, pk=pk)
    if request.method == 'POST':
        errors = {}
        title = request.POST.get('title', '').strip()
        file = request.FILES.get('file')
        if not title:
            errors['title'] = 'Judul pricelist wajib diisi.'
        if file and (file_error := _pricelist_error(file)):
            errors['file'] = file_error
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
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Pricelist', p.title)
        messages.success(request, tr(request, 'Pricelist updated.', 'Pricelist diperbarui.'))
        return redirect('landing_manage')
    return inertia_render(request, 'Landing/PricelistForm', props={
        'pricelist': _pricelist_payload(p), 'edit': True,
    })


@require_perm('landing', 'delete')
@require_POST
def pricelist_delete(request, pk):
    p = get_object_or_404(Pricelist, pk=pk)
    title = p.title
    p.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Pricelist', title)
    messages.success(request, tr(request, f'Pricelist "{title}" deleted.', f'Pricelist "{title}" dihapus.'))
    return redirect('landing_manage')
