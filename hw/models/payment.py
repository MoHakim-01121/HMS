"""Pembayaran client: PaymentRecord, alokasinya, dan log perubahannya (skema target 3.5)."""
from django.db import models
from django.urls import reverse

from .uploads import RandomFileName


class PaymentQuerySet(models.QuerySet):
    def with_allocated(self):
        """Annotate `allocated` = Σ allocation rows + the part moved to client deposit."""
        from django.db.models.functions import Coalesce
        return self.annotate(
            allocated=Coalesce(models.Sum('allocations__amount_sar'), models.Value(0)) + models.F('deposited_sar'),
        )


class PaymentRecord(models.Model):
    """Satu penerimaan uang dari client: X di rekening penerima, kurs Y, nilai Z.

    `amount` adalah X dalam mata uang rekening penerima, `exchange_rate` Y,
    dan `amount_sar` Z: nilai yang mengurangi utang client. Satu pembayaran
    satu kurs. Bagian Z yang belum punya alokasi adalah kelebihan bayar.

    Append-only: tidak ada DELETE, dan koreksi dilakukan lewat PaymentLog +
    jurnal pembalik.
    """

    # ── Siklus hidup (disimpan) ───────────────────────────────
    STATUS_PENDING   = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_REJECTED  = 'rejected'
    STATUS_REVERSED  = 'reversed'
    STATUS_VOIDED    = 'voided'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_REJECTED,  'Rejected'),
        (STATUS_REVERSED,  'Reversed'),
        (STATUS_VOIDED,    'Voided'),
    ]

    # Status yang punya efek jurnal (uang benar-benar masuk). Semua derivasi
    # angka pembayaran menyaring ke daftar ini.
    EFFECTIVE_STATUSES = (STATUS_CONFIRMED,)

    # ── Keadaan alokasi (diturunkan dari baris alokasi, tidak disimpan) ──
    ALLOCATION_NONE    = 'unallocated'
    ALLOCATION_PARTIAL = 'partial'
    ALLOCATION_FULL    = 'allocated'
    # Nama yang dipakai layar untuk pembayaran efektif, per keadaan alokasi.
    _DISPLAY = {
        ALLOCATION_NONE:    ('received', 'Received'),
        ALLOCATION_PARTIAL: ('partially_applied', 'Partially Applied'),
        ALLOCATION_FULL:    ('applied', 'Applied'),
    }

    # Identitas
    payment_number = models.CharField(max_length=50, unique=True, db_index=True)
    invoice        = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='payment_records')
    client         = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='payment_records')

    # Data pembayaran
    payment_date   = models.DateField()
    amount         = models.PositiveIntegerField()                                       # X
    exchange_rate  = models.DecimalField(max_digits=14, decimal_places=4, default=1)     # Y
    amount_sar     = models.PositiveIntegerField()                                       # Z
    # Bagian Z yang sudah dipindahkan ke deposit client (tindakan eksplisit).
    # Z − Σ alokasi − deposited_sar = kelebihan bayar yang masih menempel di sini.
    deposited_sar  = models.PositiveIntegerField(default=0)

    # Rekening (bank atau kas) yang menerima uangnya. Menentukan mata uang X,
    # cabang penerima, dan akun kas di jurnal; ketiganya tidak disimpan lagi
    # di pembayaran.
    receiving_account = models.ForeignKey(
        'MoneyAccount', on_delete=models.PROTECT, related_name='payments_received',
    )

    # Metadata
    method         = models.CharField(max_length=50)
    reference      = models.CharField(max_length=200, blank=True, db_index=True)
    note           = models.TextField(blank=True)
    proof          = models.FileField(upload_to=RandomFileName('payments/proof/'), null=True, blank=True)

    # Lifecycle
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    confirmed_by    = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    confirmed_at    = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    # Audit
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Payment Record'
        verbose_name_plural = 'Payment Records'
        indexes = [
            models.Index(fields=['status'], name='payrec_status_idx'),
            models.Index(fields=['client', 'status'], name='payrec_client_status_idx'),
            models.Index(fields=['invoice', 'status'], name='payrec_invoice_status_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'confirmed', 'rejected', 'reversed', 'voided']),
                name='payment_status_valid',
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_amount_positive'),
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='payment_amount_sar_positive'),
            models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name='payment_rate_positive'),
            models.CheckConstraint(
                condition=models.Q(deposited_sar__lte=models.F('amount_sar')), name='payment_deposited_within_amount',
            ),
        ]

    def __str__(self):
        return f"{self.payment_number} | {self.amount} {self.currency} | {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse('payment_detail', args=[self.pk])

    # ── Dibaca dari rekening penerima ─────────────────────────

    @property
    def currency(self):
        """Mata uang X = mata uang rekening penerima."""
        return self.receiving_account.currency

    @property
    def receiving_branch_code(self):
        """Cabang penerima uang (bisa berbeda dari cabang pemilik client)."""
        return self.receiving_account.branch_id

    # Nama lama kolom yang dulu disimpan terpisah dari rekeningnya.
    received_in = receiving_branch_code

    def get_received_in_display(self):
        return self.receiving_account.branch.name

    @property
    def period(self):
        """Periode keuangan tempat tanggal pembayaran ini jatuh."""
        from .period import FinancialPeriod
        return FinancialPeriod.objects.filter(
            date_from__lte=self.payment_date, date_to__gte=self.payment_date,
        ).first()

    # ── Keadaan ───────────────────────────────────────────────

    @property
    def is_editable(self):
        return self.status == self.STATUS_PENDING

    @property
    def allocated_sar(self):
        """Bagian Z yang sudah punya tempat: alokasi ke baris invoice + yang
        dipindah ke deposit."""
        annotated = getattr(self, 'allocated', None)
        if annotated is not None:
            return int(annotated)
        if not self.pk:
            return int(self.deposited_sar or 0)
        return int(self.allocations.aggregate(t=models.Sum('amount_sar'))['t'] or 0) + int(self.deposited_sar or 0)

    @property
    def unallocated_sar(self):
        """Kelebihan bayar yang masih menempel di pembayaran ini."""
        return max(0, int(self.amount_sar) - self.allocated_sar)

    @property
    def allocation_state(self):
        """unallocated / partial / allocated — None bila pembayaran tidak efektif."""
        if self.status not in self.EFFECTIVE_STATUSES:
            return None
        allocated = self.allocated_sar
        if allocated >= self.amount_sar:
            return self.ALLOCATION_FULL
        return self.ALLOCATION_PARTIAL if allocated > 0 else self.ALLOCATION_NONE

    @property
    def display_status(self):
        """Status yang dibaca layar: siklus hidup, dan untuk pembayaran efektif
        keadaan alokasinya (received / partially_applied / applied)."""
        state = self.allocation_state
        return self._DISPLAY[state][0] if state else self.status

    @property
    def display_status_label(self):
        state = self.allocation_state
        return self._DISPLAY[state][1] if state else self.get_status_display()

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
    ACTION_DEPOSITED = 'deposited'
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
        (ACTION_DEPOSITED, 'Moved to deposit'),
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
