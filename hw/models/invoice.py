"""Invoice & Reservation models.

Convention: all monetary amounts (SAR, IDR) stored as IntegerField representing
minor units (fils for SAR, sen for IDR). Conversion via hw.utils.convert_to_sar().
"""
from django.db import models
from django.urls import reverse

from .choices import Company, InvoiceType  # noqa: F401 — Company used in Remittance
from ..utils import convert_to_sar


class Invoice(models.Model):
    # ── Status lifecycle ──────────────────────────────────────
    STATUS_DRAFT    = 'draft'
    STATUS_SENT     = 'sent'
    STATUS_PARTIAL  = 'partial'
    STATUS_PAID     = 'paid'
    STATUS_OVERDUE  = 'overdue'
    STATUS_VOID     = 'void'
    STATUS_CHOICES  = [
        (STATUS_DRAFT,   'Draft'),
        (STATUS_SENT,    'Sent'),
        (STATUS_PARTIAL, 'Partial Payment'),
        (STATUS_PAID,    'Paid'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_VOID,    'Void'),
    ]

    # ── Core fields ───────────────────────────────────────────
    company        = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ, db_index=True)
    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.HOTEL, db_index=True)
    invoice_number = models.CharField(max_length=100, db_index=True)
    client         = models.ForeignKey('Client', null=True, blank=True, on_delete=models.PROTECT, related_name='invoices')
    customer_name  = models.CharField(max_length=200)
    issued_date    = models.DateField(null=True, blank=True)
    due_date       = models.DateField(null=True, blank=True, db_index=True)
    currency       = models.CharField(max_length=10, default='SAR')

    # ── Status ─────────────────────────────────────────────────
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    # ── Audit ─────────────────────────────────────────────────
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Invoice'
        verbose_name_plural = 'Invoices'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'invoice_type', 'invoice_number'],
                name='uniq_invoice_number_per_company_type',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'invoice_type'], name='hw_invoice_company_type_idx'),
            models.Index(fields=['company', 'due_date'], name='hw_invoice_company_due_idx'),
        ]

    def __str__(self):
        return f"{self.invoice_number} | {self.customer_name}"

    def get_absolute_url(self):
        return reverse('invoice_detail', args=[self.pk])

    def save(self, *args, **kwargs):
        # Auto-sync customer_name from client — single source of truth
        if self.client_id:
            self.customer_name = self.client.name
        super().save(*args, **kwargs)

    @property
    def total_sar(self):
        return sum(r.total_sar for r in self.reservations.all()) + sum(s.total for s in self.service_items.all())

    @property
    def total_paid_sar(self):
        from .. import ledger
        return ledger.invoice_paid_sar(self.id)

    @property
    def remaining_sar(self):
        return self.total_sar - self.total_paid_sar

    @property
    def is_fully_paid(self):
        return self.total_paid_sar >= self.total_sar and self.total_sar > 0

    def sync_status(self):
        """Recompute & persist `status` from total_paid_sar/total_sar --
        the same ledger reads remaining_sar/is_fully_paid use. Call after
        any write to the CashMovement/Allocation ledger for this invoice so
        status never diverges from what those properties report."""
        paid = self.total_paid_sar
        if paid >= self.total_sar and self.total_sar > 0:
            self.status = self.STATUS_PAID
        elif paid > 0:
            self.status = self.STATUS_PARTIAL
        else:
            self.status = self.STATUS_DRAFT
        self.save(update_fields=['status'])

    @classmethod
    def generate_number(cls, invoice_type):
        from django.db import transaction
        prefix = 'INV' if invoice_type == InvoiceType.HOTEL else 'SVC'
        with transaction.atomic():
            nums = []
            for num_str in cls.objects.select_for_update().filter(
                invoice_type=invoice_type,
                invoice_number__startswith=f'{prefix}-',
            ).values_list('invoice_number', flat=True):
                parts = num_str.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


