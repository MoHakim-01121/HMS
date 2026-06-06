from django.db import models
from django.urls import reverse

from .choices import Company, InvoiceType  # noqa: F401 — Company used in Remittance
from ..utils import convert_to_sar, next_sequence_number


class Invoice(models.Model):
    company        = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    client         = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices')
    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.HOTEL)
    invoice_number = models.CharField(max_length=100, db_index=True)
    customer_name  = models.CharField(max_length=200)
    issued_date    = models.DateField(null=True, blank=True)
    due_date       = models.DateField(null=True, blank=True)
    currency       = models.CharField(max_length=10, default='SAR')
    ai_summary     = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Invoice'
        verbose_name_plural = 'Invoices'

    def __str__(self):
        return f"{self.invoice_number} | {self.customer_name}"

    def get_absolute_url(self):
        return reverse('invoice_detail', args=[self.pk])

    @property
    def total_sar(self):
        return sum(r.total_sar for r in self.reservations.all())

    @property
    def total_paid_sar(self):
        return sum(
            int(round(convert_to_sar(float(p.amount), p.currency, float(p.exchange_rate))))
            for p in self.payments.all()
        )

    @property
    def remaining_sar(self):
        return self.total_sar - self.total_paid_sar

    @classmethod
    def generate_number(cls, invoice_type):
        from django.db import transaction
        prefix = 'INV' if invoice_type == InvoiceType.HOTEL else 'SVC'
        with transaction.atomic():
            nums = []
            for obj in cls.objects.select_for_update().filter(
                invoice_type=invoice_type,
                invoice_number__startswith=f'{prefix}-',
            ):
                parts = obj.invoice_number.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


class Reservation(models.Model):
    invoice            = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reservations')
    reservation_number = models.CharField(max_length=100)
    hotel              = models.CharField(max_length=200, blank=True)
    check_in           = models.DateField(null=True, blank=True)
    check_out          = models.DateField(null=True, blank=True)
    total_sar          = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Reservation'
        verbose_name_plural = 'Reservations'

    def __str__(self):
        return f"{self.reservation_number} | {self.hotel}"


class ServiceItem(models.Model):
    invoice        = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='service_items')
    service_number = models.PositiveIntegerField(default=1)
    name           = models.CharField(max_length=200)
    qty            = models.PositiveIntegerField(default=1)
    price          = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering            = ['service_number']
        verbose_name        = 'Service Item'
        verbose_name_plural = 'Service Items'

    def __str__(self):
        return f"{self.name} (x{self.qty})"

    @property
    def total(self):
        return int(self.qty * float(self.price))


class Payment(models.Model):
    invoice       = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    cl            = models.ForeignKey(
        'ConfirmationLetter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cl_payments',
    )
    linked_number = models.CharField(max_length=100, blank=True, db_index=True)
    payment_date  = models.DateField(null=True, blank=True)
    method        = models.CharField(max_length=100, blank=True)
    amount        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency      = models.CharField(max_length=10, default='SAR')
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    note          = models.TextField(blank=True)
    proof         = models.FileField(upload_to='payments/proof/', null=True, blank=True)

    class Meta:
        verbose_name        = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"{self.payment_date} | {self.amount} {self.currency}"

    @property
    def amount_sar(self):
        return int(round(convert_to_sar(float(self.amount), self.currency, float(self.exchange_rate))))


class Remittance(models.Model):
    remittance_number = models.CharField(max_length=20, unique=True, blank=True)
    company    = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    date       = models.DateField()
    note       = models.TextField(blank=True)
    proof      = models.FileField(upload_to='remittance/proof/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-date', '-created_at']
        verbose_name        = 'Remittance'
        verbose_name_plural = 'Remittances'

    def __str__(self):
        return f"{self.remittance_number} | {self.date} | {self.total_sar} SAR"

    @classmethod
    def generate_number(cls):
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for obj in cls.objects.select_for_update().filter(remittance_number__startswith='RMT-'):
                try:
                    nums.append(int(obj.remittance_number.split('-')[-1]))
                except (ValueError, IndexError):
                    pass
            return f"RMT-{(max(nums) + 1 if nums else 1):03d}"

    @property
    def total_sar(self):
        return int(sum(line.amount_sar for line in self.lines.all()))


class RemittanceLine(models.Model):
    remittance    = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='lines')
    invoice       = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='remittance_lines')
    linked_number = models.CharField(max_length=100)
    amount_sar    = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name        = 'Remittance Line'
        verbose_name_plural = 'Remittance Lines'

    def __str__(self):
        return f"Res {self.linked_number} → {self.amount_sar} SAR"


def _attachment_path(instance, filename):
    if instance.invoice_id:
        return f"attachments/invoice/{instance.invoice_id}/{filename}"
    return f"attachments/cl/{instance.cl_id}/{filename}"


class Attachment(models.Model):
    invoice     = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    cl          = models.ForeignKey('ConfirmationLetter', null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    file        = models.FileField(upload_to=_attachment_path)
    name        = models.CharField(max_length=255)
    size        = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Attachment'
        verbose_name_plural = 'Attachments'

    def __str__(self):
        return self.name

    @property
    def ext(self):
        return self.name.lower().rsplit('.', 1)[-1] if '.' in self.name else ''

    @property
    def is_image(self):
        return self.ext in ('jpg', 'jpeg', 'png', 'gif', 'webp')

    @property
    def icon(self):
        if self.is_image:
            return 'image'
        if self.ext == 'pdf':
            return 'pdf'
        return 'file'
