import json as _json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Hotel, MealPlan, RoomType, RoomView, log_activity, room_type_name
from ..models.hotel import OCCUPANCY_BY_CAPACITY
from ..permissions import require_perm
from .helpers import _is_mobile, pagination_props, snapshot_fields, track_changes


def _hotel_error(data, instance=None):
    """Alasan form hotel ditolak (None bila sah). Aturannya sama dengan
    constraint di tabel — nama unik per kota, bintang 1–5 — supaya yang sampai
    ke user berupa pesan, bukan IntegrityError."""
    from ..models.choices import HotelCity
    name = data.get('name', '').strip()
    if not name:
        return 'Hotel name is required.'
    city = data.get('city', 'makkah')
    if city not in {c for c, _ in HotelCity.choices}:
        return 'Choose Makkah or Madinah.'
    try:
        stars = int(data.get('stars') or 3)
    except (ValueError, TypeError):
        stars = 0
    if not 1 <= stars <= 5:
        return 'Stars must be between 1 and 5.'
    clash = Hotel.objects.filter(city=city, name__iexact=name)
    if instance is not None and instance.pk:
        clash = clash.exclude(pk=instance.pk)
    if clash.exists():
        return f'Hotel "{name}" already exists in {dict(HotelCity.choices)[city]}.'
    return None


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


def _clean_room_type_fields(data):
    """Normalise one room type's POSTed fields.

    View is optional (v2.0 §8.3), so a value outside the controlled vocabulary
    is blanked rather than rejected — a stale client cannot wedge the form
    that way. Occupancy is not taken from the client at all: RoomType.save()
    derives it from capacity.
    """
    try:
        capacity = min(10, max(1, int(data.get('capacity') or 1)))
    except (ValueError, TypeError):
        capacity = 1
    view = data.get('view') or ''
    return {
        'name': (data.get('name') or '').strip(),
        'capacity': capacity,
        'view': view if view in {c for c, _ in RoomView.choices} else '',
    }


def _room_type_name_error(name, clashing):
    if not name:
        return 'Nama tipe kamar wajib diisi.'
    if clashing.exists():
        return 'Tipe kamar dengan nama ini sudah ada di hotel ini.'
    return None


def _room_type_form_props(h, rt=None, form_data=None, errors=None):
    return {
        "hotel": {"id": h.id, "name": h.name},
        "room_type": form_data if form_data is not None else ({
            "name": rt.name, "capacity": rt.capacity, "view": rt.view,
        } if rt else None),
        # Feeds the live name suggestion (roomTypeName.js), so the form and
        # room_type_name() read the same words.
        "occupancy_labels": {str(c): o.label for c, o in OCCUPANCY_BY_CAPACITY.items()},
        "view_choices": [{"value": v, "label": l} for v, l in RoomView.choices],
        "edit": rt is not None,
        "action": (
            reverse('room_type_edit', args=[h.pk, rt.pk]) if rt
            else reverse('room_type_new', args=[h.pk])
        ),
        "errors": errors or {},
    }


@require_perm('hotels', 'view')
def hotel_list(request):
    qs = Hotel.objects.all()
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
    if request.method == 'POST':
        error = _hotel_error(request.POST)
        if error:
            messages.error(request, error)
            return redirect('hotel_new')
        h = Hotel()
        _save_hotel(h, request.POST)
        # Same starting point migration 0104 gave every existing hotel: allow
        # the whole active master, then narrow it from the detail page.
        # Starting empty would leave only new hotels on free-text Meals.
        h.meal_plans.set(MealPlan.objects.filter(is_active=True))
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Hotel', h.name)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/Form", props={"edit": False, "hotel": None})


