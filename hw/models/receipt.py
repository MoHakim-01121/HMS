"""Receipt (Kwitansi) — bukti pembayaran untuk reservasi.

Receipt di-generate dari PaymentRecord sebagai dokumen terpisah.
Convention: all monetary amounts stored as IntegerField (minor units).
"""
from django.db import models
from django.urls import reverse


class Receipt(models.Model):
    """Kwitansi pembayaran — dokumen bukti bahwa klien telah membayar."""

    STATUS_ACTIVE  = 'active'
    STATUS_VOIDED  = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]

    # Identitas
    receipt_number = models.CharField(max_length=50, db_index=True)
    receipt_date   = models.DateField()
    season         = models.ForeignKey(
        'Season', null=True, blank=True, on_delete=models.PROTECT, related_name='receipts',
    )

    # Relasi ke data existing
    payment        = models.ForeignKey(
        'PaymentRecord', on_delete=models.PROTECT, related_name='receipts',
    )
    # Nullable: pembayaran tanpa invoice (deposit) tetap dapat kwitansi —
    # PDF menampilkan tanpa blok invoice ("Paid for") dan tanpa rincian alokasi.
    invoice        = models.ForeignKey(
        'Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='receipts',
    )
    client         = models.ForeignKey(
        'Client', on_delete=models.PROTECT, related_name='receipts',
    )
    confirmation_letter = models.ForeignKey(
        'ConfirmationLetter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='receipts',
    )

    # Data pembayaran
    amount_sar     = models.PositiveIntegerField()
    payment_method = models.CharField(max_length=50)
    payment_note   = models.TextField(blank=True)

    # Status
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    voided_reason  = models.TextField(blank=True)

    # Audit
    created_by     = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Receipt'
        verbose_name_plural = 'Receipts'
        indexes = [
            models.Index(fields=['status'], name='receipt_status_idx'),
            models.Index(fields=['client', 'status'], name='receipt_client_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['season', 'receipt_number'], condition=models.Q(season__isnull=False),
                name='receipt_number_season_uniq',
            ),
            models.UniqueConstraint(
                fields=['receipt_number'], condition=models.Q(season__isnull=True),
                name='receipt_number_no_season_uniq',
            ),
        ]

    def __str__(self):
        return f"{self.receipt_number} | {self.amount_sar:,} SAR"

    def save(self, *args, **kwargs):
        from .period import Season

        season = Season.objects.filter(
            date_from__lte=self.receipt_date, date_to__gte=self.receipt_date,
        ).first()
        if self.season_id != (season.pk if season else None):
            self.season = season
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'season'}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        if self.payment_id:
            return reverse('payment_detail', args=[self.payment_id])
        return reverse('receipt_pdf', args=[self.pk])

    @staticmethod
    def _sequence_context(receipt_date=None):
        from .period import Season

        season = Season.objects.filter(
            date_from__lte=receipt_date, date_to__gte=receipt_date,
        ).first() if receipt_date else None
        if season:
            return f'RCP-SEASON-{season.pk}', {'season_id': season.pk}
        return 'RCP-NO-SEASON', {'season__isnull': True}

    @classmethod
    def generate_number(cls, receipt_date=None):
        from ..numbering import generate_sequential_number

        key, season_scope = cls._sequence_context(receipt_date)
        return generate_sequential_number(
            cls, 'RCP', field='receipt_number', padding=4, key=key,
            extra_filter=season_scope,
        )
