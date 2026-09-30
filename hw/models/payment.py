"""PaymentRecord — finance-redesign payment model.

Convention: amount/amount_sar are IntegerField (minor units). See invoice.py docstring.
"""
from django.db import models
from django.urls import reverse



class PaymentRecord(models.Model):
    """Satu-satunya sumber truth untuk pembayaran. Append-only.

    Tidak ada DELETE atau UPDATE pada baris ini. Koreksi dilakukan via
    PaymentLog + reversing entry di JournalEntry.
    """

    STATUS_PENDING          = 'pending'
    STATUS_RECEIVED         = 'received'
    STATUS_CONFIRMED        = 'confirmed'
    STATUS_ALLOCATED        = 'allocated'
    STATUS_PARTIALLY_APPLIED = 'partially_applied'
    STATUS_APPLIED          = 'applied'
    STATUS_REJECTED         = 'rejected'
    STATUS_REVERSED         = 'reversed'
    STATUS_VOIDED           = 'voided'
    STATUS_CHOICES = [
        (STATUS_PENDING,          'Pending'),
        (STATUS_RECEIVED,         'Received'),
        (STATUS_CONFIRMED,        'Confirmed'),
        (STATUS_ALLOCATED,        'Allocated'),
        (STATUS_PARTIALLY_APPLIED, 'Partially Applied'),
        (STATUS_APPLIED,          'Applied'),
        (STATUS_REJECTED,         'Rejected'),
        (STATUS_REVERSED,         'Reversed'),
        (STATUS_VOIDED,           'Voided'),
    ]

    # Status yang punya efek jurnal (uang benar-benar masuk). Semua derivasi
    # angka pembayaran — footer invoice, riwayat, avg-days-to-pay — menyaring
    # ke daftar ini. Satu definisi, dipakai queries + model property.
    EFFECTIVE_STATUSES = (
        STATUS_RECEIVED, STATUS_CONFIRMED, STATUS_ALLOCATED,
        STATUS_PARTIALLY_APPLIED, STATUS_APPLIED,
    )

    # Identitas
    payment_number = models.CharField(max_length=50, unique=True, db_index=True)
    invoice        = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='payment_records')
    client         = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='payment_records')

    # Data pembayaran
    payment_date   = models.DateField()
    amount         = models.PositiveIntegerField()
    currency       = models.CharField(max_length=10, default='SAR')
    exchange_rate  = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    amount_sar     = models.PositiveIntegerField()

    # Di kas mana uangnya diterima — menentukan wallet ledger & akun jurnal.
    # 'pusat' = client bayar langsung ke rekening pusat (tidak mengendap).
    RECEIVED_IN_CHOICES = [
        ('sby',   'Surabaya'),
        ('jkt',   'Jakarta'),
        ('pusat', 'Pusat (Direct)'),
    ]
    received_in    = models.CharField(max_length=10, choices=RECEIVED_IN_CHOICES, default='sby')

    # Akun uang penerima (rekening bank atau kas). Kosong hanya untuk baris
    # historis — `received_in` tetap jadi fallback routing. Cabang penerima
    # diturunkan dari sini (bisa berbeda dari cabang pemilik client).
    receiving_account = models.ForeignKey(
        'MoneyAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='payments_received',
    )

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
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Payment Record'
        verbose_name_plural = 'Payment Records'
        indexes = [
            models.Index(fields=['status'], name='payrec_status_idx'),
            models.Index(fields=['client', 'status'], name='payrec_client_status_idx'),
            models.Index(fields=['invoice', 'status'], name='payrec_invoice_status_idx'),
        ]

    def __str__(self):
        return f"{self.payment_number} | {self.amount} {self.currency} | {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse('payment_detail', args=[self.pk])

    @property
    def receiving_branch_code(self):
        """Kode cabang penerima uang — dari receiving_account, fallback received_in.
        v2.0 §4: bisa berbeda dari owner_branch reservasi."""
        acc = self.receiving_account
        return acc.branch_id if acc else self.received_in

    @property
    def is_confirmed(self):
        return self.status in self.EFFECTIVE_STATUSES

    @property
    def is_editable(self):
        return self.status == self.STATUS_PENDING

    def derive_status(self):
        """Compute derived status from allocation sum vs amount.

        Call after allocations are created/updated to set the correct
        status: applied (fully allocated), partially_applied, or received.
        """
        total_alloc = self.allocations.aggregate(
            total=models.Sum('amount_sar')
        )['total'] or 0
        if total_alloc >= self.amount_sar:
            return self.STATUS_APPLIED
        if total_alloc > 0:
            return self.STATUS_PARTIALLY_APPLIED
        return self.STATUS_RECEIVED

    @staticmethod
    def generate_number():
        from ..numbering import generate_sequential_number
        return generate_sequential_number(PaymentRecord, 'PAY', field='payment_number', padding=4)


