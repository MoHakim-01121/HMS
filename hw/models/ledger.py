from django.db import models

from .choices import Company


class Account(models.TextChoices):
    CLIENT = 'client', 'Client'
    SBY    = 'sby',    'Surabaya'
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
    company           = models.CharField(max_length=20, choices=Company.choices, db_index=True)
    client            = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='cash_movements')
    date              = models.DateField(db_index=True)
    from_account      = models.CharField(max_length=20, choices=Account.choices)
    to_account        = models.CharField(max_length=20, choices=Account.choices)
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
