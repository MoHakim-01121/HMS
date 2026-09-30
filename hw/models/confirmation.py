"""ConfirmationLetter = reservasi (skema target 3.2).

CL adalah reservasi itu sendiri: diterbitkan KONOZ Pusat untuk satu client di
satu hotel, dengan nomor internal KONOZ. Nama client dan nama hotel TIDAK
disimpan di sini: guest_name dan hotel_name adalah properti yang membaca
Client dan Hotel lewat foreign key, jadi tidak bisa berbeda dari master.
(Dulu keduanya kolom teks salinan; di produksi 3 nama hotel dan 1 tanggal di
baris tagihan sudah menyimpang dari CL-nya.)
"""
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce, NullIf
from django.urls import reverse

from ..utils import round_half_up


class ReservationStatus(models.TextChoices):
    TENTATIVE = 'TENTATIVE', 'Tentative'
    DEFINITE = 'DEFINITE', 'Definite'
    CANCELLED = 'CANCELLED', 'Cancelled'


def guest_name_expr(prefix=''):
    """Ekspresi ORM nama tampil client (brand, atau nama perusahaan) untuk
    order_by/annotate. `prefix` = jalur ke CL dari model lain (mis. 'cl__')."""
    return Coalesce(
        NullIf(models.F(f'{prefix}client__brand'), models.Value('')),
        models.F(f'{prefix}client__name'),
    )


def _live_hotel_lines(**extra):
    """Subquery: baris invoice hotel yang masih berlaku untuk CL di baris luar."""
    from .invoice import InvoiceLine
    return InvoiceLine.objects.filter(
        confirmation_letter=models.OuterRef('pk'), kind=InvoiceLine.KIND_HOTEL,
        voided_at__isnull=True, **extra,
    )


class ConfirmationLetterQuerySet(models.QuerySet):
    def with_invoice(self):
        """Ikut memuat invoice yang menagih tiap CL (dibaca `cl.invoice`)."""
        from .invoice import InvoiceLine
        return self.prefetch_related(models.Prefetch(
            'invoice_lines',
            queryset=InvoiceLine.objects.filter(
                kind=InvoiceLine.KIND_HOTEL, voided_at__isnull=True,
            ).select_related('invoice'),
            to_attr='_live_invoice_lines',
        ))

    def uninvoiced(self):
        return self.filter(~models.Exists(_live_hotel_lines()))

    def invoiced(self):
        return self.filter(models.Exists(_live_hotel_lines()))

    def on_invoice(self, invoice):
        return self.filter(models.Exists(_live_hotel_lines(invoice=invoice)))

    def with_parties(self):
        """Ikut memuat client dan hotel, yang dibaca guest_name/hotel_name."""
        return self.select_related('client', 'hotel')

    def name_matches(self, token):
        """Q: nomor CL, nama client/brand, atau nama hotel memuat `token`."""
        return (
            models.Q(confirmation_number__icontains=token)
            | models.Q(client__name__icontains=token)
            | models.Q(client__brand__icontains=token)
            | models.Q(hotel__name__icontains=token)
        )


