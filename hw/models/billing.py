from django.db import models


class BillingLog(models.Model):
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='billing_logs')
    target  = models.CharField(max_length=100)
    message = models.TextField()
    status  = models.CharField(max_length=10, choices=[('SENT', 'Sent'), ('FAILED', 'Failed')])
    error   = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-sent_at']
        verbose_name        = 'Billing Log'
        verbose_name_plural = 'Billing Logs'

    def __str__(self):
        return f"Billing {self.invoice_id} → {self.target} | {self.status}"
