from django.db import models
from django.urls import reverse

from .choices import Company
from ..utils import convert_to_sar


class PaymentRecord(models.Model):
    """Satu-satunya sumber truth untuk pembayaran. Append-only.

    Tidak ada DELETE atau UPDATE pada baris ini. Koreksi dilakukan via
    PaymentLog + reversing entry di JournalEntry.
    """

    STATUS_PENDING   = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_ALLOCATED = 'allocated'
    STATUS_REJECTED  = 'rejected'
    STATUS_REVERSED  = 'reversed'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_ALLOCATED, 'Allocated'),
        (STATUS_REJECTED,  'Rejected'),
        (STATUS_REVERSED,  'Reversed'),
    ]

    # Identitas
    payment_number = models.CharField(max_length=50, unique=True, db_index=True)
    invoice        = models.ForeignKey('Invoice', on_delete=models.PROTECT, related_name='payment_records')
    client         = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='payment_records')

    # Target alokasi (opsional: salah satu atau none)
    reservation    = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    service_item   = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    # Data pembayaran
    payment_date   = models.DateField()
    amount         = models.PositiveIntegerField()
    currency       = models.CharField(max_length=10, default='SAR')
    exchange_rate  = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    amount_sar     = models.PositiveIntegerField()

    # Metadata
    method         = models.CharField(max_length=50)
    bank_name      = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    reference      = models.CharField(max_length=200, blank=True, db_index=True)
    note           = models.TextField(blank=True)
    proof          = models.FileField(upload_to='payments/proof/', null=True, blank=True)

    # Lifecycle
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    confirmed_by    = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    confirmed_at    = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    # Period & Audit
    period     = models.ForeignKey('FinancialPeriod', on_delete=models.PROTECT, related_name='payments')
    company    = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Payment Record'
        verbose_name_plural = 'Payment Records'
        indexes = [
            models.Index(fields=['company', 'status'], name='payrec_company_status_idx'),
            models.Index(fields=['client', 'status'], name='payrec_client_status_idx'),
            models.Index(fields=['invoice', 'status'], name='payrec_invoice_status_idx'),
        ]

    def __str__(self):
        return f"{self.payment_number} | {self.amount} {self.currency} | {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse('payment_detail', args=[self.pk])

    @property
    def is_confirmed(self):
        return self.status in (self.STATUS_CONFIRMED, self.STATUS_ALLOCATED)

    @property
    def is_editable(self):
        return self.status == self.STATUS_PENDING

    @staticmethod
    def generate_number():
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for num_str in PaymentRecord.objects.select_for_update().filter(
                payment_number__startswith='PAY-',
            ).values_list('payment_number', flat=True):
                parts = num_str.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"PAY-{(max(nums) + 1 if nums else 1):04d}"


class PaymentLog(models.Model):
    """Immutable audit log untuk setiap perubahan status PaymentRecord.

    Tidak pernah di-UPDATE atau di-DELETE. Setiap perubahan mencatat
    before_state dan after_state sebagai JSON snapshot.
    """

    ACTION_CREATED   = 'created'
    ACTION_CONFIRMED = 'confirmed'
    ACTION_ALLOCATED = 'allocated'
    ACTION_REJECTED  = 'rejected'
    ACTION_UPDATED   = 'updated'
    ACTION_REVERSED  = 'reversed'
    ACTION_CHOICES = [
        (ACTION_CREATED,   'Created'),
        (ACTION_CONFIRMED, 'Confirmed'),
        (ACTION_ALLOCATED, 'Allocated'),
        (ACTION_REJECTED,  'Rejected'),
        (ACTION_UPDATED,   'Updated'),
        (ACTION_REVERSED,  'Reversed'),
    ]

    payment        = models.ForeignKey(PaymentRecord, on_delete=models.CASCADE, related_name='logs')
    action         = models.CharField(max_length=20, choices=ACTION_CHOICES)
    before_state   = models.JSONField(default=dict)
    after_state    = models.JSONField(default=dict)
    performed_by   = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    performed_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    note           = models.TextField(blank=True)

    class Meta:
        ordering            = ['-performed_at']
        verbose_name        = 'Payment Log'
        verbose_name_plural = 'Payment Logs'

    def __str__(self):
        return f"{self.payment.payment_number} | {self.get_action_display()} by {self.performed_by}"
