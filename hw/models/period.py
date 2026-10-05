from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class FinancialPeriod(models.Model):
    """Lock per periode akuntansi.

    Status lifecycle: open → soft_close → closed → locked
    - open: semua transaksi boleh masuk
    - soft_close: posting masih boleh (sama seperti open; belum ada alur
      approval jurnal manual — aplikasi tidak punya jurnal manual)
    - closed: tidak ada posting baru
    - locked: closed + final, tidak bisa diubah lagi
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
    # date_from/date_to: rentang inklusif [date_from, date_to]. Tidak boleh
    # tumpang tindih dengan periode lain — ditegakkan di save().
    date_from  = models.DateField()
    date_to    = models.DateField()
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

    def _assert_no_overlap(self):
        if self.date_from is None or self.date_to is None:
            return
        clash = FinancialPeriod.objects.filter(
            date_from__lte=self.date_to,
            date_to__gte=self.date_from,
        ).exclude(pk=self.pk)
        if clash.exists():
            other = clash.first()
            raise ValidationError(
                f"Periode {self.date_from}–{self.date_to} tumpang tindih dengan "
                f"{other.name} ({other.date_from}–{other.date_to})."
            )

    def save(self, *args, **kwargs):
        self._assert_no_overlap()
        super().save(*args, **kwargs)

    @property
    def is_editable(self):
        return self.status == self.STATUS_OPEN

    @property
    def is_postable(self):
        return self.status in (self.STATUS_OPEN, self.STATUS_SOFT_CLOSE)

    def close(self, user):
        """Tutup periode. Tidak bisa dibuka lagi."""
        from django.db import transaction

        with transaction.atomic():
            # Lock this period row so a concurrent post_entry (which also locks
            # the period via get_period_for_date) cannot slip an entry into the
            # period between our balance sweep and the status flip.
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status not in (self.STATUS_OPEN, self.STATUS_SOFT_CLOSE):
                raise ValueError("Periode sudah ditutup/locked")

            # Validate all journal entries in this period are balanced.
            # JournalEntry has no stored status/total fields — every entry is
            # posted at creation (create_journal_entry() enforces balance
            # before and after save), so re-check via the line aggregate here.
            from .journal import JournalEntry
            unbalanced_ids = [
                e.entry_number
                for e in JournalEntry.objects.filter(period=locked)
                .prefetch_related('lines')
                if not e.is_balanced
            ]
            if unbalanced_ids:
                raise ValueError(
                    f"Ada {len(unbalanced_ids)} journal entry yang tidak seimbang: "
                    f"{', '.join(unbalanced_ids)}. Harus diselesaikan dulu."
                )

            locked.status = self.STATUS_CLOSED
            locked.closed_by = user
            locked.closed_at = timezone.now()
            locked.save(update_fields=['status', 'closed_by', 'closed_at'])

            # Sinkronkan status ke instance pemanggil — lock()/views/test
            # membaca `self.status` setelah close() tanpa re-fetch.
            self.status = locked.status
            self.closed_by = locked.closed_by
            self.closed_at = locked.closed_at

    @property
    def payments(self):
        """Pembayaran client yang tanggalnya jatuh di periode ini."""
        from .payment import PaymentRecord
        return PaymentRecord.objects.filter(payment_date__gte=self.date_from, payment_date__lte=self.date_to)

    def lock(self, user):
        """Lock periode. Irreversible."""
        from django.db import transaction

        with transaction.atomic():
            # Kunci baris periode seperti close(): status dibaca ulang di bawah
            # kunci, jadi dua lock paralel tidak sama-sama lolos pemeriksaan.
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status != self.STATUS_CLOSED:
                raise ValueError("Periode harus closed dulu sebelum di-lock")

            # Validate no pending payments in this period
            from .payment import PaymentRecord
            pending = locked.payments.filter(status=PaymentRecord.STATUS_PENDING)
            if pending.exists():
                raise ValueError(f"Ada {pending.count()} pembayaran pending. Harus di-confirm/reject dulu.")

            locked.status = self.STATUS_LOCKED
            locked.locked_by = user
            locked.locked_at = timezone.now()
            locked.save(update_fields=['status', 'locked_by', 'locked_at'])

            self.status = locked.status
            self.locked_by = locked.locked_by
            self.locked_at = locked.locked_at
