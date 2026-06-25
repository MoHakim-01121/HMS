from django.db import models


class ReminderLog(models.Model):
    TYPES = [('H1_GUEST', 'H-1 ke Tamu'), ('H0_GUEST', 'Hari H ke Tamu')]

    cl            = models.ForeignKey('ConfirmationLetter', on_delete=models.CASCADE, related_name='reminder_logs')
    reminder_type = models.CharField(max_length=20, choices=TYPES)
    phone         = models.CharField(max_length=50)
    status        = models.CharField(max_length=10, choices=[('SENT', 'Sent'), ('FAILED', 'Failed')])
    sent_at       = models.DateTimeField(auto_now_add=True)
    error         = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Reminder Log'
        verbose_name_plural = 'Reminder Logs'

    def __str__(self):
        return f"{self.reminder_type} | {self.cl} | {self.status}"


class RecapLog(models.Model):
    TARGET_TYPES = [('PHONE', 'Nomor WA'), ('GROUP', 'Grup WA')]
    TRIGGERS     = [('AUTO', 'Otomatis'), ('MANUAL', 'Manual')]

    target_type  = models.CharField(max_length=10, choices=TARGET_TYPES)
    target       = models.CharField(max_length=100)
    cl_count     = models.PositiveIntegerField(default=0)
    message      = models.TextField()
    status       = models.CharField(max_length=10, choices=[('SENT', 'Sent'), ('FAILED', 'Failed')])
    sent_at      = models.DateTimeField(auto_now_add=True)
    triggered_by = models.CharField(max_length=10, choices=TRIGGERS, default='AUTO')
    error        = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Recap Log'
        verbose_name_plural = 'Recap Logs'

    def __str__(self):
        return f"Recap {self.target} | {self.status} | {self.triggered_by}"


class WATarget(models.Model):
    TARGET_TYPES = [('PHONE', 'Nomor WA'), ('GROUP', 'Grup WA')]

    label       = models.CharField(max_length=100)
    target      = models.CharField(max_length=100, unique=True)
    target_type = models.CharField(max_length=10, choices=TARGET_TYPES)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['label']
        verbose_name        = 'WA Target'
        verbose_name_plural = 'WA Targets'

    def save(self, *args, **kwargs):
        if not self.target_type:
            self.target_type = 'GROUP' if len(self.target) < 10 or '-' in self.target else 'PHONE'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} ({self.target})"


class MessageTemplate(models.Model):
    TEMPLATE_TYPES = [
        ('H1_GUEST',  'H-1 Sehari Sebelum'),
        ('H0_GUEST',  'H-0 Hari Check-in'),
        ('RECAP_OPS', 'Rekap Harian'),
    ]

    template_type = models.CharField(max_length=20, unique=True, choices=TEMPLATE_TYPES)
    body          = models.TextField()
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Message Template'
        verbose_name_plural = 'Message Templates'

    def __str__(self):
        return self.get_template_type_display()
