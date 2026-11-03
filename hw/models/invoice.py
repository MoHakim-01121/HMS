"""Invoice, its lines and its revisions (skema target 3.3).

An invoice bills one client, in the name of one branch, in one currency. What
it bills lives in InvoiceLine, one table for every kind of line:

  hotel    a reservation (ConfirmationLetter). The line stores no hotel name,
           no dates and no amount: those are read from the reservation, so an
           invoice can never disagree with the CL it bills.
  penalty  a cancellation penalty on a reservation billed here.

Amounts are whole units of the invoice currency (hotel invoices are always
SAR). Whether an invoice is paid is never stored; it is derived from the
ledger (financial_state).
"""
from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone

from .choices import InvoiceType
from .currency import CURRENCY_CODES
from .uploads import random_name


class InvoiceQuerySet(models.QuerySet):
    def with_lines(self):
        """Load everything total_sar reads, in a fixed number of queries."""
        return self.select_related('client').prefetch_related(
            models.Prefetch('lines', queryset=InvoiceLine.objects.for_amounts()),
        )

    def name_matches(self, token):
        """Q: invoice number, or the client's company or brand name, contains `token`."""
        return (
            models.Q(invoice_number__icontains=token)
            | models.Q(client__name__icontains=token)
            | models.Q(client__brand__icontains=token)
        )


