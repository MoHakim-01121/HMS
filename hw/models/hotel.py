import math

from django.db import models
from django.urls import reverse

from .choices import HotelCity

HARAM_LAT  = 21.420324; HARAM_LNG  = 39.826485
NABAWI_LAT = 24.4672;   NABAWI_LNG = 39.6112


class Hotel(models.Model):
    name          = models.CharField(max_length=200, db_index=True)
    city          = models.CharField(max_length=20, choices=HotelCity.choices, default=HotelCity.MAKKAH)
    stars         = models.PositiveSmallIntegerField(default=3)
    area          = models.CharField(max_length=100, blank=True)
    lat           = models.FloatField(null=True, blank=True)
    lng           = models.FloatField(null=True, blank=True)
    avg_occupancy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Rata-rata orang per kamar, mis. 3.4',
    )
    # The hotel holds rooms for us on contract (allotment), or we book per request.
    has_allotment = models.BooleanField(default=False)
    note          = models.TextField(blank=True)
    route         = models.JSONField(null=True, blank=True,
                                     help_text='Intermediate waypoints [[lat,lng],...] between mosque and hotel')
    # Which board types this hotel actually sells (v2.0 §10). MealPlan itself
    # is a global master — this only narrows it per hotel, and the CL form uses
    # the narrowed set as its Meals dropdown.
    meal_plans    = models.ManyToManyField('MealPlan', blank=True, related_name='hotels')
    is_active     = models.BooleanField(default=True, db_index=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Hotel'
        verbose_name_plural = 'Hotels'
        constraints = [
            models.UniqueConstraint(fields=['city', 'name'], name='uniq_hotel_city_name'),
            models.CheckConstraint(
                condition=models.Q(stars__gte=1, stars__lte=5), name='hotel_stars_1_to_5',
            ),
            models.CheckConstraint(
                condition=models.Q(city__in=[c[0] for c in HotelCity.choices]), name='hotel_city_valid',
            ),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('hotel_detail', args=[self.pk])

    @property
    def ref_point(self):
        if self.city == HotelCity.MADINAH:
            return NABAWI_LAT, NABAWI_LNG
        return HARAM_LAT, HARAM_LNG

    @property
    def ref_label(self):
        return 'Masjid Nabawi' if self.city == HotelCity.MADINAH else 'Masjid Al-Haram'

    @property
    def distance_to_haram(self):
        if self.lat is None or self.lng is None:
            return None
        R = 6_371_000
        ref_lat, ref_lng = self.ref_point
        lat1, lng1 = math.radians(self.lat), math.radians(self.lng)
        lat2, lng2 = math.radians(ref_lat), math.radians(ref_lng)
        dlat, dlng = lat2 - lat1, lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        return int(R * 2 * math.asin(math.sqrt(a)))

    @property
    def distance_label(self):
        d = self.distance_to_haram
        if d is None: return '—'
        return f'{d} m' if d < 1000 else f'{d/1000:.1f} km'

    @property
    def walk_label(self):
        d = self.distance_to_haram
        if d is None: return None
        # ~80 m/min walking pace, the metric Makkah/Madinah hotel directories
        # lead with ("2 min walk from Masjid al-Haram") because raw meters
        # mean little to pilgrims planning the Fajr walk.
        minutes = max(1, round(d / 80))
        return f'±{minutes} mnt jalan kaki'


class Occupancy(models.TextChoices):
    """Master Architecture v2.0 §8.2 — controlled vocabulary. Optional: rooms
    created before this field existed, or named freely, leave it blank."""
    DOUBLE = 'double', 'Double'
    TRIPLE = 'triple', 'Triple'
    QUAD   = 'quad',   'Quad'
    QUINT  = 'quint',  'Quint'


class RoomView(models.TextChoices):
    """v2.0 §8.3 — controlled vocabulary. Optional, same rationale as Occupancy."""
    NON_VIEW = 'non_view', 'Non View'
    CITY     = 'city',     'City View'
    KAABA    = 'kaaba',    'Kaaba View'
    HARAM    = 'haram',    'Haram View'
    OTHER    = 'other',    'Other'


# Occupancy is just the name for a guest count, so it is derived from
# `capacity` rather than entered separately — two inputs for one fact let
# "Quad, capacity 2" through. Counts outside this map have no word and stay blank.
OCCUPANCY_BY_CAPACITY = {
    2: Occupancy.DOUBLE,
    3: Occupancy.TRIPLE,
    4: Occupancy.QUAD,
    5: Occupancy.QUINT,
}


def occupancy_for_capacity(capacity):
    return OCCUPANCY_BY_CAPACITY.get(capacity, '')


def room_type_name(capacity, view=''):
    """The conventional catalog name for a guest count + view, e.g.
    "Quad Kaaba View". "Other" says nothing about the room, so it is left out.
    Mirrored by suggestRoomTypeName() in frontend/pages/Hotel/roomTypeName.js.
    """
    occupancy = occupancy_for_capacity(capacity)
    parts = [Occupancy(occupancy).label if occupancy else f'{capacity} Pax']
    if view and view != RoomView.OTHER:
        parts.append(RoomView(view).label)
    return ' '.join(parts)


class RoomType(models.Model):
    hotel      = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='room_types')
    name       = models.CharField(max_length=100)
    capacity   = models.PositiveSmallIntegerField(default=2, help_text='Guests per room')
    # Structured dimension (v2.0 §8.3) on top of the free-form `name`, for
    # filtering/reporting. Occupancy (Double/Triple/…) is only the name of a
    # guest count, so it is a property of `capacity`, not a stored column.
    view       = models.CharField(max_length=10, choices=RoomView.choices, blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Room Type'
        verbose_name_plural = 'Room Types'
        constraints = [
            models.UniqueConstraint(fields=['hotel', 'name'], name='uniq_room_type_per_hotel'),
            models.CheckConstraint(
                condition=models.Q(capacity__gte=1, capacity__lte=10), name='room_type_capacity_1_to_10',
            ),
            models.CheckConstraint(
                condition=models.Q(view__in=[''] + [c[0] for c in RoomView.choices]), name='room_type_view_valid',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.hotel.name})'

    @property
    def occupancy(self):
        return occupancy_for_capacity(self.capacity)
