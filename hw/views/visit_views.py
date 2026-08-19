"""Visit appointment views: self-scheduled client visits with GPS check-in.

PLANNED -> COMPLETED/CANCELLED lifecycle mirroring ConfirmationLetter's status
pattern. Staff see and manage only their own visits (row-level scoping enforced
here in the view layer); Manager/Admin/Viewer see the whole company's.

Validation is plain request.POST/JSON dict checking, like hw/views/cl_views.py
-- no Django Forms, no DRF.
"""
import json
import os
from datetime import date, datetime, time as dtime
from decimal import Decimal, InvalidOperation

import magic

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Client, Role, Visit, VisitPhoto, log_activity
from ..permissions import get_role, require_perm
from ..utils import haversine_meters
from .helpers import _is_mobile, _page_range_display, _parse_date, get_active_company
from .pdf import _logo_file_url

_ALLOWED_PHOTO_MIME = {'image/jpeg', 'image/png', 'image/webp'}


def _client_options(active_company):
    return list(
        Client.objects.filter(company=active_company, is_active=True)
        .order_by('name').values('id', 'name')
    )


def _get_visit(request, pk, qs=None):
    """Fetch a Visit by pk, scoped to the active company (same 404-on-scope-miss
    pattern as company scoping elsewhere). Staff additionally only ever resolve
    their own visits -- self-service ownership, enforced the same way company
    scoping is: filter the queryset, let a miss 404 rather than 403."""
    qs = qs if qs is not None else Visit.objects.all()
    qs = qs.filter(company=get_active_company(request))
    if get_role(request.user) == Role.STAFF.value:
        qs = qs.filter(staff=request.user)
    return get_object_or_404(qs, pk=pk)


def _validate_visit(data):
    errors = {}
    if not data.get('client_id'):
        errors['client_id'] = 'Please select a client.'
    if not _parse_date(data.get('scheduled_date')):
        errors['scheduled_date'] = 'Please choose a date.'
    if not data.get('purpose', '').strip():
        errors['purpose'] = 'Please describe the purpose of the visit.'
    start = _parse_time(data.get('start_time'))
    end = _parse_time(data.get('end_time'))
    if start and end and end <= start:
        errors['end_time'] = 'End time must be after start time.'
    return errors


def _visit_echo(data):
    return {
        'client_id': data.get('client_id', ''),
        'scheduled_date': data.get('scheduled_date', ''),
        'start_time': data.get('start_time', ''),
        'end_time': data.get('end_time', ''),
        'purpose': data.get('purpose', ''),
    }


def _parse_time(val):
    if not val or not str(val).strip():
        return None
    try:
        return datetime.strptime(str(val).strip(), '%H:%M').time()
    except ValueError:
        return None