class Invoice(models.Model):
    # ── Lifecycle (stored) ────────────────────────────────────
    # draft is reserved for an invoice that has not been issued to the client
    # yet; every invoice the app creates today is issued immediately.
    STATUS_DRAFT  = 'draft'
    STATUS_ISSUED = 'issued'
    STATUS_VOID   = 'void'
    STATUS_CHOICES = [
        (STATUS_DRAFT,  'Draft'),
        (STATUS_ISSUED, 'Issued'),
        (STATUS_VOID,   'Void'),
    ]

    # ── Payment state (derived, never stored) ─────────────────
    FINANCIAL_STATE_UNPAID   = 'unpaid'
    FINANCIAL_STATE_PARTIAL  = 'partial'
    FINANCIAL_STATE_PAID     = 'paid'
    FINANCIAL_STATE_OVERDUE  = 'overdue'
    FINANCIAL_STATE_CHOICES = [
        (FINANCIAL_STATE_UNPAID,  'Unpaid'),
        (FINANCIAL_STATE_PARTIAL, 'Partial'),
        (FINANCIAL_STATE_PAID,    'Paid'),
        (FINANCIAL_STATE_OVERDUE, 'Overdue'),
    ]

    invoice_type   = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.HOTEL, db_index=True)
    invoice_number = models.CharField(max_length=100)
    season         = models.ForeignKey(
        'Season', null=True, blank=True, on_delete=models.PROTECT, related_name='invoices',
    )
    client         = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='invoices')
    # Issuing branch: a fact at the time of issue. It starts as the client's
    # owner branch and stays put when the client later moves to another branch.
    # It also decides the "Pay to" accounts shown on the invoice.
    branch         = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='invoices')
    issued_date    = models.DateField(null=True, blank=True)
    due_date       = models.DateField(null=True, blank=True, db_index=True)
    # Agreed with the client per invoice: usually 30 when the first check-in is
    # more than 30 days after issue. 0 means no down payment.
    down_payment_percent = models.PositiveSmallIntegerField(default=0)
    # In PostgreSQL this column has a FOREIGN KEY to hw_currency (see the
    # migration); in Django it stays text so `invoice.currency == 'SAR'` holds.
    currency       = models.CharField(max_length=3, default='SAR')

    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ISSUED)
    void_reason = models.TextField(blank=True)
    voided_at   = models.DateTimeField(null=True, blank=True)
    voided_by   = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')

    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Invoice'
        verbose_name_plural = 'Invoices'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(invoice_type__in=[c[0] for c in InvoiceType.choices]),
                name='invoice_type_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['draft', 'issued', 'void']), name='invoice_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=CURRENCY_CODES), name='invoice_currency_valid',
            ),
            models.CheckConstraint(
                condition=~models.Q(invoice_type='hotel') | models.Q(currency='SAR'),
                name='invoice_hotel_is_sar',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(issued_date__isnull=True) | models.Q(due_date__isnull=True)
                    | models.Q(due_date__gte=models.F('issued_date'))
                ),
                name='invoice_due_not_before_issued',
            ),
            models.CheckConstraint(
                condition=models.Q(down_payment_percent__lte=100),
                name='invoice_down_payment_percent_range',
            ),
            models.UniqueConstraint(
                fields=['season', 'invoice_number'], condition=models.Q(season__isnull=False),
                name='invoice_number_season_uniq',
            ),
            models.UniqueConstraint(
                fields=['invoice_number'], condition=models.Q(season__isnull=True),
                name='invoice_number_no_season_uniq',
            ),
            models.CheckConstraint(
                condition=~models.Q(status='void') | models.Q(voided_at__isnull=False),
                name='invoice_void_has_timestamp',
            ),
        ]

    def __str__(self):
        return f"{self.invoice_number} | {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.branch_id and self.client_id:
            self.branch_id = self.client.owner_branch_id
        season = self.season_for_date(self.issued_date)
        if self.season_id != (season.pk if season else None):
            self.season = season
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'season'}
        super().save(*args, **kwargs)

    @staticmethod
    def season_for_date(issued_date):
        if issued_date is None:
            return None
        from .period import Season
        return Season.objects.filter(date_from__lte=issued_date, date_to__gte=issued_date).first()

    @classmethod
    def number_exists_in_season(cls, number, issued_date, *, exclude_pk=None):
        season = cls.season_for_date(issued_date)
        scope = {'season_id': season.pk} if season else {'season__isnull': True}
        qs = cls.objects.filter(invoice_number=number, **scope)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    def get_absolute_url(self):
        return reverse('invoice_detail', args=[self.pk])

    @property
    def customer_name(self):
        """The client's display name (brand, or company name). Not a column:
        an invoice cannot carry a name that differs from its client's."""
        return self.client.display_name

    # ── Lines ─────────────────────────────────────────────────

    def billed_lines(self):
        """The lines this invoice bills. For a void invoice: the lines it
        billed at the moment it was voided (they were voided together with it).
        A line taken off a live invoice earlier is not among them."""
        if 'lines' in getattr(self, '_prefetched_objects_cache', {}):
            lines = list(self.lines.all())
        else:
            lines = list(self.lines.for_amounts())
        for line in lines:
            line.invoice = self   # share this instance (and its frozen-amount cache)
        stamp = self.voided_at if self.is_void else None
        return [l for l in lines if l.voided_at == stamp]

    @property
    def reservations(self):
        """Hotel lines billed by this invoice, as a queryset."""
        return Reservation.objects.filter(invoice=self, voided_at=self._line_stamp())

    def _line_stamp(self):
        return self.voided_at if self.is_void else None

    @property
    def confirmation_letters(self):
        """Reservations currently billed by this invoice (none once it is void)."""
        from .confirmation import ConfirmationLetter
        return ConfirmationLetter.objects.on_invoice(self)

    def _next_line_no(self):
        last = self.lines.aggregate(m=models.Max('line_no'))['m'] or 0
        return last + 1

    def add_hotel_line(self, cl):
        """Bill reservation `cl` on this invoice."""
        if self.invoice_type != InvoiceType.HOTEL:
            raise ValueError('Only a hotel invoice can bill a reservation.')
        if cl.client_id != self.client_id:
            raise ValueError(
                f'CL {cl.confirmation_number} belongs to {cl.guest_name}, not to this invoice\'s client '
                f'({self.customer_name}). One invoice bills one client.'
            )
        other = InvoiceLine.objects.filter(
            kind=InvoiceLine.KIND_HOTEL, confirmation_letter=cl, voided_at__isnull=True,
        ).exclude(invoice=self).select_related('invoice').first()
        if other:
            raise ValueError(f'CL {cl.confirmation_number} is already billed on invoice {other.invoice.invoice_number}.')
        line, _ = InvoiceLine.objects.get_or_create(
            invoice=self, kind=InvoiceLine.KIND_HOTEL, confirmation_letter=cl, voided_at__isnull=True,
            defaults={'line_no': self._next_line_no()},
        )
        # A penalty on the reservation is billed wherever the reservation is.
        from .penalty import CancellationPenalty
        penalty = CancellationPenalty.objects.filter(cl_id=cl.pk).first()
        if penalty is not None:
            self.add_penalty_line(penalty)
        return line

    def add_penalty_line(self, penalty):
        """Bill `penalty` on this invoice, next to the reservation it belongs to."""
        if not self.lines.filter(
            kind=InvoiceLine.KIND_HOTEL, confirmation_letter_id=penalty.cl_id, voided_at__isnull=True,
        ).exists():
            raise ValueError('A penalty is billed on the invoice that bills its reservation.')
        line, _ = InvoiceLine.objects.get_or_create(
            invoice=self, kind=InvoiceLine.KIND_PENALTY, penalty=penalty, voided_at__isnull=True,
            defaults={'line_no': self._next_line_no()},
        )
        return line

    def pay_to_accounts(self):
        """Rekening tujuan bayar ("Pay to") invoice ini: rekening aktif cabang
        penerbit yang ditandai show_on_invoice. Satu sumber untuk kartu Pay to
        di detail invoice dan blok Informasi Pembayaran di draft pesan."""
        from .bank import BankAccount
        return BankAccount.objects.filter(
            branch_id=self.branch_id, is_active=True, show_on_invoice=True,
        ).order_by('currency', 'bank_name')

    # ── Amounts (derived) ─────────────────────────────────────

    @property
    def total_sar(self):
        """Sum of the billed lines, in the invoice currency."""
        return sum(line.amount for line in self.billed_lines())

    @property
    def total_paid_sar(self):
        from ..finance import queries
        return queries.invoice_paid_sar(self.id)

    @property
    def credited_sar(self):
        """Reduced by active credit notes."""
        from ..finance import queries
        return queries.invoice_credited_sar(self.id)

    @property
    def is_void(self):
        return self.status == self.STATUS_VOID

    @property
    def due_sar(self):
        """What the client owes in total: 0 when void, else total − credit notes."""
        return 0 if self.is_void else self.total_sar - self.credited_sar

    @property
    def credit_deposited_sar(self):
        """Paid money moved to client deposit by credit notes (no longer on this invoice)."""
        from ..finance import queries
        return queries.invoice_credit_deposited_sar(self.id)

    @property
    def applied_paid_sar(self):
        """Payments still standing against this invoice."""
        return self.total_paid_sar - self.credit_deposited_sar

    @property
    def remaining_sar(self):
        return self.due_sar - self.applied_paid_sar

    @property
    def down_payment_sar(self):
        """The agreed down payment, rounded half up; 0 when none or void."""
        return (self.due_sar * self.down_payment_percent + 50) // 100

    @property
    def down_payment_due_date(self):
        """24 hours after issue, by date: an invoice stores no issue time."""
        if not self.down_payment_percent or not self.issued_date:
            return None
        return self.issued_date + timedelta(days=1)

    @property
    def down_payment_outstanding_sar(self):
        return max(self.down_payment_sar - self.applied_paid_sar, 0)

    @property
    def down_payment_overdue(self):
        due = self.down_payment_due_date
        return bool(due and due < timezone.localdate() and self.down_payment_outstanding_sar > 0)

    @property
    def is_fully_paid(self):
        return self.applied_paid_sar >= self.due_sar and self.due_sar > 0

    @property
    def financial_state(self):
        """Payment state, computed fresh every read from the ledger."""
        total, paid = self.due_sar, self.applied_paid_sar
        if total > 0 and paid >= total:
            return self.FINANCIAL_STATE_PAID
        if self.due_date and self.due_date < timezone.localdate() and paid < total:
            return self.FINANCIAL_STATE_OVERDUE
        if paid > 0:
            return self.FINANCIAL_STATE_PARTIAL
        return self.FINANCIAL_STATE_UNPAID

    # ── Numbering ─────────────────────────────────────────────

    @classmethod
    def _sequence_context(cls, issued_date=None):
        """Counter key and invoice scope for the season containing this date."""
        season = cls.season_for_date(issued_date)
        if season:
            return f'INV-SEASON-{season.pk}', {'season_id': season.pk}
        return 'INV-NO-SEASON', {'season__isnull': True}

    @classmethod
    def _sequence_key(cls, issued_date=None):
        return cls._sequence_context(issued_date)[0]

    @classmethod
    def generate_number(cls, invoice_type, issued_date=None):
        from ..numbering import generate_sequential_number

        key, season_scope = cls._sequence_context(issued_date)
        return generate_sequential_number(
            cls, 'INV', field='invoice_number', padding=3, key=key,
            extra_filter={'invoice_type': invoice_type, **season_scope},
        )

    @classmethod
    def suggest_number(cls, invoice_type, issued_date=None):
        from ..numbering import peek_number

        key, season_scope = cls._sequence_context(issued_date)
        return peek_number(
            cls, 'INV', field='invoice_number', padding=3, key=key,
            extra_filter={'invoice_type': invoice_type, **season_scope},
        )

    @classmethod
    def claim_number(cls, invoice_type, number, issued_date=None):
        """Counter mengikuti nomor yang diketik user."""
        from ..numbering import advance_number

        key, season_scope = cls._sequence_context(issued_date)
        advance_number(
            cls, 'INV', number, field='invoice_number', key=key,
            extra_filter={'invoice_type': invoice_type, **season_scope},
        )


