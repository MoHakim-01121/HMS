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

from ..i18n import tr
from ..models import ActivityLog, Hotel, MealPlan, RoomType, RoomView, log_activity, room_type_name
from ..models.hotel import OCCUPANCY_BY_CAPACITY
from ..permissions import require_perm
from .helpers import csv_export_response, pagination_props, snapshot_fields, track_changes


def _hotel_error(data, instance=None):
    """Alasan form hotel ditolak (None bila sah). Aturannya sama dengan
    constraint di tabel — nama unik per kota, bintang 1–5 — supaya yang sampai
    ke user berupa pesan, bukan IntegrityError."""
    from ..models.choices import HotelCity
    name = data.get('name', '').strip()
    if not name:
        return 'Hotel name is required.'
    city = data.get('city', '')
    if city not in {c for c, _ in HotelCity.choices}:
        return 'Choose Makkah or Madinah.'
    if not data.get('stars'):
        return 'Choose the stars.'
    try:
        stars = int(data['stars'])
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


def _hotel_echo(data):
    """The submitted form, shaped like the form's `hotel` prop, so a rejected
    save comes back with what the user typed instead of an empty form."""
    def num(key):
        try:
            return float(data[key]) if data.get(key) else None
        except (ValueError, TypeError):
            return None
    return {
        "name": data.get('name', ''), "city": data.get('city', ''), "stars": int(data['stars']) if str(data.get('stars', '')).isdigit() else '',
        "area": data.get('area', ''), "note": data.get('note', ''),
        "is_active": data.get('is_active') == 'on', "has_allotment": data.get('has_allotment') == 'on',
        "avg_occupancy": num('avg_occupancy'), "lat": num('lat'), "lng": num('lng'),
    }


def _save_hotel(h, data):
    h.name    = data.get('name', '').strip()
    h.city    = data.get('city', 'makkah')
    h.stars   = int(data.get('stars') or 3)
    h.area    = data.get('area', '').strip()
    h.note    = data.get('note', '').strip()
    h.is_active = data.get('is_active') == 'on'
    h.has_allotment = data.get('has_allotment') == 'on'
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
    # The hotel form no longer edits the walking route (location is only
    # coordinates now), so a save without the field keeps the stored one.
    if 'route' in data:
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


# Yes/no filters of the hotel list: ?key=a,b → the Q each value adds. Picking
# both values of one pair is the same as picking neither.
_HOTEL_FLAG_FILTERS = {
    'allotment': {'yes': Q(has_allotment=True), 'no': Q(has_allotment=False)},
    'status': {'active': Q(is_active=True), 'inactive': Q(is_active=False)},
    'location': {
        'set': Q(lat__isnull=False, lng__isnull=False),
        'missing': Q(lat__isnull=True) | Q(lng__isnull=True),
    },
}


def _hotel_list_qs(request):
    """Hotels matching the list's search and filters (city, stars,
    allotment, status, location)."""
    from .helpers import csv_list
    qs = Hotel.objects.all()
    q = request.GET.get('q', '').strip()
    cities = csv_list(request, 'city', ['makkah', 'madinah'])
    stars = [int(x) for x in csv_list(request, 'stars', ['1', '2', '3', '4', '5'])]
    flags = {k: csv_list(request, k, list(opts)) for k, opts in _HOTEL_FLAG_FILTERS.items()}
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(area__icontains=q))
    base = qs
    if cities:
        qs = qs.filter(city__in=cities)
    if stars:
        qs = qs.filter(stars__in=stars)
    for key, picked in flags.items():
        if picked:
            cond = Q()
            for v in picked:
                cond |= _HOTEL_FLAG_FILTERS[key][v]
            qs = qs.filter(cond)
    sort = request.GET.get('sort', 'name')
    return base, qs.order_by('-name' if sort == '-name' else 'name'), {
        'q': q, 'city': cities, 'stars': [str(x) for x in stars], **flags, 'sort': sort,
    }