def _overlap_visits(active_company, staff_id, scheduled_date, start_time, end_time, exclude_pk=None):
    """PLANNED visits of the same staff on the same date that overlap the given
    slot. Only visits with both times set take part in blocking; a visit without
    a slot never blocks and never is blocked."""
    if staff_id is None or not start_time or not end_time:
        return None
    qs = Visit.objects.filter(
        company=active_company,
        staff_id=staff_id,
        status=Visit.PLANNED,
        scheduled_date=scheduled_date,
        start_time__isnull=False,
        end_time__isnull=False,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def _check_slot(request, data, exclude_pk=None):
    start = _parse_time(data.get('start_time'))
    end = _parse_time(data.get('end_time'))
    existing = _overlap_visits(
        get_active_company(request), request.user.id,
        _parse_date(data.get('scheduled_date')), start, end, exclude_pk,
    )
    if existing:
        return 'Time slot overlaps with another visit (%s).' % (
            existing.client.name if existing.client_id else 'client',
        )
    return None


def _to_float_or_none(val):
    try:
        return float(val) if val not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _slot_label(v):
    if not v.start_time and not v.end_time:
        return ''
    fmt = lambda t: t.strftime('%H:%M')
    if v.start_time and v.end_time:
        return f"{fmt(v.start_time)} – {fmt(v.end_time)}"
    return fmt(v.start_time or v.end_time)


@require_perm('visits', 'view')
def visit_list(request):
    active_company = get_active_company(request)
    qs = Visit.objects.filter(company=active_company).select_related('client', 'staff')
    if get_role(request.user) == Role.STAFF.value:
        qs = qs.filter(staff=request.user)

    today = date.today()
    is_staff = get_role(request.user) == Role.STAFF.value

    staff_filter = None
    if not is_staff:
        try:
            staff_filter = int(request.GET.get('staff') or 0) or None
        except (TypeError, ValueError):
            staff_filter = None
        if staff_filter:
            qs = qs.filter(staff_id=staff_filter)

    # -- schedule board: the month of the selected date + its day timeline --
    selected_date = _parse_date(request.GET.get('date')) or today
    month_qs = qs.filter(
        scheduled_date__year=selected_date.year,
        scheduled_date__month=selected_date.month,
    ).order_by('scheduled_date', 'start_time')

    staff_list = []
    if not is_staff:
        from django.contrib.auth.models import User
        staff_ids = list(month_qs.exclude(staff_id=None).values_list('staff_id', flat=True).distinct())
        if staff_ids:
            staff_list = [
                {'id': u.id, 'name': (u.get_full_name() or u.username)}
                for u in User.objects.filter(id__in=staff_ids).order_by('username')
            ]

    month_visits = [{
        'id': v.id,
        'client_name': v.client.name if v.client_id else '—',
        'day': v.scheduled_date.day,
        'start_time': v.start_time.strftime('%H:%M') if v.start_time else None,
        'end_time': v.end_time.strftime('%H:%M') if v.end_time else None,
        'status': v.status,
        'outcome': v.outcome,
        'staff_name': (v.staff.get_full_name() or v.staff.username) if v.staff_id else '—',
        'staff_id': v.staff_id,
        'purpose': v.purpose,
    } for v in month_qs]

    # -- history table (only served on the History tab) --
    tab = request.GET.get('tab', 'schedule')
    if tab == 'history':
        hist_qs = qs.filter(
            Q(status__in=[Visit.COMPLETED, Visit.CANCELLED]) |
            Q(status=Visit.PLANNED, scheduled_date__lt=today)
        ).order_by('-scheduled_date')
        paginator = Paginator(hist_qs, 10 if _is_mobile(request) else 15)
        page_obj = paginator.get_page(request.GET.get('page'))
        visits = [{
            'id': v.id,
            'client_id': v.client_id,
            'client_name': v.client.name if v.client_id else '',
            'staff_name': (v.staff.get_full_name() or v.staff.username) if v.staff_id else '',
            'scheduled_date': v.scheduled_date.strftime('%d/%m/%Y'),
            'time': _slot_label(v),
            'purpose': v.purpose,
            'status': v.status,
            'distance_meters': v.distance_meters,
        } for v in page_obj]
        pagination = {
            'number': page_obj.number,
            'num_pages': paginator.num_pages,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'previous_page_number': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page_number': page_obj.next_page_number() if page_obj.has_next() else None,
            'has_other_pages': page_obj.has_other_pages(),
            'range': _page_range_display(page_obj),
            'start_index': page_obj.start_index(),
            'end_index': page_obj.end_index(),
            'count': paginator.count,
        }
    else:
        tab = 'schedule'
        visits = None
        pagination = None

    scoped = Visit.objects.filter(company=active_company)
    if is_staff:
        scoped = scoped.filter(staff=request.user)

    return inertia_render(request, 'Visit/List', props={
        'tab': tab,
        'selected_date': selected_date.isoformat(),
        'year': selected_date.year,
        'month': selected_date.month,
        'staff_filter': staff_filter,
        'is_staff': is_staff,
        'staff_list': staff_list,
        'month_visits': month_visits,
        'visits': visits,
        'pagination': pagination,
        'total_count': scoped.count(),
    })


@require_perm('visits', 'create')
def visit_new(request):
    active_company = get_active_company(request)
    if request.method == 'POST':
        errors = _validate_visit(request.POST)
        slot_error = _check_slot(request, request.POST)
        if slot_error:
            errors['start_time'] = slot_error
        if errors:
            return inertia_render(request, 'Visit/Form', props={
                'visit': _visit_echo(request.POST), 'edit': False, 'errors': errors,
                'clients': _client_options(active_company),
            })
        visit = Visit.objects.create(
            company=active_company,
            client_id=request.POST.get('client_id') or None,
            staff=request.user,
            scheduled_date=_parse_date(request.POST.get('scheduled_date')),
            start_time=_parse_time(request.POST.get('start_time')),
            end_time=_parse_time(request.POST.get('end_time')),
            purpose=request.POST.get('purpose', '').strip(),
        )
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Visit', str(visit.pk), visit.company)
        messages.success(request, 'Visit appointment created.')
        return redirect('visit_detail', pk=visit.pk)

    return inertia_render(request, 'Visit/Form', props={
        'visit': None, 'edit': False, 'clients': _client_options(active_company),
    })


@require_perm('visits', 'edit')
def visit_edit(request, pk):
    visit = _get_visit(request, pk)
    if visit.status != Visit.PLANNED:
        messages.error(request, 'Only a planned visit can be edited.')
        return redirect('visit_detail', pk=visit.pk)

    active_company = get_active_company(request)
    if request.method == 'POST':
        errors = _validate_visit(request.POST)
        slot_error = _check_slot(request, request.POST, exclude_pk=visit.pk)
        if slot_error:
            errors['start_time'] = slot_error
        if errors:
            return inertia_render(request, 'Visit/Form', props={
                'visit': {**_visit_echo(request.POST), 'id': visit.pk}, 'edit': True, 'errors': errors,
                'clients': _client_options(active_company),
            })
        visit.client_id = request.POST.get('client_id') or None
        visit.scheduled_date = _parse_date(request.POST.get('scheduled_date'))
        visit.start_time = _parse_time(request.POST.get('start_time'))
        visit.end_time = _parse_time(request.POST.get('end_time'))
        visit.purpose = request.POST.get('purpose', '').strip()
        visit.save()
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Visit', str(visit.pk), visit.company)
        messages.success(request, 'Visit appointment updated.')
        return redirect('visit_detail', pk=visit.pk)

    return inertia_render(request, 'Visit/Form', props={
        'visit': {
            'id': visit.pk, 'client_id': visit.client_id,
            'scheduled_date': visit.scheduled_date.isoformat(),
            'start_time': visit.start_time.strftime('%H:%M') if visit.start_time else '',
            'end_time': visit.end_time.strftime('%H:%M') if visit.end_time else '',
            'purpose': visit.purpose,
        },
        'edit': True, 'clients': _client_options(active_company),
    })


@require_perm('visits', 'view')
def visit_detail(request, pk):
    visit = _get_visit(request, pk, Visit.objects.select_related('client', 'staff').prefetch_related('photos'))
    return inertia_render(request, 'Visit/Detail', props={
        'visit': {
            'id': visit.pk,
            'status': visit.status,
            'scheduled_date': visit.scheduled_date.strftime('%d/%m/%Y'),
            'time': _slot_label(visit),
            'purpose': visit.purpose,
            'result_notes': visit.result_notes,
            'next_follow_up_date': visit.next_follow_up_date.strftime('%d/%m/%Y') if visit.next_follow_up_date else None,
            'visited_at': visit.visited_at.strftime('%d/%m/%Y %H:%M') if visit.visited_at else None,
            'distance_meters': visit.distance_meters,
            'outcome': visit.outcome,
            'outcome_label': visit.get_outcome_display() if visit.outcome else None,
            'estimated_value': float(visit.estimated_value) if visit.estimated_value is not None else None,
            'pic_name': visit.pic_name,
            'pic_phone': visit.pic_phone,
            'checkin_lat': visit.checkin_lat,
            'checkin_lng': visit.checkin_lng,
            'client': {
                'id': visit.client.pk, 'name': visit.client.name,
                'lat': visit.client.lat, 'lng': visit.client.lng,
            } if visit.client_id else None,
            'staff_name': (visit.staff.get_full_name() or visit.staff.username) if visit.staff_id else '',
        },
        'photos': [{'id': p.id, 'url': p.file.url} for p in visit.photos.all()],
    })


@require_perm('visits', 'edit')
@require_POST
def visit_complete(request, pk):
    visit = _get_visit(request, pk)
    if visit.status != Visit.PLANNED:
        return JsonResponse({'error': 'This visit is no longer planned.'}, status=400)

    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    result_notes = (payload.get('result_notes') or '').strip()
    if not result_notes:
        return JsonResponse({'error': 'Please describe the visit outcome.'}, status=400)

    outcome = (payload.get('outcome') or '').strip().upper()
    valid_outcomes = {o[0] for o in Visit.OUTCOME_CHOICES}
    if outcome not in valid_outcomes:
        return JsonResponse({'error': 'Please choose a visit outcome.'}, status=400)

    estimated_value = None
    raw_value = (payload.get('estimated_value') or '').strip()
    if raw_value:
        try:
            estimated_value = Decimal(raw_value)
            if estimated_value < 0:
                return JsonResponse({'error': 'Estimated value cannot be negative.'}, status=400)
        except (InvalidOperation, ValueError):
            return JsonResponse({'error': 'Estimated value must be a number.'}, status=400)

    lat = _to_float_or_none(payload.get('checkin_lat'))
    lng = _to_float_or_none(payload.get('checkin_lng'))
    next_follow_up_date = _parse_date(payload.get('next_follow_up_date'))

    distance_meters = None
    if lat is not None and lng is not None and visit.client_id \
            and visit.client.lat is not None and visit.client.lng is not None:
        distance_meters = round(haversine_meters(lat, lng, visit.client.lat, visit.client.lng))

    visit.status = Visit.COMPLETED
    visit.visited_at = timezone.now()
    visit.checkin_lat = lat
    visit.checkin_lng = lng
    visit.distance_meters = distance_meters
    visit.outcome = outcome
    visit.estimated_value = estimated_value
    visit.pic_name = (payload.get('pic_name') or '').strip()[:120]
    visit.pic_phone = (payload.get('pic_phone') or '').strip()[:40]
    visit.result_notes = result_notes
    visit.next_follow_up_date = next_follow_up_date
    visit.save()

    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Visit', str(visit.pk), visit.company, ['completed'])
    return JsonResponse({'ok': True, 'distance_meters': distance_meters})


@require_perm('visits', 'edit')
@require_POST
def visit_cancel(request, pk):
    visit = _get_visit(request, pk)
    if visit.status != Visit.PLANNED:
        messages.error(request, 'Only a planned visit can be cancelled.')
        return redirect('visit_detail', pk=visit.pk)
    visit.status = Visit.CANCELLED
    visit.save(update_fields=['status', 'updated_at'])
    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Visit', str(visit.pk), visit.company, ['cancelled'])
    messages.success(request, 'Visit appointment cancelled.')
    return redirect('visit_detail', pk=visit.pk)


@require_perm('visits', 'edit')
@require_POST
def visit_photo_upload(request, pk):
    visit = _get_visit(request, pk)
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'error': 'No file'}, status=400)
    if f.size > 10 * 1024 * 1024:
        return JsonResponse({'error': 'File too large (max 10 MB)'}, status=400)

    header = f.read(2048)
    f.seek(0)
    detected_mime = magic.from_buffer(header, mime=True)
    if detected_mime not in _ALLOWED_PHOTO_MIME:
        return JsonResponse({'error': 'File type not allowed. Use JPG, PNG, or WEBP.'}, status=400)

    photo = VisitPhoto.objects.create(visit=visit, file=f)
    return JsonResponse({'id': photo.pk, 'url': photo.file.url})


