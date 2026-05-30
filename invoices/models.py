from datetime import date

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


COMPANY_CHOICES = [('konoz', 'Konoz United'), ('ijabah', 'Ijabah')]


class UserProfile(models.Model):
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    def __str__(self):
        return self.user.username


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


class ActivityLog(models.Model):
    ACTION_LOGIN  = 'login'
    ACTION_CREATE = 'create'
    ACTION_EDIT   = 'edit'
    ACTION_DELETE = 'delete'
    ACTION_PDF    = 'pdf'

    ACTION_CHOICES = [
        (ACTION_LOGIN,  'Login'),
        (ACTION_CREATE, 'Dibuat'),
        (ACTION_EDIT,   'Diedit'),
        (ACTION_DELETE, 'Dihapus'),
        (ACTION_PDF,    'Export PDF'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50, blank=True)
    object_ref = models.CharField(max_length=200, blank=True)
    company    = models.CharField(max_length=20, blank=True)
    changes    = models.JSONField(default=list, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} {self.action} {self.object_ref}"


def diff_fields(old, new, fields):
    """Compare old/new dict values, return list of {label, before, after}."""
    result = []
    for key, label in fields.items():
        b, a = str(old.get(key, '') or ''), str(new.get(key, '') or '')
        if b != a:
            result.append({'label': label, 'before': b, 'after': a})
    return result


def log_activity(user, action, model_name='', object_ref='', company='', changes=None):
    ActivityLog.objects.create(
        user=user, action=action, model_name=model_name,
        object_ref=object_ref, company=company, changes=changes or [],
    )
    old_ids = list(ActivityLog.objects.filter(user=user).order_by('-timestamp').values_list('id', flat=True)[50:])
    if old_ids:
        ActivityLog.objects.filter(id__in=old_ids).delete()


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    log_activity(user, ActivityLog.ACTION_LOGIN)


class Client(models.Model):
    company    = models.CharField(max_length=20, choices=COMPANY_CHOICES, default='konoz')
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
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_invoices(self):
        return self.invoices.count() + self.cls.count()

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
                last_payment = inv.payments.order_by('-payment_date').first()
                if last_payment and last_payment.payment_date:
                    days_list.append((last_payment.payment_date - inv.issued_date).days)
        return round(sum(days_list) / len(days_list)) if days_list else None

    @property
    def last_transaction_date(self):
        inv = self.invoices.order_by('-created_at').first()
        return inv.created_at if inv else None

    @property
    def days_since_last_order(self):
        lt = self.last_transaction_date
        if not lt:
            return None
        from django.utils import timezone
        now = timezone.now()
        if lt.tzinfo is None:
            from django.utils.timezone import make_aware
            lt = make_aware(lt)
        return (now - lt).days

    @property
    def score(self):
        # Simple score 0–100: volume (40) + payment speed (40) + recency (20)
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
            inv = self.invoices.filter(due_date__isnull=False).order_by('due_date').first()
            if inv and inv.due_date:
                overdue = (date.today() - inv.due_date).days
                if overdue > 60: return 'high'
                if overdue > 0:  return 'medium'
        days = self.days_since_last_order
        if days and days > 45 and self.total_invoices > 0:
            return 'dormant'
        return 'ok'


class ConfirmationLetter(models.Model):
    company = models.CharField(max_length=20, choices=COMPANY_CHOICES, default='konoz')
    client  = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='cls')
    hotel_name = models.CharField(max_length=200)
    guest_name = models.CharField(max_length=200)
    guest_phone = models.CharField(max_length=50, blank=True)
    check_in = models.DateField(null=True, blank=True)
    check_out = models.DateField(null=True, blank=True)
    confirmation_number = models.CharField(max_length=100)
    reservation_status = models.CharField(max_length=50, default='DEFINITE')
    invoice = models.ForeignKey(
        'Invoice',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='confirmation_letters',
    )
    note = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CL-{self.confirmation_number} | {self.guest_name}"

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
        from .utils import convert_to_sar
        payments = Payment.objects.filter(linked_number=self.confirmation_number)
        return sum(
            int(round(convert_to_sar(float(p.amount), p.currency, float(p.exchange_rate))))
            for p in payments
        )

    @property
    def remaining_sar(self):
        return int(self.total_price or 0) - self.paid_sar

    @classmethod
    def generate_number(cls):
        ym = date.today().strftime('%Y%m')
        pattern = f"CL-{ym}-"
        nums = []
        for obj in cls.objects.filter(confirmation_number__startswith=pattern):
            try:
                nums.append(int(obj.confirmation_number.split('-')[-1]))
            except (ValueError, IndexError):
                pass
        return f"CL-{ym}-{(max(nums) + 1 if nums else 1):03d}"


class Room(models.Model):
    cl = models.ForeignKey(ConfirmationLetter, on_delete=models.CASCADE, related_name='rooms')
    room_type = models.CharField(max_length=50)
    meals = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def subtotal(self):
        nights = self.cl.num_nights or 1
        return float(self.price) * self.quantity * nights


INVOICE_TYPE_CHOICES = [('hotel', 'Hotel'), ('visa', 'Visa/Services')]


