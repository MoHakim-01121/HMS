from django.db import models
from django.db.models import Q
from django.urls import reverse

from .choices import Company
from ..utils import convert_to_sar


class ConfirmationLetter(models.Model):
    company             = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ, db_index=True)
    client              = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='cls')
    hotel_name          = models.CharField(max_length=200)
    guest_name          = models.CharField(max_length=200)
    guest_phone         = models.CharField(max_length=50, blank=True)
    check_in            = models.DateField(null=True, blank=True, db_index=True)
    check_out           = models.DateField(null=True, blank=True, db_index=True)
    confirmation_number = models.CharField(max_length=100, db_index=True)
    reservation_status  = models.CharField(max_length=50, default='DEFINITE', db_index=True)
    invoice             = models.ForeignKey(
        'Invoice', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='confirmation_letters',
    )
    note       = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Confirmation Letter'
        verbose_name_plural = 'Confirmation Letters'

    def __str__(self):
        return f"CL-{self.confirmation_number} | {self.guest_name}"

    def get_absolute_url(self):
        return reverse('cl_detail', args=[self.pk])

    @property
    def num_nights(self):
        if self.check_in and self.check_out:
            return (self.check_out - self.check_in).days
        return 0

    @property
    def total_price(self):
        return sum(r.subtotal for r in self.rooms.all())

    @property
    def total_rooms(self):
        return sum(r.quantity for r in self.rooms.all())

    @property
    def num_guests(self):
        capacity = {'Double': 2, 'Triple': 3, 'Quad': 4, 'Quint': 5}
        return sum(capacity.get(r.room_type, 1) * r.quantity for r in self.rooms.all())

    @property
    def paid_sar(self):
        from .invoice import Payment
        payments = Payment.objects.filter(
            Q(cl=self) | Q(linked_number=self.confirmation_number, cl__isnull=True)
        )
        return sum(
            int(round(convert_to_sar(float(p.amount), p.currency, float(p.exchange_rate))))
            for p in payments
        )

    @property
    def remaining_sar(self):
        return int(self.total_price or 0) - self.paid_sar

    @classmethod
    def generate_number(cls):
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for num_str in cls.objects.select_for_update().filter(
                confirmation_number__startswith='CL-',
            ).values_list('confirmation_number', flat=True):
                parts = num_str.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"CL-{(max(nums) + 1 if nums else 1):03d}"


class Room(models.Model):
    cl        = models.ForeignKey(ConfirmationLetter, on_delete=models.CASCADE, related_name='rooms')
    room_type = models.CharField(max_length=50)
    meals     = models.CharField(max_length=100, blank=True)
    quantity  = models.PositiveIntegerField(default=1)
    price     = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name        = 'Room'
        verbose_name_plural = 'Rooms'

    def __str__(self):
        return f"{self.room_type} x{self.quantity} — {self.cl}"

    @property
    def subtotal(self):
        nights = self.cl.num_nights or 1
        return float(self.price) * self.quantity * nights
