import json as _json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import Hotel


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
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=q) | Q(area__icontains=q))
    if area_filter:
        qs = qs.filter(area__icontains=area_filter)
    if city_filter in ('makkah', 'madinah'):
        qs = qs.filter(city=city_filter)
    if stars_filter.isdigit():
        qs = qs.filter(stars=int(stars_filter))
    areas = Hotel.objects.filter(company=company).exclude(area='').values_list('area', flat=True).distinct().order_by('area')
    return render(request, 'invoices/hotel/hotel_list.html', {
        'hotels': qs,
        'q': q,
        'area_filter': area_filter,
        'city_filter': city_filter,
        'stars_filter': stars_filter,
        'areas': areas,
    })


@login_required
def hotel_new(request):
    company = request.session.get('active_company')
    if request.method == 'POST':
        h = Hotel(company=company)
        _save_hotel(h, request.POST)
        from ..models import log_activity, ActivityLog
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Hotel', h.name, h.company)
        return redirect('hotel_detail', pk=h.pk)
    return render(request, 'invoices/hotel/hotel_form.html', {'edit': False})


@login_required
def hotel_edit(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    if request.method == 'POST':
        from ..models import log_activity, ActivityLog
        _before = {'Nama': h.name, 'Kota': h.city, 'Area': h.area, 'Bintang': str(h.stars)}
        _save_hotel(h, request.POST)
        _after  = {'Nama': h.name, 'Kota': h.city, 'Area': h.area, 'Bintang': str(h.stars)}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', h.name, h.company, changes)
        return redirect('hotel_detail', pk=h.pk)
    return render(request, 'invoices/hotel/hotel_form.html', {
        'hotel': h,
        'edit': True,
        'hotel_route_json': _json.dumps(h.route) if h.route else 'null',
    })


@login_required
@require_POST
def hotel_delete(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    name = h.name
    h.delete()
    from ..models import log_activity, ActivityLog
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Hotel', name, h.company)
    return redirect('hotel_list')


@login_required
def hotel_detail(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    return render(request, 'invoices/hotel/hotel_detail.html', {
        'hotel': h,
        'hotel_route_json': _json.dumps(h.route) if h.route else 'null',
    })


@login_required
def hotel_map(request):
    return render(request, 'invoices/hotel/hotel_map.html')


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
