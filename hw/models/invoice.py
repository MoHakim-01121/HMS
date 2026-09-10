"""Invoice & Reservation models.

Convention: all monetary amounts (SAR, IDR) stored as IntegerField representing
minor units (fils for SAR, sen for IDR). Conversion via hw.utils.convert_to_sar().
"""
from django.db import models
from django.urls import reverse

from .choices import Company, InvoiceType
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
        from ..finance import queries
        return queries.invoice_paid_sar(self.id)

    @property
    def remaining_sar(self):
        return self.total_sar - self.total_paid_sar

    @property
    def is_fully_paid(self):
        return self.total_paid_sar >= self.total_sar and self.total_sar > 0

    def sync_status(self):
        """Recompute & persist `status` from total_paid_sar/total_sar,
        keduanya diturunkan dari JournalLine (hw.finance.queries). Panggil
        setelah setiap posting payment/charge untuk invoice ini."""
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
        from ..numbering import generate_sequential_number
        prefix = 'INV' if invoice_type == InvoiceType.HOTEL else 'SVC'
        return generate_sequential_number(
            cls, prefix, field='invoice_number', padding=3,
            extra_filter={'invoice_type': invoice_type},
        )


class Reservation(models.Model):
    invoice            = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reservations')
    # Cabang pemilik order. Nullable selama FASE A (di-backfill ke SBY); v2.0 §4
    # membedakan owner branch dari cabang penerima uang (nanti dari BankAccount).
    owner_branch       = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.PROTECT, related_name='reservations')
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
    """[LEGACY / DEPRECATED] Pembayaran lama, digantikan oleh PaymentRecord
    (hw/models/payment.py + finance/posting.py).

    Tabel (`hw_payment`) & model ini SENG AJA dipertahankan untuk kompatibilitas
    dengan seeder/backfill dan data historis. JANGAN menulis pembayaran baru
    melalui model ini -- gunakan PaymentRecord + create_payment_record().
    """
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
