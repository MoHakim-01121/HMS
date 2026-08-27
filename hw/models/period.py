from django.db import models
from django.utils import timezone


class FinancialPeriod(models.Model):
    """Lock per periode akuntansi.

    Status lifecycle: open → soft_close → closed → locked
    - open: semua transaksi boleh masuk
    - soft_close: auto-posting masih boleh, manual JE perlu approval
    - closed: tidak ada posting baru kecuali prior-period adjustment
    - locked: fiscal year closed, tidak ada perubahan sama sekali
    """

    STATUS_OPEN       = 'open'
    STATUS_SOFT_CLOSE = 'soft_close'
    STATUS_CLOSED     = 'closed'
    STATUS_LOCKED     = 'locked'
    STATUS_CHOICES = [
        (STATUS_OPEN,       'Open'),
        (STATUS_SOFT_CLOSE, 'Soft Close'),
        (STATUS_CLOSED,     'Closed'),
        (STATUS_LOCKED,     'Locked'),
    ]

    name       = models.CharField(max_length=50, unique=True)
    date_from  = models.DateField(unique=True)
    date_to    = models.DateField(unique=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    closed_by  = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    closed_at  = models.DateTimeField(null=True, blank=True)
    locked_by  = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    locked_at  = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-date_from']
        verbose_name        = 'Financial Period'
        verbose_name_plural = 'Financial Periods'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_from__lt=models.F('date_to')),
                name='period_from_before_to',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_editable(self):
        return self.status == self.STATUS_OPEN

    @property
    def is_postable(self):
        return self.status in (self.STATUS_OPEN, self.STATUS_SOFT_CLOSE)

    def close(self, user):
        """Tutup periode. Tidak bisa dibuka lagi."""
        if self.status not in (self.STATUS_OPEN, self.STATUS_SOFT_CLOSE):
            raise ValueError("Periode sudah ditutup/locked")

        # Validate all journal entries in this period are balanced.
        # JournalEntry has no stored status/total fields — every entry is
        # posted at creation (create_journal_entry() enforces balance
        # before and after save), so re-check via the line aggregate here.
        from .journal import JournalEntry
        unbalanced_ids = []
        for entry in JournalEntry.objects.filter(period=self).prefetch_related('lines'):
            if not entry.is_balanced:
                unbalanced_ids.append(entry.entry_number)
        if unbalanced_ids:
            raise ValueError(
                f"Ada {len(unbalanced_ids)} journal entry yang tidak seimbang: "
                f"{', '.join(unbalanced_ids)}. Harus diselesaikan dulu."
            )

        self.status = self.STATUS_CLOSED
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save(update_fields=['status', 'closed_by', 'closed_at'])

    def lock(self, user):
        """Lock periode. Irreversible."""
        if self.status != self.STATUS_CLOSED:
            raise ValueError("Periode harus closed dulu sebelum di-lock")
        
        # Validate no pending payments in this period
        from .payment import PaymentRecord
        pending = PaymentRecord.objects.filter(
            period=self,
            status=PaymentRecord.STATUS_PENDING,
        )
        if pending.exists():
            raise ValueError(f"Ada {pending.count()} pembayaran pending. Harus di-confirm/reject dulu.")
        
        self.status = self.STATUS_LOCKED
        self.locked_by = user
        self.locked_at = timezone.now()
        self.save(update_fields=['status', 'locked_by', 'locked_at'])