class ConfirmationLetter(models.Model):
    client              = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='cls')
    hotel               = models.ForeignKey('Hotel', on_delete=models.PROTECT, related_name='confirmation_letters')
    guest_phone         = models.CharField(max_length=50, blank=True)
    check_in            = models.DateField(db_index=True)
    check_out           = models.DateField(db_index=True)
    confirmation_number = models.CharField(max_length=100, db_index=True)
    reservation_status  = models.CharField(
        max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.DEFINITE,
    )
    note          = models.TextField(blank=True)
    estimasi_tiba = models.TimeField(null=True, blank=True)
    pic_name      = models.CharField(max_length=200, blank=True)
    pic_phone     = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConfirmationLetterQuerySet.as_manager()

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Confirmation Letter'
        verbose_name_plural = 'Confirmation Letters'
        constraints = [
            models.UniqueConstraint(
                fields=['confirmation_number'],
                name='uniq_confirmation_number',
            ),
            models.CheckConstraint(
                condition=models.Q(check_out__gt=models.F('check_in')),
                name='cl_check_out_after_check_in',
            ),
            models.CheckConstraint(
                condition=models.Q(reservation_status__in=[c[0] for c in ReservationStatus.choices]),
                name='cl_status_valid',
            ),
        ]
        indexes = [
            models.Index(fields=['reservation_status'], name='hw_cl_status_idx'),
        ]

    def __str__(self):
        return f"CL-{self.confirmation_number} | {self.guest_name}"

    def get_absolute_url(self):
        return reverse('cl_detail', args=[self.pk])

    @property
    def guest_name(self):
        """Nama tampil client (brand, atau nama perusahaan)."""
        return self.client.display_name if self.client_id else ''

    @property
    def hotel_name(self):
        return self.hotel.name if self.hotel_id else ''

    @property
    def invoice_line(self):
        """Baris invoice yang sedang menagih reservasi ini (None bila belum
        ditagih). Reservasi tidak menyimpan invoice-nya: tautannya adalah
        baris invoice, dan paling banyak satu yang berlaku (unique constraint)."""
        # Dibaca segar kecuali sudah dimuat with_invoice(): tautan ini berubah
        # saat invoice dibuat, diedit, atau di-void.
        lines = getattr(self, '_live_invoice_lines', None)
        if lines is None:
            from .invoice import InvoiceLine
            lines = list(InvoiceLine.objects.filter(
                confirmation_letter_id=self.pk, kind=InvoiceLine.KIND_HOTEL, voided_at__isnull=True,
            ).select_related('invoice')[:1]) if self.pk else []
        return lines[0] if lines else None

    @property
    def invoice(self):
        line = self.invoice_line
        return line.invoice if line else None

    @property
    def invoice_id(self):
        line = self.invoice_line
        return line.invoice_id if line else None

    @property
    def is_cancelled(self):
        return self.reservation_status == ReservationStatus.CANCELLED

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
        return sum(r.room_type_ref.capacity * r.quantity for r in self.rooms.all())

    @property
    def paid_sar(self):
        # Derivasi dari jurnal (system of record). Bulk-nya: queries.cl_paid_sar_map.
        from ..finance import queries as fq
        return fq.cl_paid_sar_map([self]).get(self.pk, 0)

    @property
    def remaining_sar(self):
        return round_half_up(self.total_price or 0) - self.paid_sar

    @classmethod
    def generate_number(cls):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, 'CL', field='confirmation_number', padding=3)

    @classmethod
    def suggest_number(cls):
        from ..numbering import peek_number
        return peek_number(cls, 'CL', field='confirmation_number', padding=3)

    @classmethod
    def claim_number(cls, number):
        """Counter mengikuti nomor yang diketik user."""
        from ..numbering import advance_number
        advance_number(cls, 'CL', number, field='confirmation_number')


class Room(models.Model):
    """Kamar dalam sebuah reservasi: komponen CL (terhapus bersama CL-nya).

    Tipe kamar dan meal plan menunjuk master lewat foreign key. room_type dan
    meals (dulu kolom teks salinan) sekarang properti yang membaca master itu.
    """
    cl        = models.ForeignKey(ConfirmationLetter, on_delete=models.CASCADE, related_name='rooms')
    room_type_ref = models.ForeignKey('RoomType', on_delete=models.PROTECT, related_name='bookings')
    meal_plan = models.ForeignKey('MealPlan', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    # Catatan bebas tentang makan/kamar (mis. "BB + late checkout"), bukan data.
    note      = models.CharField(max_length=100, blank=True)
    quantity  = models.PositiveIntegerField(default=1)
    price     = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name        = 'Room'
        verbose_name_plural = 'Rooms'
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='room_quantity_positive'),
            models.CheckConstraint(condition=models.Q(price__gte=0), name='room_price_non_negative'),
        ]

    def __str__(self):
        return f"{self.room_type} x{self.quantity} — {self.cl}"

    @property
    def room_type(self):
        """Nama tipe kamar dari master (mis. "Quad Kaaba View")."""
        return self.room_type_ref.name

    @property
    def meals(self):
        """Kode meal plan (FB/RO/BB), atau catatan bebas bila tidak memakai master."""
        return self.meal_plan_id or self.note

    @property
    def subtotal(self):
        nights = self.cl.num_nights or 1
        return self.price * self.quantity * nights