@require_perm('hotels', 'edit')
def hotel_edit(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    if request.method == 'POST':
        error = _hotel_error(request.POST, instance=h)
        if error:
            messages.error(request, error)
            return redirect('hotel_edit', pk=h.pk)
        _before = snapshot_fields(h, ['name', 'city', 'area', 'stars'])
        _save_hotel(h, request.POST)
        _after = snapshot_fields(h, ['name', 'city', 'area', 'stars'])
        changes = track_changes(
            _before, _after,
            labels={'name': 'Nama', 'city': 'Kota', 'area': 'Area', 'stars': 'Bintang'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', h.name, changes)
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


@require_perm('hotels', 'delete')
@require_POST
def hotel_delete(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    name = h.name
    h.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Hotel', name)
    return redirect('hotel_list')


@require_perm('hotels', 'view')
def hotel_detail(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
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
            "room_types": [
                {
                    "id": rt.id,
                    "name": rt.name,
                    "capacity": rt.capacity,
                    "view": rt.get_view_display(),
                }
                for rt in h.room_types.filter(is_active=True).order_by('name')
            ],
            "meal_plans": [
                {"code": mp.code, "name": mp.name}
                for mp in h.meal_plans.filter(is_active=True).order_by('code')
            ],
        },
    })


@require_perm('hotels', 'edit')
def room_type_new(request, hotel_pk):
    h = get_object_or_404(Hotel, pk=hotel_pk)
    if request.method == 'POST':
        fields = _clean_room_type_fields(request.POST)
        # Only an *active* row blocks the name. One that was soft-removed is
        # reused below instead, so a type can be brought back without leaving
        # a second row behind the unique constraint.
        error = _room_type_name_error(
            fields['name'], h.room_types.filter(name=fields['name'], is_active=True),
        )
        if error:
            return inertia_render(request, "Hotel/RoomTypeForm", props=_room_type_form_props(
                h, form_data=fields, errors={"name": error},
            ))
        rt, created = RoomType.objects.update_or_create(
            hotel=h, name=fields['name'], defaults={**fields, 'is_active': True},
        )
        log_activity(
            request.user,
            ActivityLog.ACTION_CREATE if created else ActivityLog.ACTION_EDIT,
            'Room Type', f'{rt.name} — {h.name}',
        )
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/RoomTypeForm", props=_room_type_form_props(h))


@require_perm('hotels', 'edit')
def room_type_edit(request, hotel_pk, pk):
    h = get_object_or_404(Hotel, pk=hotel_pk)
    rt = get_object_or_404(RoomType, pk=pk, hotel=h)
    if request.method == 'POST':
        fields = _clean_room_type_fields(request.POST)
        # Renaming is stricter than creating: a soft-removed row holding the
        # target name still occupies it, and silently deleting that row would
        # blank Room.room_type_ref on every CL that used it.
        error = _room_type_name_error(
            fields['name'], h.room_types.filter(name=fields['name']).exclude(pk=rt.pk),
        )
        if error:
            return inertia_render(request, "Hotel/RoomTypeForm", props=_room_type_form_props(
                h, rt=rt, form_data=fields, errors={"name": error},
            ))
        for field, value in fields.items():
            setattr(rt, field, value)
        rt.is_active = True
        rt.save()
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Room Type', f'{rt.name} — {h.name}')
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/RoomTypeForm", props=_room_type_form_props(h, rt=rt))


def _json_list(raw):
    try:
        value = _json.loads(raw or '[]')
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


# "Other" names nothing, so a generated "Double Other" would be useless.
_BULK_VIEWS = [(v, l) for v, l in RoomView.choices if v != RoomView.OTHER]


@require_perm('hotels', 'edit')
def room_type_bulk(request, hotel_pk):
    """Create the usual occupancy × view grid in one go.

    A combination whose name is already an active type is skipped, never
    overwritten — the operator may have tuned it. A soft-removed one is
    brought back, same as room_type_new does.
    """
    h = get_object_or_404(Hotel, pk=hotel_pk)
    if request.method == 'POST':
        capacities = [c for c in OCCUPANCY_BY_CAPACITY if c in {
            int(x) for x in _json_list(request.POST.get('capacities')) if str(x).isdigit()
        }]
        picked = {str(v) for v in _json_list(request.POST.get('views'))}
        views = [v for v, _ in _BULK_VIEWS if v in picked] or ['']
        if not capacities:
            return inertia_render(request, "Hotel/RoomTypeBulkForm", props={
                **_room_type_bulk_props(h),
                "errors": {"capacities": "Pilih minimal satu kapasitas."},
            })
        created = skipped = 0
        with transaction.atomic():
            for view in views:
                for capacity in capacities:
                    name = room_type_name(capacity, view)
                    rt = h.room_types.filter(name=name).first()
                    if rt and rt.is_active:
                        skipped += 1
                        continue
                    RoomType.objects.update_or_create(
                        hotel=h, name=name,
                        defaults={'capacity': capacity, 'view': view, 'is_active': True},
                    )
                    created += 1
        if created:
            log_activity(request.user, ActivityLog.ACTION_CREATE, 'Room Type',
                         f'{created} tipe kamar (sekaligus) — {h.name}')
        msg = f'{created} tipe kamar ditambahkan.'
        if skipped:
            msg += f' {skipped} dilewati karena sudah ada.'
        messages.success(request, msg)
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/RoomTypeBulkForm", props=_room_type_bulk_props(h))


def _room_type_bulk_props(h):
    return {
        "hotel": {"id": h.id, "name": h.name},
        "capacity_choices": [{"value": c, "label": o.label} for c, o in OCCUPANCY_BY_CAPACITY.items()],
        "view_choices": [{"value": v, "label": l} for v, l in _BULK_VIEWS],
        # Lets the preview mark what will be skipped before anything is sent.
        "existing_names": list(h.room_types.filter(is_active=True).values_list('name', flat=True)),
        # Structured so the form can pre-check the capacity/view pairs the
        # hotel already sells — nothing already present is created again.
        "existing_pairs": [
            {"capacity": r.capacity, "view": r.view}
            for r in h.room_types.filter(is_active=True).order_by('capacity', 'name')
        ],
        "errors": {},
    }


@require_perm('hotels', 'edit')
@require_POST
def room_type_delete(request, hotel_pk, pk):
    h = get_object_or_404(Hotel, pk=hotel_pk)
    rt = get_object_or_404(RoomType, pk=pk, hotel=h)
    # Soft delete — CLs point at this row through Room.room_type_ref, and a
    # hard delete would blank that link on every past booking.
    rt.is_active = False
    rt.save(update_fields=['is_active', 'updated_at'])
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Room Type', f'{rt.name} — {h.name}')
    return redirect('hotel_detail', pk=h.pk)


@require_perm('hotels', 'edit')
def hotel_meal_plans(request, hotel_pk):
    """Narrow the global MealPlan master down to what this hotel sells.

    Nothing is created here — the codes are a fixed master (v2.0 §10), so this
    is a set selection, which is why it is one checkbox form rather than the
    add/edit/remove rows the room-type catalog gets.
    """
    h = get_object_or_404(Hotel, pk=hotel_pk)
    available = MealPlan.objects.filter(is_active=True).order_by('code')
    if request.method == 'POST':
        try:
            codes = _json.loads(request.POST.get('meal_plans', '[]') or '[]')
        except (ValueError, TypeError):
            codes = None
        # A garbled payload leaves the selection alone: wiping it would be a
        # silent, surprising loss, and the real form always sends a list.
        if isinstance(codes, list):
            # Codes outside the active master are dropped silently, same as
            # the occupancy/view vocabulary.
            h.meal_plans.set(available.filter(code__in=[str(c) for c in codes]))
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', f'{h.name} — Meal Plans')
        return redirect('hotel_detail', pk=h.pk)
    return inertia_render(request, "Hotel/MealPlanForm", props={
        "hotel": {"id": h.id, "name": h.name},
        "available": [{"code": mp.code, "name": mp.name} for mp in available],
        "selected": list(h.meal_plans.filter(is_active=True).values_list('code', flat=True)),
    })


@require_perm('hotels', 'view')
def hotel_map(request):
    return inertia_render(request, "Hotel/Map")


@require_perm('hotels', 'view')
def hotel_map_data(request):
    hotels = []
    for h in Hotel.objects.filter(is_active=True):
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
