import math
from datetime import date

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .utils import convert_to_sar, next_sequence_number


# ── Choices ──────────────────────────────────────────────────────────────────

class Company(models.TextChoices):
    KONOZ  = 'konoz',  'Konoz United'
    IJABAH = 'ijabah', 'Ijabah'


class InvoiceType(models.TextChoices):
    HOTEL = 'hotel', 'Hotel'
    VISA  = 'visa',  'Visa/Services'


class HotelCity(models.TextChoices):
    MAKKAH  = 'makkah',  'Makkah'
    MADINAH = 'madinah', 'Madinah'


# ── Models ────────────────────────────────────────────────────────────────────

class UserProfile(models.Model):
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    class Meta:
        verbose_name        = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return self.user.username


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN  = 'login',  'Login'
        CREATE = 'create', 'Dibuat'
        EDIT   = 'edit',   'Diedit'
        DELETE = 'delete', 'Dihapus'
        PDF    = 'pdf',    'Export PDF'

    # Keep flat constants for backward-compat call sites
    ACTION_LOGIN  = Action.LOGIN
    ACTION_CREATE = Action.CREATE
    ACTION_EDIT   = Action.EDIT
    ACTION_DELETE = Action.DELETE
    ACTION_PDF    = Action.PDF

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action     = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=50, blank=True)
    object_ref = models.CharField(max_length=200, blank=True)
    company    = models.CharField(max_length=20, blank=True)
    changes    = models.JSONField(default=list, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-timestamp']
        verbose_name        = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"{self.user.username} {self.action} {self.object_ref}"


def log_activity(user, action, model_name='', object_ref='', company='', changes=None):
    ActivityLog.objects.create(
        user=user, action=action, model_name=model_name,
        object_ref=object_ref, company=company, changes=changes or [],
    )


class Client(models.Model):
    company    = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    name       = models.CharField(max_length=200)
    city       = models.CharField(max_length=100, blank=True)
    province   = models.CharField(max_length=100, blank=True)
    lat        = models.FloatField(null=True, blank=True)
    lng        = models.FloatField(null=True, blank=True)
    pic        = models.CharField(max_length=200, blank=True, verbose_name='PIC')
    wa         = models.CharField(max_length=30, blank=True, verbose_name='WhatsApp')
    email      = models.EmailField(blank=True)
    note       = models.TextField(blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('client_detail', args=[self.pk])

    @property
    def total_invoices(self):
        return len(self.invoices.all()) + len(self.cls.all())

    @property
    def total_billed(self):
        return sum(inv.total_sar for inv in self.invoices.all())

    @property
    def total_paid(self):
        return sum(inv.total_paid_sar for inv in self.invoices.all())

    @property
    def outstanding(self):
        return sum(inv.remaining_sar for inv in self.invoices.all() if inv.remaining_sar > 0)

    @property
    def avg_days_to_pay(self):
        days_list = []
        for inv in self.invoices.all():
            if inv.remaining_sar <= 0 and inv.issued_date:
                payments = sorted(
                    inv.payments.all(),
                    key=lambda p: p.payment_date or date.min,
                    reverse=True,
                )
                if payments and payments[0].payment_date:
                    days_list.append((payments[0].payment_date - inv.issued_date).days)
        return round(sum(days_list) / len(days_list)) if days_list else None

    @property
    def last_transaction_date(self):
        invs = list(self.invoices.all())
        if not invs:
            return None
        return max(inv.created_at for inv in invs)

    @property
    def days_since_last_order(self):
        lt = self.last_transaction_date
        if not lt:
            return None
        now = timezone.now()
        if lt.tzinfo is None:
            lt = timezone.make_aware(lt)
        return (now - lt).days

    @property
    def score(self):
        s = 0
        total = self.total_billed
        if total >= 100000: s += 40
        elif total >= 50000: s += 30
        elif total >= 10000: s += 20
        elif total > 0: s += 10
        avg = self.avg_days_to_pay
        if avg is not None:
            if avg <= 7: s += 40
            elif avg <= 14: s += 30
            elif avg <= 30: s += 20
            elif avg <= 60: s += 10
        days = self.days_since_last_order
        if days is not None:
            if days <= 30: s += 20
            elif days <= 60: s += 15
            elif days <= 90: s += 5
        return s

    @property
    def risk_label(self):
        if self.outstanding > 0:
            due_invs = sorted(
                [i for i in self.invoices.all() if i.due_date is not None],
                key=lambda i: i.due_date,
            )
            if due_invs:
                overdue = (date.today() - due_invs[0].due_date).days
                if overdue > 60: return 'high'
                if overdue > 0:  return 'medium'
        days = self.days_since_last_order
        if days and days > 45 and self.total_invoices > 0:
            return 'dormant'
        return 'ok'


class ConfirmationLetter(models.Model):
    company = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    client  = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='cls')
    hotel_name = models.CharField(max_length=200)
    guest_name = models.CharField(max_length=200)
    guest_phone = models.CharField(max_length=50, blank=True)
    check_in = models.DateField(null=True, blank=True)
    check_out = models.DateField(null=True, blank=True)
    confirmation_number = models.CharField(max_length=100, db_index=True)
    reservation_status = models.CharField(max_length=50, default='DEFINITE')
    invoice = models.ForeignKey(
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
        return next_sequence_number(cls.objects, 'confirmation_number', 'CL')


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


class Invoice(models.Model):
    company        = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    client         = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices')
    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.HOTEL)
    invoice_number = models.CharField(max_length=100, db_index=True)
    customer_name  = models.CharField(max_length=200)
    issued_date    = models.DateField(null=True, blank=True)
    due_date       = models.DateField(null=True, blank=True)
    currency       = models.CharField(max_length=10, default='SAR')
    ai_summary     = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Invoice'
        verbose_name_plural = 'Invoices'

    def __str__(self):
        return f"{self.invoice_number} | {self.customer_name}"

    def get_absolute_url(self):
        return reverse('invoice_detail', args=[self.pk])

    @property
    def total_sar(self):
        return sum(r.total_sar for r in self.reservations.all())

    @property
    def total_paid_sar(self):
        return sum(
            int(round(convert_to_sar(float(p.amount), p.currency, float(p.exchange_rate))))
            for p in self.payments.all()
        )

    @property
    def remaining_sar(self):
        return self.total_sar - self.total_paid_sar

    @classmethod
    def generate_number(cls, invoice_type):
        prefix = 'INV' if invoice_type == InvoiceType.HOTEL else 'SVC'
        return next_sequence_number(
            cls.objects.filter(invoice_type=invoice_type),
            'invoice_number',
            prefix,
        )


class Reservation(models.Model):
    invoice            = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reservations')
    reservation_number = models.CharField(max_length=100)
    hotel              = models.CharField(max_length=200, blank=True)
    check_in           = models.DateField(null=True, blank=True)
    check_out          = models.DateField(null=True, blank=True)
    total_sar          = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Reservation'
        verbose_name_plural = 'Reservations'

    def __str__(self):
        return f"{self.reservation_number} | {self.hotel}"


class ServiceItem(models.Model):
    invoice        = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='service_items')
    service_number = models.PositiveIntegerField(default=1)
    name           = models.CharField(max_length=200)
    qty            = models.PositiveIntegerField(default=1)
    price          = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering            = ['service_number']
        verbose_name        = 'Service Item'
        verbose_name_plural = 'Service Items'

    def __str__(self):
        return f"{self.name} (x{self.qty})"

    @property
    def total(self):
        return int(self.qty * float(self.price))