@require_perm('visits', 'edit')
@require_POST
def visit_photo_delete(request, pk, photo_pk):
    visit = _get_visit(request, pk)
    photo = get_object_or_404(VisitPhoto, pk=photo_pk, visit=visit)
    try:
        if photo.file and os.path.isfile(photo.file.path):
            os.remove(photo.file.path)
    except Exception:
        pass
    photo.delete()
    return JsonResponse({'ok': True})


@require_perm('visits', 'export')
def visit_pdf(request, pk):
    visit = _get_visit(
        request, pk,
        Visit.objects.select_related('client', 'staff').prefetch_related('photos'),
    )
    photos = [{'path': p.file.path} for p in visit.photos.all()]
    ctx = {
        'visit': visit,
        'photos': photos,
        'logo_rel_path': _logo_file_url(visit.company),
        'now': datetime.now(),
    }
    html = render_to_string('hw/visit/visit_pdf.html', ctx)
    from weasyprint import HTML
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="visit-{visit.pk}.pdf"'
    return response


def _visit_bucket():
    return {
        'total': 0, 'completed': 0, 'cancelled': 0, 'planned': 0,
        'distance_meters': 0, 'value_sar': 0,
    }


def _accumulate_visit(v, bucket):
    bucket['total'] += 1
    if v.status == Visit.COMPLETED:
        bucket['completed'] += 1
        bucket['distance_meters'] += v.distance_meters or 0
        bucket['value_sar'] += float(v.estimated_value or 0)
    elif v.status == Visit.CANCELLED:
        bucket['cancelled'] += 1
    else:
        bucket['planned'] += 1