class InvoiceLineQuerySet(models.QuerySet):
    def for_amounts(self):
        """Load what `amount` reads: the reservation, its hotel and its rooms."""
        return self.select_related(
            'confirmation_letter__hotel', 'confirmation_letter__client', 'penalty',
        ).prefetch_related('confirmation_letter__rooms')

    def active(self):
        return self.filter(voided_at__isnull=True)

    def numbered(self, numbers):
        """Hotel lines whose reservation (CL) number is in `numbers`."""
        return self.filter(confirmation_letter__confirmation_number__in=list(numbers))

    def reservation_rows(self):
        """Dicts with the reservation facts of each hotel line, read from its CL:
        id, invoice_id, reservation_number, hotel, check_in, check_out."""
        return self.values(
            'id', 'invoice_id',
            reservation_number=models.F('confirmation_letter__confirmation_number'),
            hotel=models.F('confirmation_letter__hotel__name'),
            check_in=models.F('confirmation_letter__check_in'),
            check_out=models.F('confirmation_letter__check_out'),
        )


class InvoiceLine(models.Model):
    KIND_HOTEL   = 'hotel'
    KIND_PENALTY = 'penalty'
    KIND_CHOICES = [
        (KIND_HOTEL,   'Hotel reservation'),
        (KIND_PENALTY, 'Cancellation penalty'),
    ]

    # PROTECT: an invoice is voided, not deleted, once its lines carry money.
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='lines')
    line_no = models.PositiveSmallIntegerField()
    kind    = models.CharField(max_length=8, choices=KIND_CHOICES)

    # hotel: the reservation billed. One reservation is on at most one live line.
    confirmation_letter = models.ForeignKey(
        'ConfirmationLetter', null=True, blank=True, on_delete=models.PROTECT, related_name='invoice_lines',
    )
    # penalty: the cancellation penalty billed.
    penalty = models.ForeignKey(
        'CancellationPenalty', null=True, blank=True, on_delete=models.PROTECT, related_name='invoice_lines',
    )

    # Set when the line stops being billed: taken off the invoice after the
    # ledger already referenced it, or the whole invoice was voided. The row
    # stays, because journal lines and payment allocations point at it.
    voided_at = models.DateTimeField(null=True, blank=True)

    objects = InvoiceLineQuerySet.as_manager()

    class Meta:
        ordering            = ['invoice_id', 'line_no']
        verbose_name        = 'Invoice Line'
        verbose_name_plural = 'Invoice Lines'
        constraints = [
            models.UniqueConstraint(fields=['invoice', 'line_no'], name='invoice_line_no_uniq'),
            models.CheckConstraint(
                condition=models.Q(kind__in=['hotel', 'penalty']), name='invoice_line_kind_valid',
            ),
            # Each kind fills exactly its own columns.
            models.CheckConstraint(
                condition=(
                    models.Q(kind='hotel', confirmation_letter__isnull=False, penalty__isnull=True)
                    | models.Q(kind='penalty', penalty__isnull=False, confirmation_letter__isnull=True)
                ),
                name='invoice_line_shape_per_kind',
            ),
            models.UniqueConstraint(
                fields=['confirmation_letter'], condition=models.Q(voided_at__isnull=True, kind='hotel'),
                name='invoice_line_one_live_per_reservation',
            ),
            models.UniqueConstraint(
                fields=['penalty'], condition=models.Q(voided_at__isnull=True, kind='penalty'),
                name='invoice_line_one_live_per_penalty',
            ),
        ]

    def __str__(self):
        return f"{self.invoice_id}#{self.line_no} {self.label}"

    @property
    def is_voided(self):
        return self.voided_at is not None

    @property
    def label(self):
        if self.kind == self.KIND_HOTEL:
            return f'{self.reservation_number} · {self.hotel}'.strip(' ·')
        return f'Penalty {self.penalty.penalty_number}'

    @property
    def amount(self):
        """What this line bills, in the invoice currency.

        A voided line keeps the amount it had when it was voided (read from the
        invoice's revision history); a live line is computed from its source.
        """
        if self.voided_at is not None:
            return self._frozen_amount()
        return self.live_amount

    @property
    def live_amount(self):
        if self.kind == self.KIND_PENALTY:
            return self.penalty.penalty_amount
        from ..finance.reservation_rules import reservation_total_for_cl
        return reservation_total_for_cl(self.confirmation_letter)

    def _frozen_amount(self):
        invoice = self.invoice
        frozen = getattr(invoice, '_frozen_amounts', None)
        if frozen is None:
            frozen = {}
            for revision in invoice.revisions.order_by('-revision_no'):
                for row in revision.lines_snapshot:
                    frozen.setdefault(row.get('line_id'), int(row.get('amount') or 0))
            invoice._frozen_amounts = frozen
        return frozen.get(self.pk, 0)

    def void(self, at=None):
        self.voided_at = at or timezone.now()
        self.save(update_fields=['voided_at'])

    # ── Hotel line: read from the reservation ─────────────────

    @property
    def reservation_number(self):
        return self.confirmation_letter.confirmation_number if self.confirmation_letter_id else ''

    @property
    def hotel(self):
        return self.confirmation_letter.hotel_name if self.confirmation_letter_id else ''

    @property
    def check_in(self):
        return self.confirmation_letter.check_in if self.confirmation_letter_id else None

    @property
    def check_out(self):
        return self.confirmation_letter.check_out if self.confirmation_letter_id else None

    @property
    def client_id(self):
        return self.invoice.client_id

    @property
    def owner_branch_id(self):
        """Branch that owns this receivable: the invoice's issuing branch."""
        return self.invoice.branch_id

    @property
    def total_sar(self):
        return self.amount

    @property
    def total(self):
        return self.amount


