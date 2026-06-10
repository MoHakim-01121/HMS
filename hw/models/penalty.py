from django.db import models


class CancellationPenalty(models.Model):
    cl              = models.OneToOneField('ConfirmationLetter', on_delete=models.CASCADE, related_name='penalty')
    penalty_number  = models.CharField(max_length=50, unique=True)
    cancellation_date = models.DateField()
    reason          = models.TextField(blank=True)

    penalty_amount   = models.DecimalField(max_digits=14, decimal_places=2)
    penalty_currency = models.CharField(max_length=10, default='SAR')
    exchange_rate    = models.DecimalField(max_digits=14, decimal_places=4, default=1)

    is_paid        = models.BooleanField(default=False)
    payment_date   = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=100, blank=True)
    payment_note   = models.TextField(blank=True)

    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Cancellation Penalty'
        verbose_name_plural = 'Cancellation Penalties'

    def __str__(self):
        return f"{self.penalty_number} — {self.cl.confirmation_number}"

    @property
    def penalty_amount_sar(self):
        return float(self.penalty_amount) * float(self.exchange_rate)

    @classmethod
    def generate_number(cls):
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for num_str in cls.objects.select_for_update().filter(
                penalty_number__startswith='PNL-',
            ).values_list('penalty_number', flat=True):
                parts = num_str.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"PNL-{(max(nums) + 1 if nums else 1):03d}"
