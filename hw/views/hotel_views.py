import json as _json

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Hotel, Occupancy, RoomType, RoomView, log_activity
from ..permissions import require_perm
from .helpers import _is_mobile, get_active_company, pagination_props, snapshot_fields, track_changes


def _save_hotel(h, data):
    h.name    = data.get('name', '').strip()
    h.city    = data.get('city', 'makkah')
    h.stars   = int(data.get('stars') or 3)
    h.area    = data.get('area', '').strip()
    h.note    = data.get('note', '').strip()
    h.is_active = data.get('is_active') == 'on'
    try:
        h.lat = float(data['lat']) if data.get('lat') else None
    except (ValueError, TypeError):
        h.lat = None
    try:
        h.lng = float(data['lng']) if data.get('lng') else None
    except (ValueError, TypeError):
        h.lng = None
    try:
        val = data.get('avg_occupancy', '').strip()
        h.avg_occupancy = float(val) if val else None
    except (ValueError, TypeError):
        h.avg_occupancy = None
    route_raw = data.get('route', '').strip()
    try:
        parsed = _json.loads(route_raw) if route_raw else None
        h.route = parsed if isinstance(parsed, list) and len(parsed) > 0 else None
    except (ValueError, TypeError):
        h.route = None
    h.save()


def _save_hotel_room_types(h, data):
    # Finding 1 fix: only reconcile if room_types key is actually present in POST data
    if 'room_types' not in data:
        return

    try:
        room_types = _json.loads(data.get('room_types', '[]') or '[]')
    except (ValueError, TypeError):
        room_types = []

    valid_occupancy = {c for c, _ in Occupancy.choices}
    valid_view = {c for c, _ in RoomView.choices}

    # Finding 2 fix: wrap in transaction.atomic() to prevent partial commits
    with transaction.atomic():
        kept_ids = set()
        for rt_data in room_types:
            name = (rt_data.get('name') or '').strip()
            if not name:
                continue
            try:
                capacity = max(1, int(rt_data.get('capacity') or 1))
            except (ValueError, TypeError):
                capacity = 1
            # Optional structured fields (v2.0 §8.2-8.3) — silently blanked if
            # the client sends something outside the controlled vocabulary.
            occupancy = rt_data.get('occupancy') or ''
            occupancy = occupancy if occupancy in valid_occupancy else ''
            view = rt_data.get('view') or ''
            view = view if view in valid_view else ''
            rt_id = rt_data.get('id')
            if rt_id:
                RoomType.objects.filter(pk=rt_id, hotel=h).update(
                    name=name, capacity=capacity, occupancy=occupancy, view=view, is_active=True,
                )
                kept_ids.add(int(rt_id))
            else:
                # Finding 2 fix: look up by name first (including soft-deleted) to avoid IntegrityError
                try:
                    rt = RoomType.objects.get(hotel=h, name=name)
                    # Reactivate and update capacity
                    rt.capacity = capacity
                    rt.occupancy = occupancy
                    rt.view = view
                    rt.is_active = True
                    rt.save()
                    kept_ids.add(rt.pk)
                except RoomType.DoesNotExist:
                    # Create new if name doesn't exist
                    rt = RoomType.objects.create(hotel=h, name=name, capacity=capacity, occupancy=occupancy, view=view)
                    kept_ids.add(rt.pk)

        h.room_types.exclude(pk__in=kept_ids).update(is_active=False)