class Payment(models.Model):
    invoice       = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    cl            = models.ForeignKey(
        ConfirmationLetter, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cl_payments',
    )
    linked_number = models.CharField(max_length=100, blank=True, db_index=True)
    payment_date  = models.DateField(null=True, blank=True)
    method        = models.CharField(max_length=100, blank=True)
    amount        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency      = models.CharField(max_length=10, default='SAR')
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    note          = models.TextField(blank=True)
    proof         = models.FileField(upload_to='payments/proof/', null=True, blank=True)

    class Meta:
        verbose_name        = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"{self.payment_date} | {self.amount} {self.currency}"

    @property
    def amount_sar(self):
        return int(round(convert_to_sar(float(self.amount), self.currency, float(self.exchange_rate))))


def _attachment_path(instance, filename):
    if instance.invoice_id:
        return f"attachments/invoice/{instance.invoice_id}/{filename}"
    return f"attachments/cl/{instance.cl_id}/{filename}"


class Attachment(models.Model):
    invoice     = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    cl          = models.ForeignKey(ConfirmationLetter, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    file        = models.FileField(upload_to=_attachment_path)
    name        = models.CharField(max_length=255)
    size        = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Attachment'
        verbose_name_plural = 'Attachments'

    def __str__(self):
        return self.name

    @property
    def ext(self):
        return self.name.lower().rsplit('.', 1)[-1] if '.' in self.name else ''

    @property
    def is_image(self):
        return self.ext in ('jpg', 'jpeg', 'png', 'gif', 'webp')

    @property
    def icon(self):
        if self.is_image:
            return 'image'
        if self.ext == 'pdf':
            return 'pdf'
        return 'file'


# ── Reference coordinates ────────────────────────────────────────────────────
HARAM_LAT  = 21.420324; HARAM_LNG  = 39.826485  # Masjid Al-Haram (Makkah)
NABAWI_LAT = 24.4672;   NABAWI_LNG = 39.6112    # Masjid Nabawi (Madinah)


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
        """Haversine distance in meters from hotel to reference mosque."""
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
