"""HQ settlement domain (Master Architecture v2.0 §33–39, §80).

Tiga entity baru, DITAMBAHKAN di atas `Remittance`/`RemittanceLine` yang sudah
ada (hw/models/remittance.py) — tidak menggantikannya. `Remittance` tetap
mewakili transfer fisik (kirim); jalur lama `Remittance.received_amount_sar`
+ `post_remittance_receive()` (satu tanda terima lump-sum) tetap berjalan
untuk remittance yang sudah dikelola begitu. `RemittanceSettlement` adalah
jalur BARU (dipakai lewat `hw.finance.settlement_service`) untuk remittance
yang diterima BERTAHAP — satu transfer bisa punya banyak settlement, dan
satu settlement bisa menutup banyak `HQObligation`.

HQObligation != Expense. Ini kewajiban cabang→pusat, bukan beban.
"""
from django.db import models


class HQObligation(models.Model):
    """Kewajiban satu cabang untuk menyetor uang yang sudah dikumpulkan ke pusat."""

    STATUS_OPEN              = 'open'
    STATUS_PARTIALLY_SETTLED = 'partially_settled'
    STATUS_SETTLED           = 'settled'
    STATUS_CANCELLED         = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN,              'Open'),
        (STATUS_PARTIALLY_SETTLED, 'Partially Settled'),
        (STATUS_SETTLED,           'Settled'),
        (STATUS_CANCELLED,         'Cancelled'),
    ]

    branch       = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='hq_obligations')
    reservation  = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    amount_sar   = models.PositiveIntegerField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    due_date     = models.DateField(null=True, blank=True)
    note         = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'created_at']
        verbose_name = 'HQ Obligation'
        verbose_name_plural = 'HQ Obligations'
        indexes = [
            models.Index(fields=['branch', 'status'], name='hqobligation_branch_status_idx'),
        ]

    def __str__(self):
        return f"HQObligation {self.branch_id} {self.amount_sar:,} ({self.status})"

    @property
    def settled_sar(self):
        return self.allocations.aggregate(t=models.Sum('amount_sar'))['t'] or 0

    @property
    def outstanding_sar(self):
        return max(0, self.amount_sar - self.settled_sar)

    def derive_status(self):
        if self.status == self.STATUS_CANCELLED:
            return self.status
        settled = self.settled_sar
        if settled >= self.amount_sar and self.amount_sar > 0:
            return self.STATUS_SETTLED
        if settled > 0:
            return self.STATUS_PARTIALLY_SETTLED
        return self.STATUS_OPEN


class RemittanceSettlement(models.Model):
    """Satu tanda terima aktual di pusat untuk sebagian/seluruh sebuah Remittance.

    Nominal DITERIMA (bukan yang diharapkan) adalah source of truth — lihat
    v2.0 §36. Satu Remittance boleh punya banyak baris ini (kirim bertahap
    diterima, atau satu kiriman dipecah beberapa tanda terima)."""

    remittance         = models.ForeignKey('Remittance', on_delete=models.PROTECT, related_name='settlements')
    received_amount_sar = models.PositiveIntegerField()
    received_date       = models.DateField()
    reference            = models.CharField(max_length=200, blank=True)
    note                 = models.TextField(blank=True)
    created_by           = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at            = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['received_date', 'id']
        verbose_name = 'Remittance Settlement'
        verbose_name_plural = 'Remittance Settlements'

    def __str__(self):
        return f"Settlement {self.remittance.remittance_number} {self.received_amount_sar:,} SAR"

    @property
    def allocated_sar(self):
        return self.allocations.aggregate(t=models.Sum('amount_sar'))['t'] or 0

    @property
    def unallocated_sar(self):
        return max(0, self.received_amount_sar - self.allocated_sar)


class RemittanceAllocation(models.Model):
    """Bagian dari satu RemittanceSettlement yang menutup satu HQObligation.

    Invariant (service-enforced, lihat settlement_service.allocate_settlement):
    Σ allocation per settlement <= settlement.received_amount_sar."""

    settlement     = models.ForeignKey(RemittanceSettlement, on_delete=models.PROTECT, related_name='allocations')
    hq_obligation  = models.ForeignKey(HQObligation, on_delete=models.PROTECT, related_name='allocations')
    amount_sar     = models.PositiveIntegerField()
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Remittance Allocation'
        verbose_name_plural = 'Remittance Allocations'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='remitalloc_amount_positive'),
        ]

    def __str__(self):
        return f"{self.settlement_id} → {self.hq_obligation_id}: {self.amount_sar:,}"