@require_perm('hotels', 'view')
def hotel_list(request):
    company = get_active_company(request)
    qs = Hotel.objects.filter(company=company)
    q            = request.GET.get('q', '').strip()
    area_filter  = request.GET.get('area', '').strip()
    city_filter  = request.GET.get('city', '').strip()
    stars_filter = request.GET.get('stars', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(area__icontains=q))
    if area_filter:
        qs = qs.filter(area__icontains=area_filter)
    if city_filter in ('makkah', 'madinah'):
        qs = qs.filter(city=city_filter)
    if stars_filter.isdigit():
        qs = qs.filter(stars=int(stars_filter))
    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    hotels = [{
        "id": h.id,
        "name": h.name,
        "city": h.city,
        "city_display": h.get_city_display(),
        "area": h.area,
        "stars": h.stars,
        "distance": h.distance_to_haram,
        "distance_label": h.distance_label,
        "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None,
        "is_active": h.is_active,
    } for h in page_obj]

    return inertia_render(request, "Hotel/List", props={
        "hotels": hotels,
        "total_count": paginator.count,
        "q": q,
        "city_filter": city_filter,
        "stars_filter": stars_filter,
        "area_filter": area_filter,
        "pagination": pagination_props(page_obj),
    })


@require_perm('hotels', 'create')
def hotel_new(request):
    company = get_active_company(request)
    if request.method == 'POST':
        h = Hotel(company=company)
        _save_hotel(h, request.POST)
        _save_hotel_room_types(h, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Hotel', h.name, h.company)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/Form", props={"edit": False, "hotel": None})


@require_perm('hotels', 'edit')
def hotel_edit(request, pk):
    h = get_object_or_404(Hotel, pk=pk, company=get_active_company(request))
    if request.method == 'POST':
        _before = snapshot_fields(h, ['name', 'city', 'area', 'stars'])
        _save_hotel(h, request.POST)
        _save_hotel_room_types(h, request.POST)
        _after = snapshot_fields(h, ['name', 'city', 'area', 'stars'])
        changes = track_changes(
            _before, _after,
            labels={'name': 'Nama', 'city': 'Kota', 'area': 'Area', 'stars': 'Bintang'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', h.name, h.company, changes)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/Form", props={
        "edit": True,
        "hotel": {
            "id": h.id, "name": h.name, "city": h.city, "stars": h.stars,
            "area": h.area, "note": h.note, "is_active": h.is_active,
            "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None,
            "lat": h.lat, "lng": h.lng, "route": h.route,
            "room_types": [
                {"id": rt.id, "name": rt.name, "capacity": rt.capacity,
                 "occupancy": rt.occupancy, "view": rt.view}
                for rt in h.room_types.filter(is_active=True).order_by('name')
            ],
        },
    })


@require_perm('hotels', 'delete')
@require_POST
def hotel_delete(request, pk):
    h = get_object_or_404(Hotel, pk=pk, company=get_active_company(request))
    name = h.name
    h.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Hotel', name, h.company)
    return redirect('hotel_list')


@require_perm('hotels', 'view')
def hotel_detail(request, pk):
    h = get_object_or_404(Hotel, pk=pk, company=get_active_company(request))
    return inertia_render(request, "Hotel/Detail", props={
        "hotel": {
            "id": h.id,
            "name": h.name,
            "city": h.city,
            "city_display": h.get_city_display(),
            "area": h.area,
            "stars": h.stars,
            "distance": h.distance_to_haram,
            "distance_label": h.distance_label,
            "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None,
            "note": h.note,
            "is_active": h.is_active,
            "lat": h.lat,
            "lng": h.lng,
            "ref_label": h.ref_label,
            "route": h.route,
        },
    })


@require_perm('hotels', 'view')
def hotel_map(request):
    return inertia_render(request, "Hotel/Map")


@require_perm('hotels', 'view')
def hotel_map_data(request):
    company = get_active_company(request)
    hotels = []
    for h in Hotel.objects.filter(company=company, is_active=True):
        if h.lat is None or h.lng is None:
            continue
        d = h.distance_to_haram
        hotels.append({
            'pk':      h.pk,
            'name':    h.name,
            'city':    h.city,
            'stars':   h.stars,
            'area':    h.area,
            'lat':     h.lat,
            'lng':     h.lng,
            'distance': d,
            'distance_label': h.distance_label,
            'ref_label': h.ref_label,
            'avg':     float(h.avg_occupancy) if h.avg_occupancy else None,
            'route':   h.route,
            'url':     reverse('hotel_detail', args=[h.pk]),
        })
    return JsonResponse({'hotels': hotels})