@require_perm('hotels', 'view')
def hotel_list(request):
    """Hotel list (Record View HMS canvas): no KPIs, city and stars in Filter."""
    from django.db.models import Count

    from .helpers import list_per_page
    base, qs, filters = _hotel_list_qs(request)
    page_obj = Paginator(qs, list_per_page(request)).get_page(request.GET.get('page'))
    hotels = [{
        "id": h.id, "name": h.name, "city": h.city, "city_display": h.get_city_display(), "area": h.area,
        "stars": h.stars, "distance": h.distance_to_haram, "distance_label": h.distance_label,
        "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None, "is_active": h.is_active,
        "has_allotment": h.has_allotment,
    } for h in page_obj]
    return inertia_render(request, "Hotel/List", props={
        "hotels": hotels,
        "total": Hotel.objects.count(),
        "filters": {**filters, "per": list_per_page(request)},
        "counts": {
            "city": {r['city']: r['n'] for r in base.values('city').annotate(n=Count('id'))},
            "stars": {str(r['stars']): r['n'] for r in base.values('stars').annotate(n=Count('id'))},
            **{key: {v: base.filter(cond).count() for v, cond in opts.items()} for key, opts in _HOTEL_FLAG_FILTERS.items()},
            "all": base.count(),
        },
        "pagination": pagination_props(page_obj),
    })


@require_perm('hotels', 'export')
def hotel_export_csv(request):
    _, qs, _ = _hotel_list_qs(request)
    return csv_export_response('hotels.csv', ['Hotel', 'City', 'Area', 'Stars', 'Allotment', 'Avg pax', 'Distance to mosque', 'Status'], [
        [h.name, h.get_city_display(), h.area, h.stars, 'Yes' if h.has_allotment else 'No', h.avg_occupancy or '', h.distance_label, 'Active' if h.is_active else 'Inactive']
        for h in qs
    ])


@require_perm('hotels', 'create')
def hotel_new(request):
    if request.method == 'POST':
        error = _hotel_error(request.POST)
        if error:
            return inertia_render(request, "Hotel/Form", props={
                "edit": False, "hotel": _hotel_echo(request.POST), "error": error,
            })
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
            return inertia_render(request, "Hotel/Form", props={
                "edit": True, "hotel": {**_hotel_echo(request.POST), "id": h.id}, "error": error,
            })
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
            "area": h.area, "note": h.note, "is_active": h.is_active, "has_allotment": h.has_allotment,
            "avg_occupancy": float(h.avg_occupancy) if h.avg_occupancy else None,
            "lat": h.lat, "lng": h.lng, "route": h.route,
        },
    })


@require_perm('hotels', 'edit')
@require_POST
def hotel_toggle_active(request, pk):
    """Deactivate / activate in one click: the reversible way to retire a
    hotel, which Delete refuses once a CL names it."""
    h = get_object_or_404(Hotel, pk=pk)
    h.is_active = not h.is_active
    h.save(update_fields=['is_active', 'updated_at'])
    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Hotel', h.name,
                 [{'label': 'Status', 'before': 'Inactive' if h.is_active else 'Active',
                   'after': 'Active' if h.is_active else 'Inactive'}])
    messages.success(request, tr(request, f'Hotel "{h.name}" is now {"active" if h.is_active else "inactive"}.', f'Hotel "{h.name}" sekarang {"aktif" if h.is_active else "nonaktif"}.'))
    return redirect('hotel_detail', pk=pk)


@require_perm('hotels', 'delete')
@require_POST
def hotel_delete(request, pk):
    h = get_object_or_404(Hotel, pk=pk)
    name = h.name
    # A hotel named on a CL is PROTECTed: deleting it would leave the
    # bookings without their hotel. Say so instead of failing with a 500.
    used = h.confirmation_letters.count()
    if used:
        messages.error(request, tr(request, f'Hotel "{name}" is used by {used} CL and cannot be deleted. Set it to Inactive instead.', f'Hotel "{name}" dipakai {used} CL dan tidak bisa dihapus. Nonaktifkan saja.'))
        return redirect('hotel_detail', pk=pk)
    h.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Hotel', name)
    messages.success(request, tr(request, f'Hotel "{name}" deleted.', f'Hotel "{name}" dihapus.'))
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
            "has_allotment": h.has_allotment,
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
        msg = tr(request, f'{created} room types added.', f'{created} tipe kamar ditambahkan.')
        if skipped:
            msg += tr(request, f' {skipped} skipped because they already exist.', f' {skipped} dilewati karena sudah ada.')
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
    messages.success(request, tr(request, f'Room type "{rt.name}" removed.', f'Tipe kamar "{rt.name}" dihapus.'))
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
