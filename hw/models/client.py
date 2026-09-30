import re
import unicodedata
from datetime import date

from django.db import models
from django.urls import reverse
from django.utils import timezone

# Cabang pemilik bila tidak dipilih (satu-satunya cabang penjual saat ini).
DEFAULT_OWNER_BRANCH = 'sby'

_LEGAL_FORMS = {'pt', 'cv', 'tbk', 'persero', 'ud'}


def client_name_key(name):
    """Bentuk pembanding nama perusahaan, untuk mencegah client dobel:
    "PT. Safaar" / "SAFAAR" / "  safaar  " → "safaar"."""
    text = unicodedata.normalize('NFKC', name or '').lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = [t for t in text.split() if t not in _LEGAL_FORMS]
    return ' '.join(tokens) or ' '.join(text.split())


def default_owner_branch():
    return DEFAULT_OWNER_BRANCH


class Client(models.Model):
    REMINDER_TARGET_CHOICES = [
        ('PIC', 'PIC'),
        ('GROUP', 'WhatsApp Group'),
        ('BOTH', 'PIC & Group'),
    ]

    # `name` = nama perusahaan; `brand` = nama brand travel (boleh kosong).
    # Nama yang tampil di dokumen: brand, atau nama perusahaan bila kosong.
    name       = models.CharField(max_length=200, db_index=True)
    brand      = models.CharField(max_length=200, blank=True)
    # Diisi save() dari `name`; UNIQUE supaya satu perusahaan tidak tercatat dua kali.
    name_key   = models.CharField(max_length=200, unique=True, editable=False)
    # Cabang pemilik client: penerbit invoice-nya. Client bisa pindah cabang;
    # invoice lama tetap atas nama cabang lama (Invoice.branch = fakta saat terbit).
    owner_branch = models.ForeignKey(
        'Branch', on_delete=models.PROTECT, related_name='clients', default=default_owner_branch,
    )
    city       = models.CharField(max_length=100, blank=True)
    province   = models.CharField(max_length=100, blank=True)
    address    = models.CharField(max_length=255, blank=True)
    lat        = models.FloatField(null=True, blank=True)
    lng        = models.FloatField(null=True, blank=True)
    pic        = models.CharField(max_length=200, blank=True, verbose_name='PIC')
    wa         = models.CharField(max_length=30, blank=True, verbose_name='WhatsApp')
    wa_group   = models.CharField(max_length=100, blank=True, verbose_name='WhatsApp Group')
    reminder_target = models.CharField(max_length=10, choices=REMINDER_TARGET_CHOICES, default='GROUP')
    email      = models.EmailField(blank=True)
    note       = models.TextField(blank=True)
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name_key = client_name_key(self.name)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'name' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'name_key'}
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.brand or self.name

    def get_absolute_url(self):
        return reverse('client_detail', args=[self.pk])

    @property
    def resolved_invoices(self):
        """Invoices belonging to this client via either signal: the direct
        Invoice.client FK (populated by invoice_views.py/services_views.py
        forms) OR a journal line carrying this client's dimension (Fase 7 --
        pengganti Charge.client yang pensiun; charge income lines sudah
        membawa dimensi client). Unioned rather than picking one -- an invoice
        can have the FK set before any journal entry exists (or vice versa),
        and either signal alone would silently drop it from this client's
        totals/statement."""
        from django.db.models import Q
        from .invoice import Invoice
        from .journal import JournalLine
        journal_invoice_ids = JournalLine.objects.filter(
            client=self, invoice__isnull=False,
        ).values_list('invoice_id', flat=True).distinct()
        return Invoice.objects.filter(
            Q(client=self) | Q(pk__in=journal_invoice_ids)
        ).distinct()

    @property
    def total_invoices(self):
        return len(self.resolved_invoices) + len(self.cls.all())

    @property
    def total_billed(self):
        from ..finance import queries
        return queries.client_billed_sar(self.id)

    @property
    def total_paid(self):
        from ..finance import queries
        return queries.client_paid_sar(self.id)

    @property
    def outstanding(self):
        # Satu kantong per klien (bukan dijumlah per-invoice) -- konsisten dengan
        # desain ledger: piutang di satu reservasi bisa dilunasi lewat alokasi
        # yang berasal dari kelebihan bayar di reservasi lain klien yang sama.
        from ..finance import queries
        return max(0, queries.client_receivable(self.id))

    @property
    def avg_days_to_pay(self):
        from ..models.payment import PaymentRecord
        days_list = []
        for inv in self.resolved_invoices:
            if inv.remaining_sar <= 0 and inv.issued_date:
                last = (
                    inv.payment_records
                    .filter(status__in=PaymentRecord.EFFECTIVE_STATUSES)
                    .order_by('-payment_date', '-pk')
                    .first()
                )
                if last and last.payment_date:
                    days_list.append((last.payment_date - inv.issued_date).days)
        return round(sum(days_list) / len(days_list)) if days_list else None

    @property
    def last_transaction_date(self):
        invs = list(self.resolved_invoices)
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
                [i for i in self.resolved_invoices if i.due_date is not None],
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