class PaymentAllocation(models.Model):
    """Bagian dari satu pembayaran yang melunasi satu baris invoice.

    Tujuannya selalu satu baris invoice: baris hotel (reservasi) atau baris
    service. Denda tidak dialokasikan sendiri: ia dibayar lewat baris hotel
    reservasinya (lihat hw.finance.penalty_billing). Bagian pembayaran yang
    tidak punya alokasi adalah kelebihan bayar.
    """

    payment      = models.ForeignKey(PaymentRecord, on_delete=models.PROTECT, related_name='allocations')
    # PROTECT: baris invoice yang sudah menerima uang tidak boleh hilang.
    invoice_line = models.ForeignKey('InvoiceLine', on_delete=models.PROTECT, related_name='payment_allocations')
    amount_sar   = models.BigIntegerField()
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Payment Allocation'
        verbose_name_plural = 'Payment Allocations'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_sar__gt=0),
                name='paymentallocation_amount_positive',
            ),
        ]

    def __str__(self):
        return f"{self.payment.payment_number} → {self.amount_sar:,}"

    # Nama lama per jenis baris, untuk pembaca yang membedakan reservasi dari
    # service (tampilan alokasi, kwitansi, dimensi jurnal).
    @property
    def reservation(self):
        line = self.invoice_line
        return line if line.kind == line.KIND_HOTEL else None

    @property
    def reservation_id(self):
        line = self.reservation
        return line.pk if line else None

    @property
    def service_item(self):
        line = self.invoice_line
        return line if line.kind == line.KIND_SERVICE else None

    @property
    def service_item_id(self):
        line = self.service_item
        return line.pk if line else None


class PaymentLog(models.Model):
    """Immutable audit log untuk setiap perubahan status PaymentRecord.

    Tidak pernah di-UPDATE atau di-DELETE. Setiap perubahan mencatat
    before_state dan after_state sebagai JSON snapshot.
    """

    ACTION_CREATED   = 'created'
    ACTION_RECEIVED  = 'received'
    ACTION_CONFIRMED = 'confirmed'
    ACTION_ALLOCATED = 'allocated'
    ACTION_APPLIED   = 'applied'
    ACTION_REJECTED  = 'rejected'
    ACTION_UPDATED   = 'updated'
    ACTION_REVERSED  = 'reversed'
    ACTION_VOIDED    = 'voided'
    ACTION_CHOICES = [
        (ACTION_CREATED,   'Created'),
        (ACTION_RECEIVED,  'Received'),
        (ACTION_CONFIRMED, 'Confirmed'),
        (ACTION_ALLOCATED, 'Allocated'),
        (ACTION_APPLIED,   'Applied'),
        (ACTION_REJECTED,  'Rejected'),
        (ACTION_UPDATED,   'Updated'),
        (ACTION_REVERSED,  'Reversed'),
        (ACTION_VOIDED,    'Voided'),
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