class _KindManager(models.Manager.from_queryset(InvoiceLineQuerySet)):
    def __init__(self, kind):
        super().__init__()
        self._kind = kind

    def get_queryset(self):
        qs = super().get_queryset().filter(kind=self._kind)
        return qs.for_amounts() if self._kind == InvoiceLine.KIND_HOTEL else qs


class Reservation(InvoiceLine):
    """A hotel line. The name predates schema v2, where "reservation" means
    the ConfirmationLetter; payments and the journal still reference lines
    through this name until they move to a single invoice-line key."""

    objects = _KindManager(InvoiceLine.KIND_HOTEL)

    class Meta:
        proxy = True
        verbose_name = 'Hotel Line'
        verbose_name_plural = 'Hotel Lines'

    def save(self, *args, **kwargs):
        self.kind = InvoiceLine.KIND_HOTEL
        super().save(*args, **kwargs)


class InvoiceRevision(models.Model):
    """One row each time what an issued invoice bills changes.

    CLs change after they are invoiced, and the invoice follows. The revision
    keeps what the invoice billed after each change (total and amount per
    line), so an earlier figure can always be shown and explained. Append-only.
    """
    REASON_ISSUE       = 'issue'
    REASON_CL_CHANGE   = 'cl_change'
    REASON_LINE_CHANGE = 'line_change'
    REASON_CREDIT_NOTE = 'credit_note'
    REASON_VOID        = 'void'
    REASON_CHOICES = [
        (REASON_ISSUE,       'Issued'),
        (REASON_CL_CHANGE,   'Reservation changed'),
        (REASON_LINE_CHANGE, 'Lines changed'),
        (REASON_CREDIT_NOTE, 'Credit note'),
        (REASON_VOID,        'Voided'),
    ]

    invoice     = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='revisions')
    revision_no = models.PositiveIntegerField()
    # What the client owes on this invoice after the change (0 once void).
    total       = models.BigIntegerField()
    reason      = models.CharField(max_length=12, choices=REASON_CHOICES)
    # [{line_id, line_no, kind, label, amount}] at that moment.
    lines_snapshot = models.JSONField(default=list)
    changed_by  = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    changed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['invoice_id', 'revision_no']
        verbose_name = 'Invoice Revision'
        verbose_name_plural = 'Invoice Revisions'
        constraints = [
            models.UniqueConstraint(fields=['invoice', 'revision_no'], name='invoice_revision_no_uniq'),
            models.CheckConstraint(
                condition=models.Q(reason__in=['issue', 'cl_change', 'line_change', 'credit_note', 'void']),
                name='invoice_revision_reason_valid',
            ),
        ]

    def __str__(self):
        return f"{self.invoice_id} rev {self.revision_no} ({self.reason})"


def _attachment_path(instance, filename):
    # Random stored name; the uploaded name stays in Attachment.name.
    if instance.invoice_id:
        return f"attachments/invoice/{instance.invoice_id}/{random_name(filename)}"
    return f"attachments/cl/{instance.cl_id}/{random_name(filename)}"


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
        constraints = [
            # Lampiran milik tepat satu dokumen: invoice ATAU reservasi.
            models.CheckConstraint(
                condition=(
                    models.Q(invoice__isnull=False, cl__isnull=True)
                    | models.Q(invoice__isnull=True, cl__isnull=False)
                ),
                name='attachment_exactly_one_parent',
            ),
        ]

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
