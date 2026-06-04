import math

from django.db import models
from django.urls import reverse

from .choices import Company, HotelCity


HARAM_LAT  = 21.420324; HARAM_LNG  = 39.826485
NABAWI_LAT = 24.4672;   NABAWI_LNG = 39.6112


class Hotel(models.Model):
    company       = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    name          = models.CharField(max_length=200)
    city          = models.CharField(max_length=20, choices=HotelCity.choices, default=HotelCity.MAKKAH)
    stars         = models.PositiveSmallIntegerField(default=3)
    area          = models.CharField(max_length=100, blank=True)
    lat           = models.FloatField(null=True, blank=True)
    lng           = models.FloatField(null=True, blank=True)
    avg_occupancy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Rata-rata orang per kamar, mis. 3.4',
    )
    note          = models.TextField(blank=True)
    route         = models.JSONField(null=True, blank=True,
                                     help_text='Intermediate waypoints [[lat,lng],...] between mosque and hotel')
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Hotel'
        verbose_name_plural = 'Hotels'

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
    def stars_display(self):
        return '★' * self.stars + '☆' * (5 - self.stars)

    def rooms_needed(self, jamaah_count):
        if not self.avg_occupancy or self.avg_occupancy <= 0:
            return None
        return math.ceil(jamaah_count / float(self.avg_occupancy))