@require_perm('visits', 'view')
def visit_recap(request):
    active_company = get_active_company(request)
    qs = Visit.objects.filter(company=active_company).select_related('client', 'staff')
    if get_role(request.user) == Role.STAFF.value:
        qs = qs.filter(staff=request.user)

    monthly = {}
    for v in qs.order_by('scheduled_date'):
        key = v.scheduled_date.strftime('%Y-%m')
        m = monthly.get(key)
        if m is None:
            m = monthly[key] = {
                'label': v.scheduled_date.strftime('%B %Y'),
                'period': key,
                **_visit_bucket(),
                'outcomes': {
                    o[0]: {'key': o[0], 'label': o[1], 'count': 0}
                    for o in Visit.OUTCOME_CHOICES
                },
                'staffs': {},
            }
        _accumulate_visit(v, m)
        if v.status == Visit.COMPLETED and v.outcome in m['outcomes']:
            m['outcomes'][v.outcome]['count'] += 1
        staff_name = (v.staff.get_full_name() or v.staff.username) if v.staff_id else '—'
        s = m['staffs'].get(staff_name)
        if s is None:
            s = m['staffs'][staff_name] = {'name': staff_name, **_visit_bucket()}
        _accumulate_visit(v, s)

    months = []
    for key in sorted(monthly, reverse=True):
        m = monthly[key]
        months.append({
            'label': m['label'],
            'period': m['period'],
            'total': m['total'],
            'completed': m['completed'],
            'cancelled': m['cancelled'],
            'planned': m['planned'],
            'completion_rate': round(m['completed'] / m['total'] * 100) if m['total'] else 0,
            'total_value_sar': m['value_sar'],
            'total_distance_meters': m['distance_meters'],
            'outcomes': list(m['outcomes'].values()),
            'staffs': list(m['staffs'].values()),
        })

    return inertia_render(request, 'Visit/Recap', props={'monthly': months})