class Invoice(models.Model):
    company = models.CharField(max_length=20, choices=COMPANY_CHOICES, default='konoz')
    client  = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices')
    invoice_type = models.CharField(max_length=20, choices=INVOICE_TYPE_CHOICES, default='hotel')
    invoice_number = models.CharField(max_length=100)
    customer_name = models.CharField(max_length=200)
    issued_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default='SAR')
    ai_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} | {self.customer_name}"

    @property
    def total_sar(self):
        return sum(r.total_sar for r in self.reservations.all())

    @property
    def total_paid_sar(self):
        from .utils import convert_to_sar
        return sum(
            int(round(convert_to_sar(float(p.amount), p.currency, float(p.exchange_rate))))
            for p in self.payments.all()
        )

    @property
    def remaining_sar(self):
        return self.total_sar - self.total_paid_sar

    @classmethod
    def generate_number(cls, invoice_type):
        prefix = "INV" if invoice_type == "hotel" else "SVC"
        ym = date.today().strftime('%Y%m')
        pattern = f"{prefix}-{ym}-"
        nums = []
        for obj in cls.objects.filter(invoice_type=invoice_type, invoice_number__startswith=pattern):
            try:
                nums.append(int(obj.invoice_number.split('-')[-1]))
            except (ValueError, IndexError):
                pass
        return f"{prefix}-{ym}-{(max(nums) + 1 if nums else 1):03d}"


class Reservation(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reservations')
    reservation_number = models.CharField(max_length=100)
    hotel = models.CharField(max_length=200, blank=True)
    check_in = models.DateField(null=True, blank=True)
    check_out = models.DateField(null=True, blank=True)
    total_sar = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.reservation_number} | {self.hotel}"


class ServiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='service_items')
    service_number = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=200)
    qty = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['service_number']

    @property
    def total(self):
        return int(self.qty * float(self.price))


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    linked_number = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    method = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='SAR')
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    note = models.TextField(blank=True)
    proof = models.FileField(upload_to='payments/proof/', null=True, blank=True)

    def __str__(self):
        return f"{self.payment_date} | {self.amount} {self.currency}"

    @property
    def amount_sar(self):
        from .utils import convert_to_sar
        return int(round(convert_to_sar(float(self.amount), self.currency, float(self.exchange_rate))))


def _attachment_path(instance, filename):
    if instance.invoice_id:
        return f"attachments/invoice/{instance.invoice_id}/{filename}"
    return f"attachments/cl/{instance.cl_id}/{filename}"


class Attachment(models.Model):
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    cl = models.ForeignKey(ConfirmationLetter, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=_attachment_path)
    name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def is_image(self):
        return self.name.lower().rsplit('.', 1)[-1] in ('jpg', 'jpeg', 'png', 'gif', 'webp')

    @property
    def icon(self):
        ext = self.name.lower().rsplit('.', 1)[-1] if '.' in self.name else ''
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            return 'image'
        if ext == 'pdf':
            return 'pdf'
        return 'file'


# ── Reference coordinates ────────────────────────────────────────────────────
HARAM_LAT    = 21.420324; HARAM_LNG    = 39.826485  # Pelataran Masjid Al-Haram (Makkah)
NABAWI_LAT   = 24.4672;  NABAWI_LNG   = 39.6112   # Masjid Nabawi (Madinah)

HOTEL_CITY_CHOICES = [('makkah', 'Makkah'), ('madinah', 'Madinah')]


class Hotel(models.Model):
    company      = models.CharField(max_length=20, choices=COMPANY_CHOICES, default='konoz')
    name         = models.CharField(max_length=200)
    city         = models.CharField(max_length=20, choices=HOTEL_CITY_CHOICES, default='makkah')
    stars        = models.PositiveSmallIntegerField(default=3)
    area         = models.CharField(max_length=100, blank=True)
    lat          = models.FloatField(null=True, blank=True)
    lng          = models.FloatField(null=True, blank=True)
    avg_occupancy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Rata-rata orang per kamar, mis. 3.4'
    )
    note         = models.TextField(blank=True)
    route        = models.JSONField(null=True, blank=True,
                                    help_text='Intermediate waypoints [[lat,lng],...] between mosque and hotel')
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def ref_point(self):
        """Reference mosque coordinates based on city."""
        if self.city == 'madinah':
            return NABAWI_LAT, NABAWI_LNG
        return HARAM_LAT, HARAM_LNG

    @property
    def ref_label(self):
        return 'Masjid Nabawi' if self.city == 'madinah' else 'Masjid Al-Haram'

    @property
    def distance_to_haram(self):
        """Haversine distance in meters from hotel to reference mosque."""
        if self.lat is None or self.lng is None:
            return None
        import math
        R = 6_371_000
        ref_lat, ref_lng = self.ref_point
        lat1, lng1 = math.radians(self.lat), math.radians(self.lng)
        lat2, lng2 = math.radians(ref_lat), math.radians(ref_lng)
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        return int(R * 2 * math.asin(math.sqrt(a)))

    @property
    def distance_label(self):
        d = self.distance_to_haram
        if d is None:
            return '—'
        if d < 1000:
            return f'{d} m'
        return f'{d/1000:.1f} km'

    @property
    def stars_display(self):
        return '★' * self.stars + '☆' * (5 - self.stars)

    def rooms_needed(self, jamaah_count):
        """Calculate rooms needed for a given jamaah count."""
        if not self.avg_occupancy or self.avg_occupancy <= 0:
            return None
        import math
        return math.ceil(jamaah_count / float(self.avg_occupancy))
