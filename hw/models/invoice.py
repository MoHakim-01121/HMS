"""Invoice & Reservation models.

Convention: all monetary amounts (SAR, IDR) stored as IntegerField representing
minor units (fils for SAR, sen for IDR). Conversion via hw.utils.convert_to_sar().
"""
from django.db import models
from django.urls import reverse

from .choices import InvoiceType
from ..utils import convert_to_sar


# Cabang penerbit bila reservasi tidak menyebut owner_branch.
DEFAULT_INVOICE_BRANCH = 'sby'


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

    # v2.0 §15 — financial state, derived, NEVER persisted (unlike `status`
    # above, which mixes it with lifecycle and IS persisted by sync_status()).
    # Audit note (FASE G): STATUS_SENT/STATUS_VOID/STATUS_OVERDUE above are
    # never actually assigned anywhere in the codebase today — sync_status()
    # only ever produces draft/partial/paid, and there is no invoice-void
    # workflow. So `status`'s "lifecycle" half is currently vestigial, not a
    # real state machine to migrate off of. `financial_state` is additive:
    # it does not replace `status`, and nothing existing reads it yet.
    FINANCIAL_STATE_UNPAID   = 'unpaid'
    FINANCIAL_STATE_PARTIAL  = 'partial'
    FINANCIAL_STATE_PAID     = 'paid'
    FINANCIAL_STATE_OVERDUE  = 'overdue'
    FINANCIAL_STATE_CHOICES = [
        (FINANCIAL_STATE_UNPAID,  'Unpaid'),
        (FINANCIAL_STATE_PARTIAL, 'Partial'),
        (FINANCIAL_STATE_PAID,    'Paid'),
        (FINANCIAL_STATE_OVERDUE, 'Overdue'),
    ]

    # ── Core fields ───────────────────────────────────────────
    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.HOTEL, db_index=True)
    invoice_number = models.CharField(max_length=100, db_index=True)
    client         = models.ForeignKey('Client', null=True, blank=True, on_delete=models.PROTECT, related_name='invoices')
    customer_name  = models.CharField(max_length=200)
    # Cabang penerbit — menentukan rekening "Pay to" di detail invoice
    # (BankAccount.show_on_invoice milik cabang ini). Diisi dari form, atau
    # otomatis dari owner_branch reservasinya (fallback: DEFAULT_INVOICE_BRANCH).
    branch         = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.PROTECT, related_name='invoices')
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
                fields=['invoice_type', 'invoice_number'],
                name='uniq_invoice_number_per_type',
            ),
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

    def infer_branch_id(self):
        """Cabang yang wajar untuk invoice ini bila belum dipilih: owner_branch
        reservasi pertama yang punya, selain itu DEFAULT_INVOICE_BRANCH."""
        owner = (
            self.reservations.exclude(owner_branch__isnull=True)
            .order_by('pk').values_list('owner_branch_id', flat=True).first()
        ) if self.pk else None
        return owner or DEFAULT_INVOICE_BRANCH

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

    @property
    def financial_state(self):
        """Derived financial state (v2.0 §15) — computed fresh every read,
        never stored. Distinct vocabulary from `status`: 'unpaid' here maps
        to whatever `status` happens to hold when nothing has been paid
        (draft, sent, or an unpaid partial-lifecycle value alike)."""
        from datetime import date
        total, paid = self.total_sar, self.total_paid_sar
        if total > 0 and paid >= total:
            return self.FINANCIAL_STATE_PAID
        if self.due_date and self.due_date < date.today() and paid < total:
            return self.FINANCIAL_STATE_OVERDUE
        if paid > 0:
            return self.FINANCIAL_STATE_PARTIAL
        return self.FINANCIAL_STATE_UNPAID

    @property
    def financial_state_display(self):
        return dict(self.FINANCIAL_STATE_CHOICES)[self.financial_state]

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
    # v2.0 §12: Reservation harus tetap bisa ditelusuri ke Client dan CL.
    # Sebelumnya keduanya cuma bisa ditemukan via invoice.client / pencocokan
    # string reservation_number == cl.confirmation_number pada invoice yang
    # sama (aturan implisit yang sudah dipakai _sync_invoice_reservation_from_cl).
    # FK langsung ini menggantikan pencocokan string itu — data historis
    # di-backfill sekali pakai aturan yang persis sama (lihat migrasi).
    client              = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='reservations')
    confirmation_letter = models.ForeignKey('ConfirmationLetter', null=True, blank=True, on_delete=models.SET_NULL, related_name='reservations')
    reservation_number = models.CharField(max_length=100)
    hotel              = models.CharField(max_length=200, blank=True)
    check_in           = models.DateField(null=True, blank=True)
    check_out          = models.DateField(null=True, blank=True)
    total_sar          = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Reservation'
        verbose_name_plural = 'Reservations'
        constraints = [
            # v2.0 §12: check_out > check_in. Verified data-safe against
            # production before adding (2026-09-12): 0 of 84 existing
            # reservations violate this, including 0 same-day (check_out ==
            # check_in) rows -- so there is no known legitimate day-use
            # booking pattern this would break. Only ConfirmationLetter's
            # own dates were left unchecked (that query was blocked
            # mid-audit) -- this constraint is NOT mirrored there.
            models.CheckConstraint(
                condition=(
                    models.Q(check_in__isnull=True) | models.Q(check_out__isnull=True)
                    | models.Q(check_out__gt=models.F('check_in'))
                ),
                name='reservation_check_out_after_check_in',
            ),
        ]

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
