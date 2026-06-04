from datetime import date

from django.db import models
from django.urls import reverse
from django.utils import timezone

from .choices import Company


class Client(models.Model):
    company    = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    name       = models.CharField(max_length=200)
    city       = models.CharField(max_length=100, blank=True)
    province   = models.CharField(max_length=100, blank=True)
    lat        = models.FloatField(null=True, blank=True)
    lng        = models.FloatField(null=True, blank=True)
    pic        = models.CharField(max_length=200, blank=True, verbose_name='PIC')
    wa         = models.CharField(max_length=30, blank=True, verbose_name='WhatsApp')
    email      = models.EmailField(blank=True)
    note       = models.TextField(blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('client_detail', args=[self.pk])

    @property
    def total_invoices(self):
        return len(self.invoices.all()) + len(self.cls.all())

    @property
    def total_billed(self):
        return sum(inv.total_sar for inv in self.invoices.all())

    @property
    def total_paid(self):
        return sum(inv.total_paid_sar for inv in self.invoices.all())

    @property
    def outstanding(self):
        return sum(inv.remaining_sar for inv in self.invoices.all() if inv.remaining_sar > 0)

    @property
    def avg_days_to_pay(self):
        days_list = []
        for inv in self.invoices.all():
            if inv.remaining_sar <= 0 and inv.issued_date:
                payments = sorted(
                    inv.payments.all(),
                    key=lambda p: p.payment_date or date.min,
                    reverse=True,
                )
                if payments and payments[0].payment_date:
                    days_list.append((payments[0].payment_date - inv.issued_date).days)
        return round(sum(days_list) / len(days_list)) if days_list else None

    @property
    def last_transaction_date(self):
        invs = list(self.invoices.all())
        if not invs:
            return None
        return max(inv.created_at for inv in invs)

    @property
    def days_since_last_order(self):
        lt = self.last_transaction_date
        if not lt:
            return None
        now = timezone.now()
        if lt.tzinfo is None:
            lt = timezone.make_aware(lt)
        return (now - lt).days

    @property
    def score(self):
        s = 0
        total = self.total_billed
        if total >= 100000: s += 40
        elif total >= 50000: s += 30
        elif total >= 10000: s += 20
        elif total > 0: s += 10
        avg = self.avg_days_to_pay
        if avg is not None:
            if avg <= 7: s += 40
            elif avg <= 14: s += 30
            elif avg <= 30: s += 20
            elif avg <= 60: s += 10
        days = self.days_since_last_order
        if days is not None:
            if days <= 30: s += 20
            elif days <= 60: s += 15
            elif days <= 90: s += 5
        return s

    @property
    def risk_label(self):
        if self.outstanding > 0:
            due_invs = sorted(
                [i for i in self.invoices.all() if i.due_date is not None],
                key=lambda i: i.due_date,
            )
            if due_invs:
                overdue = (date.today() - due_invs[0].due_date).days
                if overdue > 60: return 'high'
                if overdue > 0:  return 'medium'
        days = self.days_since_last_order
        if days and days > 45 and self.total_invoices > 0:
            return 'dormant'
        return 'ok'