class Reservation(models.Model):
    invoice            = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reservations')
    client             = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='reservations')
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
    price          = models.PositiveIntegerField(default=0)

    class Meta:
        ordering            = ['service_number']
        verbose_name        = 'Service Item'
        verbose_name_plural = 'Service Items'

    def __str__(self):
        return f"{self.name} (x{self.qty})"

    @property
    def total(self):
        return self.qty * self.price


class Payment(models.Model):
    invoice       = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    cl            = models.ForeignKey(
        'ConfirmationLetter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cl_payments',
    )
    linked_number = models.CharField(max_length=100, blank=True, db_index=True)
    payment_date  = models.DateField(null=True, blank=True)
    method        = models.CharField(max_length=100, blank=True)
    amount        = models.PositiveIntegerField(default=0)
    currency      = models.CharField(max_length=10, default='SAR')
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    note          = models.TextField(blank=True)
    proof         = models.FileField(upload_to='payments/proof/', null=True, blank=True)

    class Meta:
        ordering            = ['id']
        verbose_name        = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"{self.payment_date} | {self.amount} {self.currency}"

    @property
    def amount_sar(self):
        return int(round(convert_to_sar(self.amount, self.currency, float(self.exchange_rate))))


class Remittance(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_RECEIVED = 'received'
    STATUS_CHOICES  = [(STATUS_PENDING, 'Pending'), (STATUS_RECEIVED, 'Received')]

    remittance_number = models.CharField(max_length=20, unique=True, blank=True)
    company           = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    date              = models.DateField()
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    receipt_reference = models.CharField(max_length=100, blank=True)

    # Transfer bank fisik: uang IDR keluar dari Surabaya, kurs yang dipakai,
    # dan nominal SAR yang benar-benar diterima pusat (bisa beda karena biaya
    # transfer/pembulatan). Semuanya opsional -- RMT lama hanya punya baris.
    amount_idr         = models.BigIntegerField(null=True, blank=True)
    exchange_rate      = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    received_amount_sar = models.IntegerField(null=True, blank=True)

    note              = models.TextField(blank=True)
    proof             = models.FileField(upload_to='remittance/proof/', null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-date', '-created_at']
        verbose_name        = 'Remittance'
        verbose_name_plural = 'Remittances'

    def __str__(self):
        return f"{self.remittance_number} | {self.date} | {self.total_sar} SAR"

    @classmethod
    def generate_number(cls):
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for obj in cls.objects.select_for_update().filter(remittance_number__startswith='RMT-'):
                try:
                    nums.append(int(obj.remittance_number.split('-')[-1]))
                except (ValueError, IndexError):
                    pass
            return f"RMT-{(max(nums) + 1 if nums else 1):03d}"

    @property
    def total_sar(self):
        from .. import ledger
        return int(ledger.remittance_total_sar(self.id))

    @property
    def expected_sar(self):
        """SAR teoretis dari amount_idr / kurs (sebelum biaya transfer)."""
        if self.amount_idr is None or not self.exchange_rate:
            return None
        from decimal import Decimal, ROUND_HALF_UP
        return int((Decimal(self.amount_idr) / self.exchange_rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @property
    def allocated_sar(self):
        """Total SAR yang sudah dibagikan ke reservasi (Σ baris)."""
        return sum(int(l.amount_sar or 0) for l in self.lines.all())

    @property
    def unallocated_sar(self):
        """Sisa transfer yang belum dialokasikan ke reservasi mana pun."""
        if self.received_amount_sar is None:
            return 0
        return int(self.received_amount_sar) - self.allocated_sar


class RemittanceLine(models.Model):
    remittance    = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='lines')
    invoice       = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='remittance_lines')
    linked_number = models.CharField(max_length=100)
    amount_sar    = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Remittance Line'
        verbose_name_plural = 'Remittance Lines'

    def __str__(self):
        return f"Res {self.linked_number} → {self.amount_sar} SAR"


def _attachment_path(instance, filename):
    if instance.invoice_id:
        return f"attachments/invoice/{instance.invoice_id}/{filename}"
    return f"attachments/cl/{instance.cl_id}/{filename}"


class Attachment(models.Model):
    invoice     = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    cl          = models.ForeignKey('ConfirmationLetter', null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
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
