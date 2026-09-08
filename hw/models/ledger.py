"""[LEGACY / DEPRECATED] Ledger models: Charge, Allocation, CashMovement.

Pernah menjadi sumber utama untuk wallet/piutang klien, namun kini DIGANTIKAN
oleh general ledger baru (hw/models/journal.py + hw/finance/). Model di file ini
SENGAJA dipertahankan untuk kompatibilitas dengan seeder/backfill dan data
historis -- JANGAN menulis data baru melalui model ini pada fitur yang sudah
ada padanannya di jurnal (lihat finance/posting.py & finance/queries.py).

Contoh penggunaan aktif residual:
- ``CashAccount`` dipakai oleh ``hw/views/client_views.py`` (REFUND_ACCOUNTS /
  from_account pada refund) -- sedang ditransisikan ke chart of accounts.
- ``Charge``/``Allocation``/``CashMovement`` hanya dibaca oleh backfill/check.

Convention: all amount_sar fields are IntegerField (minor units, e.g. fils).
"""
from django.db import models

from .choices import Company


class CashAccount(models.TextChoices):
    """[LEGACY / DEPRECATED] Cash-routing destinations.

    Masih dipakai oleh ``REFUND_ACCOUNTS`` di client_views.py untuk memilih
    asal dana refund; sedang ditransisikan ke chart of accounts
    (hw/finance/accounts.py). Lihat journal.py:Account untuk Chart of Accounts.
    """
    CLIENT = 'client', 'Client'
    SBY    = 'sby',    'Surabaya'
    JKT    = 'jkt',    'Jakarta'
    PUSAT  = 'pusat',  'Pusat'
    FX     = 'fx',     'FX'


class ChargeReason(models.TextChoices):
    INITIAL      = 'initial',      'Initial'
    REVISION     = 'revision',     'Revision'
    CANCELLATION = 'cancellation', 'Cancellation'
    CORRECTION   = 'correction',   'Correction'


class AllocationReason(models.TextChoices):
    INITIAL      = 'initial',      'Initial'
    REVISION     = 'revision',     'Revision'
    TRANSFER     = 'transfer',     'Transfer'
    CANCELLATION = 'cancellation', 'Cancellation'
    CORRECTION   = 'correction',   'Correction'


def _exactly_one_target_condition():
    """Q expression: exactly one of reservation/service_item/penalty is set.

    Shared by Charge and Allocation's CheckConstraint (see their Meta) so the
    DB — not just the dead ``clean()`` below — rejects a row with zero or
    multiple targets.
    """
    return (
        models.Q(reservation__isnull=False, service_item__isnull=True, penalty__isnull=True) |
        models.Q(reservation__isnull=True, service_item__isnull=False, penalty__isnull=True) |
        models.Q(reservation__isnull=True, service_item__isnull=True, penalty__isnull=False)
    )


class LedgerEntryTarget(models.Model):
    """Abstract base: exactly one of reservation/service_item/penalty must be set."""

    reservation  = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.CASCADE, related_name='+')
    service_item = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.CASCADE, related_name='+')
    penalty      = models.ForeignKey('CancellationPenalty', null=True, blank=True, on_delete=models.CASCADE, related_name='+')

    class Meta:
        abstract = True

    def clean(self):
        from django.core.exceptions import ValidationError
        targets = [self.reservation_id, self.service_item_id, self.penalty_id]
        if sum(1 for t in targets if t) != 1:
            raise ValidationError('Tepat satu dari reservation/service_item/penalty harus terisi.')


