import json as _json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Hotel, log_activity
from .helpers import _is_mobile, _page_range_display


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


@login_required
def hotel_list(request):
    company = request.session.get('active_company')
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
        "pagination": {
            "number": page_obj.number,
            "num_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
            "has_other_pages": page_obj.has_other_pages(),
            "range": _page_range_display(page_obj),
        },
    })


@login_required
def hotel_new(request):
    company = request.session.get('active_company')
    if request.method == 'POST':
        h = Hotel(company=company)
        _save_hotel(h, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Hotel', h.name, h.company)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/Form", props={"edit": False, "hotel": None})


@login_required
def hotel_edit(request, pk):
    company = request.session.get('active_company')
    filters = {'pk': pk}
    if company:
        filters['company'] = company
    h = get_object_or_404(Hotel, **filters)
    if request.method == 'POST':
        _before = {'Nama': h.name, 'Kota': h.city, 'Area': h.area, 'Bintang': str(h.stars)}
        _save_hotel(h, request.POST)
        _after  = {'Nama': h.name, 'Kota': h.city, 'Area': h.area, 'Bintang': str(h.stars)}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', h.name, h.company, changes)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/Form", props={
        "edit": True,
        "hotel": {
            "id": h.id, "name": h.name, "city": h.city, "stars": h.stars,
            "area": h.area, "note": h.note, "is_active": h.is_active,
            "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None,
            "lat": h.lat, "lng": h.lng, "route": h.route,
        },
    })


@login_required
@require_POST
def hotel_delete(request, pk):
    company = request.session.get('active_company')
    filters = {'pk': pk}
    if company:
        filters['company'] = company
    h = get_object_or_404(Hotel, **filters)
    name = h.name
    h.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Hotel', name, h.company)
    return redirect('hotel_list')


@login_required
def hotel_detail(request, pk):
    company = request.session.get('active_company')
    filters = {'pk': pk}
    if company:
        filters['company'] = company
    h = get_object_or_404(Hotel, **filters)
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


@login_required
def hotel_map(request):
    return inertia_render(request, "Hotel/Map")


@login_required
def hotel_map_data(request):
    company = request.session.get('active_company')
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
