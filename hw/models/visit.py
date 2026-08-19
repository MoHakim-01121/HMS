from django.conf import settings
from django.db import models

from .choices import Company


class Visit(models.Model):
    PLANNED = 'PLANNED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (PLANNED, 'Planned'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    ]

    # Sales-force-style structured outcome, filled in when the visit is
    # realized. `estimated_value` is the expected order value in SAR when the
    # visit produced business (or a live prospect), so the recap can roll it up.
    OUTCOME_ORDER = 'ORDER'
    OUTCOME_PROSPECT = 'PROSPECT'
    OUTCOME_NO_INTEREST = 'NO_INTEREST'
    OUTCOME_NOT_MET = 'NOT_MET'
    OUTCOME_CHOICES = [
        (OUTCOME_ORDER, 'Order received'),
        (OUTCOME_PROSPECT, 'Prospect / follow-up needed'),
        (OUTCOME_NO_INTEREST, 'No interest'),
        (OUTCOME_NOT_MET, 'Client not met'),
    ]

    company = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ, db_index=True)
    client  = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    staff   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')

    scheduled_date = models.DateField(db_index=True)
    start_time     = models.TimeField(null=True, blank=True)
    end_time       = models.TimeField(null=True, blank=True)
    purpose        = models.TextField()
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PLANNED, db_index=True)

    # Populated only when the visit is realized (status -> COMPLETED).
    visited_at           = models.DateTimeField(null=True, blank=True)
    checkin_lat          = models.FloatField(null=True, blank=True)
    checkin_lng          = models.FloatField(null=True, blank=True)
    distance_meters      = models.PositiveIntegerField(null=True, blank=True)
    outcome              = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True, default='')
    estimated_value      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pic_name             = models.CharField(max_length=120, blank=True, default='')
    pic_phone            = models.CharField(max_length=40, blank=True, default='')
    result_notes         = models.TextField(blank=True)
    next_follow_up_date  = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-scheduled_date', '-created_at']
        verbose_name        = 'Visit'
        verbose_name_plural = 'Visits'
        indexes = [
            models.Index(fields=['company', 'status'], name='hw_visit_company_status_idx'),
            models.Index(fields=['company', 'scheduled_date'], name='hw_visit_company_date_idx'),
        ]

    def __str__(self):
        return f"Visit to {self.client.name if self.client_id else '—'} on {self.scheduled_date}"


def _visit_photo_path(instance, filename):
    return f"visits/photos/{instance.visit_id}/{filename}"


class VisitPhoto(models.Model):
    visit       = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='photos')
    file        = models.FileField(upload_to=_visit_photo_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Visit Photo'
        verbose_name_plural = 'Visit Photos'

    def __str__(self):
        return f"Photo for visit #{self.visit_id}"