class Charge(LedgerEntryTarget):
    """[LEGACY / DEPRECATED] Ditulis ke general ledger via
    finance/posting.post_invoice_charge/penalty_charge. READ-ONLY sia-sianya
    (backfill/seed). Jangan menulis baru."""
    company    = models.CharField(max_length=20, choices=Company.choices, db_index=True)
    # Nullable: historical invoices frequently have no resolvable client (Invoice.client
    # FK was never populated by the form, and the linked ConfirmationLetter may also
    # lack one). Rows with client=None still count in company-wide wallet totals, they
    # just don't appear in per-client views (saldo_dana, piutang_klien, statement).
    client     = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='charges')
    date       = models.DateField(db_index=True)
    amount_sar = models.IntegerField()
    invoice    = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='charges')
    reason     = models.CharField(max_length=20, choices=ChargeReason.choices)
    description = models.CharField(max_length=255, blank=True)
    note       = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['date', 'created_at', 'id']
        verbose_name        = 'Charge'
        verbose_name_plural = 'Charges'
        constraints = [
            models.CheckConstraint(
                condition=_exactly_one_target_condition(),
                name='ledger_charge_exactly_one_target',
            ),
        ]

    def __str__(self):
        return f"Charge {self.amount_sar} SAR ({self.reason}) — {self.client}"


class Allocation(LedgerEntryTarget):
    """[LEGACY / DEPRECATED] Alokasi kas masuk/gabung. Dilihat/reversed via
    jurnal (posting.allocate_payment / queries). READ-ONLY sia-sianya."""
    company        = models.CharField(max_length=20, choices=Company.choices, db_index=True)
    client         = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='allocations')
    date           = models.DateField(db_index=True)
    amount_sar     = models.IntegerField()
    invoice        = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='allocations')
    reason         = models.CharField(max_length=20, choices=AllocationReason.choices)
    transfer_group = models.UUIDField(null=True, blank=True, db_index=True)
    note           = models.TextField(blank=True)
    created_by     = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['date', 'created_at', 'id']
        verbose_name        = 'Allocation'
        verbose_name_plural = 'Allocations'
        constraints = [
            models.CheckConstraint(
                condition=_exactly_one_target_condition(),
                name='ledger_allocation_exactly_one_target',
            ),
        ]

    def __str__(self):
        return f"Allocation {self.amount_sar} SAR ({self.reason}) — {self.client}"


class CashMovement(models.Model):
    """[LEGACY / DEPRECATED] Transfer kas. Pindah ke jurnal via
    posting.post_fund_transfer / post_remittance_send. READ-ONLY sia-sianya."""
    company           = models.CharField(max_length=20, choices=Company.choices, db_index=True)
    client            = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='cash_movements')
    date              = models.DateField(db_index=True)
    from_account      = models.CharField(max_length=20, choices=CashAccount.choices)
    to_account        = models.CharField(max_length=20, choices=CashAccount.choices)
    amount            = models.PositiveIntegerField()
    currency          = models.CharField(max_length=10, default='SAR')
    exchange_rate     = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    method            = models.CharField(max_length=100, blank=True)
    invoice           = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='cash_movements')
    remittance        = models.ForeignKey('Remittance', null=True, blank=True, on_delete=models.CASCADE, related_name='movements')
    # Keterangan saja, tidak mengikat (lihat Allocation utk yang mengikat). Paling
    # banyak satu dari keduanya terisi -- reservasi hotel vs booking visa/servis.
    reservation_label  = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    service_item_label = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    penalty_label      = models.ForeignKey('CancellationPenalty', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reverses          = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='reversed_by')
    note              = models.TextField(blank=True)
    proof             = models.FileField(upload_to='ledger/proof/', null=True, blank=True)
    created_by        = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at        = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['date', 'created_at', 'id']
        verbose_name        = 'Cash Movement'
        verbose_name_plural = 'Cash Movements'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_account=models.F('to_account')),
                name='ledger_cashmovement_from_ne_to',
            ),
            models.CheckConstraint(
                condition=~(
                    models.Q(reservation_label__isnull=False, service_item_label__isnull=False)
                    | models.Q(reservation_label__isnull=False, penalty_label__isnull=False)
                    | models.Q(service_item_label__isnull=False, penalty_label__isnull=False)
                ),
                name='ledger_cashmovement_at_most_one_label',
            ),
        ]

    def __str__(self):
        return f"{self.from_account} -> {self.to_account}: {self.amount} {self.currency}"

    @property
    def amount_sar(self):
        from ..utils import convert_to_sar
        return int(round(convert_to_sar(self.amount, self.currency, float(self.exchange_rate))))
