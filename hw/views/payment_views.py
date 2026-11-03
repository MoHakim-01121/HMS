"""Payment views — list, detail, record, confirm, reject."""
import json
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http.request import RawPostDataException
from django.shortcuts import redirect
from django.utils import timezone
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, payment_receiving_branches, scope
from ..finance import posting
from ..finance_helpers import (
    FinanceError,
    _payment_snapshot,
    confirm_payment,
    create_payment_record,
    reverse_journal_entry,
)
from ..i18n import tr
from ..models.client import Client
from ..models.invoice import Invoice
from ..models.journal import JournalEntry
from ..models.payment import PaymentLog, PaymentRecord
from ..models.role import ADMIN_SLUG
from ..permissions import get_role, require_perm
from ..utils import CURRENCIES, round_half_up
from .helpers import (
    _parse_date,
    _parse_search_tokens,
    _to_float,
    csv_export_response,
    money_account_choices,
    pagination_props,
    resolve_money_account,
    serialize_journal_entry,
)

logger = logging.getLogger(__name__)


def _payment_props(p):
    from pathlib import PurePosixPath
    proof_url = p.proof.url if p.proof else None
    proofs = []
    if p.proof:
        try:
            size = p.proof.size or 0
        except OSError:  # file missing from storage; the record still shows its name
            size = 0
        proofs.append({
            'url': proof_url,
            'name': PurePosixPath(p.proof.name).name,
            'size': size,
        })
    from ..finance import queries as fq
    # Void/reversed/pending/rejected money never landed (or was taken back),
    # so it is neither allocated nor unallocated -- same rule as the list's
    # unapplied stat, which only sums EFFECTIVE_STATUSES.
    if p.status in PaymentRecord.EFFECTIVE_STATUSES:
        unallocated = fq.payment_unallocated_sar(p.pk)
        allocated = p.amount_sar - unallocated
    else:
        unallocated = allocated = 0
    group_key, group_label, group_tone = _GROUP_META[_group_of(p)]
    return {
        'id': p.pk,
        'payment_number': p.payment_number,
        'invoice_id': p.invoice_id,
        'invoice_number': p.invoice.invoice_number if p.invoice else None,
        'client_id': p.client_id,
        'client_name': p.client.name if p.client else None,
        # hotel/check_in/check_out ikut dikirim supaya tabel alokasi di detail
        # bisa menyebut kamar mana yang dibayar, bukan cuma nomor reservasi.
        'allocations': [{
            'id': a.pk,
            'reservation_id': a.reservation_id,
            'reservation_number': a.reservation.reservation_number if a.reservation else None,
            'hotel': a.reservation.hotel if a.reservation else '',
            'check_in': a.reservation.check_in.isoformat() if a.reservation and a.reservation.check_in else None,
            'check_out': a.reservation.check_out.isoformat() if a.reservation and a.reservation.check_out else None,
            'invoice_number': a.invoice_line.invoice.invoice_number,
            'amount_sar': a.amount_sar,
        } for a in p.allocations.select_related('invoice_line__confirmation_letter__hotel', 'invoice_line__invoice')],
        'unallocated_sar': unallocated,
        'allocated_sar': allocated,
        'deposited_sar': p.deposited_sar,
        'payment_date': p.payment_date.isoformat() if p.payment_date else None,
        'amount': p.amount,
        'currency': p.currency,
        'exchange_rate': float(p.exchange_rate),
        'amount_sar': p.amount_sar,
        'method': p.method,
        'received_in': p.received_in,
        'received_in_display': p.get_received_in_display(),
        'receiving_account': p.receiving_account.token if p.receiving_account_id else None,
        'receiving_account_label': str(p.receiving_account) if p.receiving_account else None,
        'receiving_branch': p.receiving_branch_code,
        'reference': p.reference,
        'note': p.note,
        'proof_url': proof_url,
        'proof': proofs,
        # `status` as the screens read it: lifecycle, and for an effective
        # payment its allocation state (received / partially_applied / applied).
        'status': p.display_status,
        'status_display': p.display_status_label,
        'status_group': group_key,
        'status_group_label': group_label,
        'status_group_tone': group_tone,
        'confirmed_by': p.confirmed_by.username if p.confirmed_by else None,
        'confirmed_at': p.confirmed_at.isoformat() if p.confirmed_at else None,
        'rejected_reason': p.rejected_reason,
        'created_by': p.created_by.username if p.created_by else None,
        'created_at': p.created_at.isoformat(),
    }


def _open_invoices(queryset, limit=None):
    """Invoices in `queryset` the client still owes on, newest first.

    Whether an invoice is paid is derived from the ledger, not stored, so the
    filter runs here: not void, and not yet covered by payments."""
    from ..finance import queries as fq
    invoices = list(
        queryset.exclude(status=Invoice.STATUS_VOID).with_lines().order_by('-created_at')
    )
    ids = [inv.pk for inv in invoices]
    paid_map = fq.invoice_paid_map(ids)
    credited_map = fq.invoice_credited_map(ids)
    out = []
    for inv in invoices:
        credited, deposited = credited_map.get(inv.pk, (0, 0))
        total = inv.total_sar
        if total > 0 and paid_map.get(inv.pk, 0) - deposited >= total - credited:
            continue
        out.append(inv)
        if limit and len(out) >= limit:
            break
    return out


def _invoice_choices(queryset):
    """Choices daftar invoice untuk dialog Record Payment / ApplyPaymentSheet.

    Setiap entry membawa client_id + client_name supaya frontend bisa
    mengfilter invoice per client (client-first) dan menurunkan client saat
    invoice dipilih. Reservations ikut dikirim supaya ApplyPaymentSheet bisa
    menampilkan baris alokasi tanpa fetch tambahan.
    """
    from ..finance import queries as fq
    from ..finance.credit_note_service import _credited_by_lines
    from .context import _build_reservation_context
    invoices = list(queryset)
    ids = [inv.pk for inv in invoices]
    paid_map = fq.invoice_paid_map(ids)
    res_paid = fq.reservation_paid_maps(ids)
    credited = _credited_by_lines(ids)
    out = []
    for inv in invoices:
        res_ctx = _build_reservation_context(inv, credited=credited[inv.pk], paid_map=res_paid[inv.pk])
        reservations = [{
            'id': r.get('id'),
            'number': r['number'],
            'hotel': r['hotel'],
            'total': r['total_int'],
            'paid': r['paid_int'],
            'remaining': r['remaining_int'],
        } for r in res_ctx]
        client_name = inv.client.name
        out.append({
            'id': inv.pk,
            'label': f'{inv.invoice_number} - {client_name}',
            'client_id': inv.client_id,
            'client_name': client_name,
            'remaining': inv.total_sar - paid_map.get(inv.pk, 0),
            'reservations': reservations,
        })
    return out


def _resolve_target_invoice(payment, data, request, targets=()):
    """Deposit (pembayaran tanpa invoice): invoice utama yang dilekatkan.

    `invoice_id` yang dikirim dipakai bila ada (harus milik client
    pembayaran ini); tanpa itu, invoice dari alokasi terbesarnya. Mengembalikan
    Invoice, atau None (pesan error sudah dipasang). TIDAK menyimpan apa pun --
    pemanggil melekatkan lewat _attach_invoice di dalam transaksi yang sama
    dengan alokasinya, supaya permintaan yang ditolak tidak meninggalkan
    deposit menempel ke invoice itu.
    """
    if payment.invoice_id:
        return payment.invoice
    invoice_id = data.get('invoice_id')
    if not invoice_id:
        if targets:
            return max(targets, key=lambda t: t[1])[0].invoice
        messages.error(
            request,
            tr(request, 'Choose the invoice this deposit goes to.', 'Pilih invoice tujuan untuk pembayaran deposit ini.'),
        )
        return None
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except (Invoice.DoesNotExist, TypeError, ValueError):
        messages.error(request, tr(request, 'Invoice not found.', 'Invoice tujuan tidak ditemukan.'))
        return None
    if invoice.client_id != payment.client_id:
        messages.error(
            request,
            tr(request, 'That invoice does not belong to this payment\'s client.', 'Invoice tujuan bukan milik client pembayaran ini.'),
        )
        return None
    return invoice


def _attach_invoice(payment, invoice):
    """Lekatkan deposit ke invoice tujuan. Panggil di dalam transaction.atomic."""
    if payment.invoice_id != invoice.pk:
        payment.invoice = invoice
        payment.save(update_fields=['invoice'])


_PAYMENT_SORT_MAP = {
    '-created_at':   ('-created_at',),
    '-payment_date': ('-payment_date', '-created_at'),
    'payment_date':  ('payment_date', 'created_at'),
    '-amount_sar':   ('-amount_sar', '-created_at'),
}
# What the user filters and reads on the list. The payment stores only its
# lifecycle status; whether its money has been allocated is derived from the
# allocation rows (PaymentRecord.allocation_state), so an effective payment
# falls into one of three groups by that state.
PAYMENT_STATUS_GROUPS = (
    ('pending',     'Awaiting confirmation', 'yellow'),
    ('unallocated', 'Unallocated',           'blue'),
    ('partial',     'Partially allocated',   'yellow'),
    ('allocated',   'Allocated',             'green'),
    ('cancelled',   'Cancelled',             'gray'),
)
_GROUP_META = {key: (key, label, tone) for key, label, tone in PAYMENT_STATUS_GROUPS}
_DEAD_STATUSES = (PaymentRecord.STATUS_REJECTED, PaymentRecord.STATUS_REVERSED, PaymentRecord.STATUS_VOIDED)
# Links from before the statuses were reduced (?status=applied, ...).
_LEGACY_STATUS_GROUP = {
    'received': 'unallocated', 'confirmed': 'unallocated', 'partially_applied': 'partial',
    'applied': 'allocated', 'rejected': 'cancelled', 'reversed': 'cancelled', 'voided': 'cancelled',
}


def _group_of(payment):
    """Group key of one payment (see PAYMENT_STATUS_GROUPS)."""
    if payment.status == PaymentRecord.STATUS_PENDING:
        return 'pending'
    return payment.allocation_state or 'cancelled'


def _group_q(key):
    """Q over a queryset annotated with_allocated() for one group."""
    confirmed = Q(status=PaymentRecord.STATUS_CONFIRMED)
    if key == 'pending':
        return Q(status=PaymentRecord.STATUS_PENDING)
    if key == 'cancelled':
        return Q(status__in=_DEAD_STATUSES)
    if key == 'unallocated':
        return confirmed & Q(allocated=0)
    if key == 'partial':
        return confirmed & Q(allocated__gt=0, allocated__lt=F('amount_sar'))
    return confirmed & Q(allocated__gte=F('amount_sar'))


def _status_group_keys(values):
    """Normalise ?status= values to group keys, keeping order and dropping junk.

    A raw status (?status=applied from an older link) maps to its group.
    """
    out = []
    for v in values:
        if v in _GROUP_META:
            key = v
        elif v in _LEGACY_STATUS_GROUP:
            key = _LEGACY_STATUS_GROUP[v]
        else:
            continue
        if key not in out:
            out.append(key)
    return out


def _payment_filter_params(request):
    """Read the Payment list filters off the querystring.

    `status` is repeatable (?status=a&status=b), so a single ?status=pending
    link from before multi-select still works.
    """
    return {
        'q': request.GET.get('q', '').strip(),
        'status_list': _status_group_keys(request.GET.getlist('status')),
        'date_from': _parse_date(request.GET.get('date_from', '').strip()),
        'date_to': _parse_date(request.GET.get('date_to', '').strip()),
        'client_id': request.GET.get('client', '').strip(),
        'invoice_id': request.GET.get('invoice', '').strip(),
        'sort': request.GET.get('sort', '-created_at'),
    }


def _apply_payment_filters(qs, f):
    """Shared by the list and CSV export so the two never return different rows."""
    if f['q']:
        combined = Q()
        for token in _parse_search_tokens(f['q']):
            combined |= (
                Q(payment_number__icontains=token)
                | Q(client__name__icontains=token)
                | Q(invoice__invoice_number__icontains=token)
                | Q(reference__icontains=token)
                | Q(method__icontains=token)
            )
        qs = qs.filter(combined)
    if f['status_list']:
        wanted = Q()
        for key in f['status_list']:
            wanted |= _group_q(key)
        qs = qs.with_allocated().filter(wanted)
    if f['date_from']:
        qs = qs.filter(payment_date__gte=f['date_from'])
    if f['date_to']:
        qs = qs.filter(payment_date__lte=f['date_to'])
    if f['client_id'].isdigit():
        qs = qs.filter(client_id=f['client_id'])
    if f['invoice_id'].isdigit():
        qs = qs.filter(invoice_id=f['invoice_id'])
    return qs.order_by(*_PAYMENT_SORT_MAP.get(f['sort'], _PAYMENT_SORT_MAP['-created_at']))


def _payments(request):
    """Payments of the user's branches: received into their accounts, or
    paid by their clients (also when head office received them)."""
    return scope(PaymentRecord.objects.all(), request.user)


_LIST_GROUPS = ('pending', 'open', 'allocated', 'cancelled')


def _list_group_q(key):
    """The four status groups of the Payments list filter."""
    if key == 'open':
        return _group_q('unallocated') | _group_q('partial')
    return _group_q(key)


@require_perm('payments', 'view')
def payment_list(request):
    """Payments list (Record View HMS canvas): cash received in the month
    (by currency on the back), waiting confirmation, unapplied cash, the
    toolbar and the table, one page at a time."""
    from ..finance import queries as fq
    from .helpers import csv_list, list_per_page, list_period, pct_delta, prev_month_range
    base = _payments(request).select_related('client', 'invoice', 'receiving_account', 'created_by')
    q = request.GET.get('q', '').strip()
    groups = csv_list(request, 'status', _LIST_GROUPS)
    currencies = csv_list(request, 'cur', ['IDR', 'USD', 'SAR'])
    methods = csv_list(request, 'method')
    sort = request.GET.get('sort', '-date')
    date_from, date_to, period = list_period(request)

    qs = _apply_payment_filters(base, {'q': q, 'status_list': [], 'date_from': None, 'date_to': None,
                                       'client_id': '', 'invoice_id': '', 'sort': '-created_at'})
    # Waiting confirmation and unapplied cash are not tied to a month.
    if not (groups and set(groups) <= {'pending', 'open'}):
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)
    period_qs = qs.with_allocated()
    counts = {k: period_qs.filter(_list_group_q(k)).count() for k in _LIST_GROUPS}
    from django.db.models import Count
    cur_counts = {r['receiving_account__currency']: r['n'] for r in period_qs.values('receiving_account__currency').annotate(n=Count('id'))}
    method_counts = sorted(((r['method'], r['n']) for r in period_qs.values('method').annotate(n=Count('id')) if r['method']), key=lambda x: -x[1])

    rows_qs = period_qs
    if groups:
        wanted = Q()
        for k in groups:
            wanted |= _list_group_q(k)
        rows_qs = rows_qs.filter(wanted)
    if currencies:
        rows_qs = rows_qs.filter(receiving_account__currency__in=currencies)
    if methods:
        rows_qs = rows_qs.filter(method__in=methods)
    rows_qs = rows_qs.order_by('payment_date' if sort == 'date' else '-payment_date', '-pk')

    page_obj = Paginator(rows_qs, list_per_page(request)).get_page(request.GET.get('page'))
    page = list(page_obj)
    unalloc = fq.payment_unallocated_map([p.pk for p in page if p.status in PaymentRecord.EFFECTIVE_STATUSES])
    rows = []
    for p in page:
        g = _group_of(p)
        rows.append({
            'id': p.pk, 'payment_number': p.payment_number,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'client_name': p.client.name if p.client_id else '',
            'invoice_number': p.invoice.invoice_number if p.invoice_id else '',
            'account': str(p.receiving_account) if p.receiving_account_id else '',
            'method': p.method, 'currency': p.currency, 'amount': p.amount, 'amount_sar': p.amount_sar,
            'group': g, 'status': p.status, 'status_display': p.get_status_display(),
            'unallocated_sar': unalloc.get(p.pk, 0),
            'has_proof': bool(p.proof), 'proof_url': p.proof.url if p.proof else None,
            'created_by': p.created_by.username if p.created_by_id else None,
        })

    kpis = None
    if period['month']:
        eff = _payments(request).filter(status__in=PaymentRecord.EFFECTIVE_STATUSES)
        month = eff.filter(payment_date__gte=date_from, payment_date__lte=date_to)
        pf, pl = prev_month_range(date_from)
        prev_sar = sum(eff.filter(payment_date__gte=pf, payment_date__lte=pl).values_list('amount_sar', flat=True))
        by_cur = {}
        for cur, amt, sar in month.values_list('receiving_account__currency', 'amount', 'amount_sar'):
            a2 = by_cur.setdefault(cur, [0, 0]); a2[0] += amt; a2[1] += sar
        received = sum(v[1] for v in by_cur.values())
        pending = _payments(request).filter(status=PaymentRecord.STATUS_PENDING)
        um = fq.payment_unallocated_map(eff.values_list('pk', flat=True))
        kpis = {
            'received': received, 'delta': pct_delta(received, prev_sar), 'prev_month': pf.strftime('%Y-%m'),
            'by_currency': [{'code': c, 'amount': by_cur[c][0], 'sar': by_cur[c][1]} for c in ('IDR', 'USD', 'SAR') if c in by_cur],
            'pending_count': pending.count(), 'pending_sar': sum(pending.values_list('amount_sar', flat=True)),
            'unapplied_sar': sum(um.values()), 'unapplied_count': sum(1 for v in um.values() if v > 0),
        }

    def invoice_choices():
        return _invoice_choices(_open_invoices(scope(Invoice.objects.all(), request.user), limit=50))

    def client_choices():
        return [{'id': c.pk, 'name': c.name, 'city': c.city}
                for c in scope(Client.objects.filter(is_active=True), request.user).order_by('name')]

    years = sorted({d.year for d in _payments(request).dates('payment_date', 'year')} | {timezone.localdate().year})
    return inertia_render(request, 'Payment/List', props={
        'payments': rows,
        'filters': {'q': q, 'status': groups, 'cur': currencies, 'method': methods, 'sort': sort,
                    'per': list_per_page(request), **period},
        'years': years,
        'counts': counts, 'currency_counts': cur_counts,
        'method_counts': [{'method': m, 'count': n} for m, n in method_counts],
        'kpis': kpis,
        'export_qs': '?' + '&'.join(x for x in [
            f'date_from={date_from.isoformat()}' if date_from else '', f'date_to={date_to.isoformat()}' if date_to else '',
        ] if x),
        'invoice_choices': invoice_choices,
        'client_choices': client_choices,
        'account_choices': lambda: money_account_choices(branches=payment_receiving_branches(request.user)),
        'pagination': pagination_props(page_obj),
    })


def _allocatable_reservations(payment):
    """Baris hotel yang bisa menerima alokasi pembayaran ini, per invoice:
    invoice utamanya, invoice yang sudah ia alokasikan, lalu invoice lain
    milik client yang masih terbuka (maks. 30). Invoice void dilewati.

    `max_sar` tiap baris = batas untuk pembayaran ini (posting.allocation_caps):
    sisa tagihan baris ditambah yang sudah dibayar pembayaran ini sendiri ke
    baris itu. `remaining_int` (sisa tagihan sekarang) bisa negatif =
    kelebihan bayar."""
    from .context import _build_reservation_context
    invoices, seen = [], set()

    def add(inv):
        if inv is not None and inv.pk not in seen and not inv.is_void:
            seen.add(inv.pk)
            invoices.append(inv)

    add(payment.invoice)
    allocated = payment.allocations.values_list('invoice_line__invoice_id', flat=True)
    for inv in Invoice.objects.filter(pk__in=list(allocated)).order_by('-created_at'):
        add(inv)
    for inv in _open_invoices(Invoice.objects.filter(client_id=payment.client_id), limit=30):
        add(inv)

    from ..finance import queries as fq
    from ..finance.credit_note_service import _credited_by_lines
    ids = [inv.pk for inv in invoices]
    res_paid = fq.reservation_paid_maps(ids)
    credited = _credited_by_lines(ids)
    rows = []
    for inv in invoices:
        for row in _build_reservation_context(inv, credited=credited[inv.pk], paid_map=res_paid[inv.pk]):
            rows.append({**row, 'invoice_id': inv.pk, 'invoice_number': inv.invoice_number})
    caps = posting.allocation_caps(payment, [r['id'] for r in rows])
    for row in rows:
        row['max_sar'] = max(caps.get(row['id'], 0), 0)
    return rows


def _unbilled_reservations(payment, limit=20):
    """CL milik client pembayaran ini yang belum ditagihkan di invoice mana
    pun (dan tidak batal): belum bisa menerima alokasi. Ditampilkan abu-abu di
    lembar alokasi dengan alasannya, supaya tidak terlihat seperti hilang."""
    from ..models import ConfirmationLetter
    from ..models.confirmation import ReservationStatus
    from ..models.invoice import InvoiceLine
    billed = InvoiceLine.objects.filter(
        kind=InvoiceLine.KIND_HOTEL, voided_at__isnull=True, confirmation_letter__isnull=False,
    ).values('confirmation_letter_id')
    letters = (
        ConfirmationLetter.objects.filter(client_id=payment.client_id)
        .exclude(pk__in=billed).exclude(reservation_status=ReservationStatus.CANCELLED)
        .select_related('hotel').order_by('-check_in')[:limit]
    )
    return [{
        'id': cl.pk,
        'number': cl.confirmation_number,
        'hotel': cl.hotel_name,
        'check_in': cl.check_in.isoformat() if cl.check_in else None,
        'check_out': cl.check_out.isoformat() if cl.check_out else None,
    } for cl in letters]


@require_perm('payments', 'view')
def payment_detail(request, pk):
    payment = get_in_scope_or_404(
        PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by', 'created_by', 'receiving_account__branch'),
        request.user, pk=pk,
    )
    logs = payment.logs.select_related('performed_by').order_by('-performed_at')

    # Get related journal entries
    journal_entries = JournalEntry.objects.for_source('PaymentRecord', payment.pk).order_by('-entry_date')

    reservations = _allocatable_reservations(payment)

    # Receipts (kwitansi) auto-generated for this payment.
    from ..models import Receipt
    receipts = [{
        'id': r.pk,
        'receipt_number': r.receipt_number,
        'status': r.status,
        'status_display': r.get_status_display(),
        'voided_reason': r.voided_reason,
    } for r in Receipt.objects.filter(payment=payment)]

    return inertia_render(request, 'Payment/Detail', props={
        'payment': _payment_props(payment),
        'reservations': reservations,
        'unbilled_reservations': _unbilled_reservations(payment),
        'receipts': receipts,
        'logs': [{
            'action': l.action,
            'action_display': l.get_action_display(),
            'before_state': l.before_state,
            'after_state': l.after_state,
            'performed_by': l.performed_by.username if l.performed_by else None,
            'performed_at': l.performed_at.isoformat(),
            'note': l.note,
        } for l in logs],
        'journal_entries': [serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit) for e in journal_entries],
    })


@require_perm('payments', 'create')
def payment_record(request):
    """Record a new payment from the Payment List page.
    
    Supports per-reservation allocation via `allocations` JSON field:
    [{"reservation_id": 1, "amount": 5000}, {"reservation_id": 2, "amount": 3000}]

    Pembayaran dibuat dengan status PENDING — belum ada jurnal, belum ada
    receipt. Finansial/admin me-review dulu (cek benar-benar masuk) lalu
    klik Confirm (payment_confirm) untuk memposting jurnal + menerbitkan
    kwitansi, atau Reject bila tidak sah.
    """
    if request.method != 'POST':
        return redirect('payment_list')

    # Handle both JSON and multipart form data (for file uploads)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
    else:
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        except (json.JSONDecodeError, ValueError):
            data = request.POST

    invoice_id = data.get('invoice_id')
    payment_date = _parse_date(data.get('payment_date'))

    invoice = None
    client = None
    if invoice_id:
        invoice = get_in_scope_or_404(Invoice.objects.all(), request.user, pk=invoice_id)
        client = invoice.client
    else:
        # Deposit: invoice opsional — client wajib dipilih eksplisit.
        client_id = data.get('client_id')
        if not client_id:
            messages.error(request, tr(request, 'Choose the client for a payment without an invoice (deposit).', 'Pilih client untuk pembayaran tanpa invoice (deposit).'))
            return redirect('payment_list')
        client = get_in_scope_or_404(Client.objects.all(), request.user, pk=client_id)
    amount = _to_float(data.get('amount'))
    exchange_rate = _to_float(data.get('exchange_rate'), 1) or 1
    currency = (data.get('currency') or 'SAR').upper()

    # Receiving account (v2.0 FASE C): a concrete MoneyAccount (bank or cash)
    # picked in the UI. received_in stays the routing fallback — derived
    # from the account's branch when one is chosen, or the raw field for
    # older callers/tests that still send received_in directly.
    receiving_account = resolve_money_account(data.get('account'))
    if receiving_account is not None:
        received_in = receiving_account.branch_id
        # The payment's currency is its receiving account's currency.
        currency = receiving_account.currency
    else:
        received_in = data.get('received_in', 'sby')
        if received_in not in ('sby', 'jkt', 'pusat'):
            received_in = 'sby'
    allowed = payment_receiving_branches(request.user)
    if allowed is not None and received_in not in allowed:
        messages.error(request, tr(request, 'The receiving account is outside your branch.', 'Rekening penerima di luar cabang Anda.'))
        return redirect('payment_list')

    # amount/amount_sar are PositiveIntegerField. A negative value passes a
    # bare truthiness check, survives convert_to_sar, and only fails at the
    # database CHECK constraint -- an IntegrityError the FinanceError handler
    # below does not catch, so the user gets a 500 instead of a form message.
    # A non-positive rate does the same by flipping a positive amount.
    if not amount or amount <= 0:
        messages.error(request, tr(request, 'The payment amount must be more than zero.', 'Jumlah pembayaran harus lebih besar dari nol.'))
        return redirect('payment_list')
    if amount != int(amount):
        # Money is kept in whole units (riyal, rupiah, dollar); a fraction
        # would be dropped silently when stored.
        messages.error(request, tr(request, 'The payment amount must be a whole number, without decimals.', 'Jumlah pembayaran harus bilangan bulat, tanpa desimal.'))
        return redirect('payment_list')
    amount = int(amount)
    if exchange_rate <= 0:
        messages.error(request, tr(request, 'The rate must be more than zero.', 'Kurs harus lebih besar dari nol.'))
        return redirect('payment_list')
    if currency not in CURRENCIES:
        messages.error(request, tr(request, f'Unknown currency: {currency}.', f'Mata uang tidak dikenal: {currency}.'))
        return redirect('payment_list')

    # Handle proof file upload — same size/type guard as every other proof
    # path (remittance, invoice billing, client refund). nginx caps the body
    # at 3 MB upstream; this is the backstop plus the image/PDF type check.
    proof_file = request.FILES.get('proof')
    if proof_file:
        from .helpers import validate_proof_file
        proof_error = validate_proof_file(proof_file)
        if proof_error:
            messages.error(request, proof_error)
            return redirect('payment_list')
    else:
        # Proof is required on every payment (Receive/Apply flow): the receipt
        # anchors the CR Piutang entry that auto-posts at receive time.
        messages.error(request, tr(request, 'Attach the proof of payment.', 'Bukti pembayaran wajib dilampirkan.'))
        return redirect('payment_list')

    # Parse per-reservation allocations
    allocations_raw = data.get('allocations', '')
    allocations = []
    if allocations_raw:
        try:
            allocations = json.loads(allocations_raw) if isinstance(allocations_raw, str) else allocations_raw
        except (json.JSONDecodeError, ValueError):
            allocations = []

    if invoice is None and allocations:
        messages.error(
            request,
            tr(request, 'A deposit (no invoice) cannot be allocated right away. Choose the invoice when distributing it later.', 'Deposit (tanpa invoice) tidak bisa langsung dialokasikan. Pilih invoice tujuan saat distribusi nanti.'),
        )
        return redirect('payment_list')

    from django.utils import timezone as tz

    from ..finance import posting
    from ..models import Reservation

    if allocations:
        # Satu transfer dgn beberapa reservasi = SATU PaymentRecord
        # (menyimpan amount asli + kurs utk analisis), lalu PaymentAllocation
        # analitik per reservasi dalam SAR (riyal patokan). Ini menggantikan
        # perilaku lama yg membuat satu PaymentRecord per baris -- yang
        # memperlakukan alokasi SAR sebagai currency asli, membuat
        # amount_sar double-convert dan warning "Allocation != Amount"
        # membandingkan SAR vs currency asli.
        valid_alloc = [
            a for a in allocations
            if _to_float(a.get('amount', 0)) and _to_float(a.get('amount', 0)) > 0
        ]
        if not valid_alloc:
            messages.error(request, tr(request, 'No valid allocation.', 'Tidak ada alokasi yang valid.'))
            return redirect('payment_list')

        # PaymentAllocation per reservasi — nominal dalam SAR (riyal patokan).
        # A reservation_id that does not belong to this invoice used to be
        # skipped silently: the payment was created for the full amount, the
        # skipped slice never landed anywhere, and the user was told the
        # allocation succeeded. Refuse the whole request instead.
        targets = []
        unknown = []
        for alloc in valid_alloc:
            reservation = Reservation.objects.filter(
                pk=alloc.get('reservation_id'), invoice=invoice, voided_at__isnull=True,
            ).first()
            if reservation is None:
                unknown.append(str(alloc.get('reservation_id')))
                continue
            targets.append((reservation, round_half_up(_to_float(alloc.get('amount', 0)))))
        if unknown:
            messages.error(
                request,
                tr(request, f'These reservations do not belong to this invoice: {", ".join(unknown)}.', f'Reservasi berikut bukan milik invoice ini: {", ".join(unknown)}.'),
            )
            return redirect('payment_list')
        if not targets:
            messages.error(request, tr(request, 'No valid allocation.', 'Tidak ada alokasi yang valid.'))
            return redirect('payment_list')

        # Nilai SAR pembayaran (riyal patokan), untuk memvalidasi total alokasi
        # SEBELUM record dibuat -- jangan sisakan PaymentRecord yatim bila over.
        from ..utils import convert_to_sar
        sar_amount = convert_to_sar(amount, currency, exchange_rate)
        if sum(a for _, a in targets) > sar_amount:
            messages.error(
                request,
                tr(request, f'The allocations total is more than the payment\'s SAR value ({sar_amount:,}).', f'Total alokasi melebihi nilai SAR pembayaran ({sar_amount:,}).'),
            )
            return redirect('payment_list')

        from django.db import transaction
        try:
            with transaction.atomic():
                payment = create_payment_record(
                    invoice=invoice,
                    client=client,
                    payment_date=payment_date or tz.now().date(),
                    amount=amount,                 # currency asli (mis. IDR) — utk analisis
                    currency=currency,
                    exchange_rate=exchange_rate,   # kurs asli — utk analisis
                    method=data.get('method', ''),
                    reference=data.get('reference', ''),
                    note=data.get('note', '') or f'Allocated to {len(valid_alloc)} reservation(s)',
                    created_by=request.user,
                    received_in=received_in,
                    receiving_account=receiving_account,
                )
                if proof_file:
                    payment.proof = proof_file
                    payment.save(update_fields=['proof'])

                # Simpan alokasi analitik (SAR) saja — TANPA jurnal. Payment
                # tetap PENDING sampai dikonfirmasi oleh finance/admin.
                posting.allocate_payment(payment, targets, created_by=request.user)
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('payment_list')

        messages.success(
            request,
            tr(request, 'Payment created and allocated. Waiting for Finance/Admin to confirm.', 'Payment berhasil dibuat dan dialokasikan. Menunggu konfirmasi finance/admin.'),
        )
        return redirect(f'/finance/payments/?invoice={invoice.pk}')
    else:
        # No allocations — single payment, unallocated.
        from django.db import transaction
        try:
            with transaction.atomic():
                payment = create_payment_record(
                    invoice=invoice,
                    client=client,
                    payment_date=payment_date or tz.now().date(),
                    amount=amount,
                    currency=currency,
                    exchange_rate=exchange_rate,
                    method=data.get('method', ''),
                    reference=data.get('reference', ''),
                    note=data.get('note', ''),
                    created_by=request.user,
                    received_in=received_in,
                    receiving_account=receiving_account,
                )
                if proof_file:
                    payment.proof = proof_file
                    payment.save(update_fields=['proof'])
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('payment_list')

        messages.success(
            request,
            tr(request, f'Payment {payment.payment_number} created. Waiting for Finance/Admin to confirm.', f'Payment {payment.payment_number} berhasil dibuat. Menunggu konfirmasi finance/admin.'),
        )
        return redirect('payment_detail', pk=payment.pk)


@require_perm('payments', 'approve')
def payment_confirm(request, pk):
    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)
    if request.method == 'POST':
        try:
            note = ''
            if request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                    note = data.get('note', '')
                except (json.JSONDecodeError, ValueError):
                    pass

            # Pemisahan tugas: pencatat pembayaran tidak mengonfirmasi uangnya
            # sendiri. Admin boleh (break-glass), dan itu tercatat di log.
            if payment.created_by_id == request.user.pk:
                if get_role(request.user) != ADMIN_SLUG:
                    messages.error(
                        request,
                        tr(request, 'You recorded this payment yourself — another user has to confirm it.', 'Pembayaran ini Anda catat sendiri — konfirmasi harus oleh user lain.'),
                    )
                    return redirect('payment_detail', pk=pk)
                note = ('[Dikonfirmasi oleh pencatatnya sendiri (admin)] ' + note).strip()

            # Konfirmasi dan kwitansinya satu transaksi: tidak ada pembayaran
            # terkonfirmasi tanpa kwitansi bila pembuatan kwitansi gagal.
            from django.db import transaction

            from ..finance.receipt_service import ensure_receipt
            with transaction.atomic():
                confirm_payment(payment, confirmed_by=request.user, note=note)
                ensure_receipt(payment, created_by=request.user)

            messages.success(request, tr(request, f'Payment {payment.payment_number} confirmed.', f'Payment {payment.payment_number} berhasil dikonfirmasi.'))
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'approve')
def payment_reject(request, pk):
    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)
    if request.method == 'POST':
        # Only a PENDING payment may be rejected. A confirmed/allocated payment
        # has already touched the ledger (DR Kas / CR Piutang); flipping it to
        # REJECTED without reversing its journal entry would desync the ledger
        # from the payment record. Rejection on effective payments must go
        # through payment_reverse.
        if payment.status not in (PaymentRecord.STATUS_PENDING,):
            messages.error(
                request,
                tr(request, f'Payment {payment.payment_number} is {payment.display_status_label}. Only a pending payment can be rejected. Use Reverse to correct an effective payment.', f'Payment {payment.payment_number} berstatus {payment.display_status_label}. Hanya payment pending yang bisa ditolak. Gunakan Reverse sebagai koreksi untuk pembayaran efektif.'),
            )
            return redirect('payment_detail', pk=pk)

        reason = ''
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                reason = data.get('reason', '')
            except (json.JSONDecodeError, ValueError):
                pass

        old_state = {
            'status': payment.status,
            'amount_sar': payment.amount_sar,
        }
        from django.db import transaction
        with transaction.atomic():
            # Lock and re-read: a confirm racing this reject must not leave a
            # posted payment marked REJECTED.
            current = (
                PaymentRecord.objects.select_for_update()
                .values_list('status', flat=True).get(pk=payment.pk)
            )
            if current != PaymentRecord.STATUS_PENDING:
                messages.error(request, tr(request, f'Payment {payment.payment_number} has already been processed.', f'Payment {payment.payment_number} sudah diproses.'))
                return redirect('payment_detail', pk=pk)
            payment.status = PaymentRecord.STATUS_REJECTED
            payment.rejected_reason = reason
            payment.save(update_fields=['status', 'rejected_reason'])
            dropped = posting.clear_payment_allocations(payment)
            PaymentLog.objects.create(
                payment=payment,
                action=PaymentLog.ACTION_REJECTED,
                before_state={**old_state, 'allocations': dropped},
                after_state={'status': payment.status},
                performed_by=request.user,
                note=reason or 'Payment rejected',
            )
        messages.success(request, tr(request, f'Payment {payment.payment_number} rejected.', f'Payment {payment.payment_number} ditolak.'))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


def _request_allocations(request):
    """(data, allocations) dari body permintaan alokasi.

    Inertia/axios mengirim JSON (request.POST kosong); multipart/urlencoded
    lewat request.POST. Pada POST multipart request.body sudah habis dibaca
    oleh request.POST dan melempar RawPostDataException -- bukan ValueError --
    jadi harus ditangkap supaya tidak jadi 500. `allocations` None berarti
    formatnya tidak valid."""
    data = request.POST
    if not data.get('allocations'):
        try:
            body = json.loads(request.body) if request.body else None
            if isinstance(body, dict):
                data = body
        except (json.JSONDecodeError, ValueError, RawPostDataException):
            pass
    raw = data.get('allocations', '')
    try:
        allocations = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
    except (json.JSONDecodeError, ValueError):
        allocations = None
    return data, allocations


def _allocation_targets(payment, allocations, request):
    """[(baris hotel, nominal)] dari isian alokasi.

    Baris boleh dari invoice mana pun milik client pembayaran ini, selama
    invoice dan barisnya tidak void (realokasi lintas invoice). Baris yang
    tidak dikenal ditolak, bukan dibuang diam-diam -- selisihnya akan
    mengambang tanpa peringatan. Mengembalikan None bila ditolak (pesan
    error sudah dipasang)."""
    from ..models import Reservation
    targets, unknown = [], []
    for alloc in allocations:
        amount = round_half_up(_to_float(alloc.get('amount', 0)))
        if amount <= 0:
            continue
        try:
            line_id = int(alloc.get('reservation_id'))
        except (TypeError, ValueError):
            line_id = None
        line = None
        if line_id:
            line = (
                Reservation.objects.select_related('invoice', 'confirmation_letter')
                .filter(pk=line_id, voided_at__isnull=True, invoice__client_id=payment.client_id)
                .exclude(invoice__status=Invoice.STATUS_VOID)
                .first()
            )
        if line is None:
            unknown.append(str(alloc.get('reservation_id')))
            continue
        targets.append((line, amount))
    if unknown:
        messages.error(
            request,
            tr(request, f'These reservations do not belong to this payment\'s client: {", ".join(unknown)}.', f'Reservasi berikut bukan milik client pembayaran ini: {", ".join(unknown)}.'),
        )
        return None
    return targets


def _save_allocations(request, pk, *, require_targets, log_action, success):
    """Apply / Reallocate: ganti alokasi pembayaran efektif lewat
    posting.reallocate_payment (pembalik + posting ulang bertanggal hari ini,
    batas per baris, log sebelum/sesudah)."""
    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        messages.error(
            request,
            tr(request, f'Payment {payment.payment_number} is {payment.display_status_label}. Only an effective payment can be allocated.', f'Payment {payment.payment_number} berstatus {payment.display_status_label}. Hanya payment efektif yang bisa dialokasikan.'),
        )
        return redirect('payment_detail', pk=pk)

    data, allocations = _request_allocations(request)
    if allocations is None:
        messages.error(request, tr(request, 'Invalid allocation format.', 'Format alokasi tidak valid.'))
        return redirect('payment_detail', pk=pk)
    if require_targets and not allocations:
        messages.error(request, tr(request, 'The allocation cannot be empty.', 'Alokasi tidak boleh kosong.'))
        return redirect('payment_detail', pk=pk)

    targets = _allocation_targets(payment, allocations, request)
    if targets is None:
        return redirect('payment_detail', pk=pk)
    if require_targets and not targets:
        messages.error(request, tr(request, 'No valid allocation.', 'Tidak ada alokasi yang valid.'))
        return redirect('payment_detail', pk=pk)

    total = sum(amount for _, amount in targets)
    if total > payment.amount_sar:
        messages.error(
            request,
            tr(request, f'The allocations total ({total:,}) is more than the payment ({payment.amount_sar:,}).', f'Total alokasi ({total:,}) melebihi jumlah pembayaran ({payment.amount_sar:,}).'),
        )
        return redirect('payment_detail', pk=pk)

    # Deposit (tanpa invoice): lekatkan ke invoice utama di transaksi yang sama.
    header = payment.invoice
    if header is None and (targets or data.get('invoice_id')):
        header = _resolve_target_invoice(payment, data, request, targets)
        if header is None:
            return redirect('payment_detail', pk=pk)

    from django.db import transaction
    try:
        with transaction.atomic():
            if header is not None:
                _attach_invoice(payment, header)
            posting.reallocate_payment(
                payment, targets, created_by=request.user,
                log_action=log_action,
                note=f'{len(targets)} reservation(s), {total:,} SAR',
            )
    except FinanceError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, tr(request, *success).format(number=payment.payment_number))
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_reallocate(request, pk):
    """Realokasi payment efektif. Body: allocations = [{"reservation_id", "amount"}].
    Daftar kosong boleh: semua jadi belum teralokasi (lalu bisa ke deposit)."""
    return _save_allocations(
        request, pk, require_targets=False, log_action=PaymentLog.ACTION_ALLOCATED,
        success=('Payment {number} reallocated.', 'Payment {number} berhasil direalokasi.'),
    )


def _retire_payment(payment, *, status, action, reversal_date, journal_note, user):
    """Take an effective payment's money back out: shared by Void and Reverse.

    One transaction, because journal reversal, status, receipt and allocations
    are one fact -- reversing the journal on its own could leave a payment
    still "applied" whose money the ledger already took back. Raises
    FinanceError (rolled back) for the caller to report.
    """
    from django.db import transaction

    from ..finance.bank_ledger import void_bank_transactions
    from ..finance.receipt_service import void_receipts_for_payment

    with transaction.atomic():
        # Lock and re-read: a double-click must not pass the caller's status
        # check twice and reverse the journal a second time.
        payment.status = (
            PaymentRecord.objects.select_for_update()
            .values_list('status', flat=True).get(pk=payment.pk)
        )
        if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
            raise FinanceError(
                f'Payment {payment.payment_number} sudah {payment.display_status_label}.'
            )
        old_state = _payment_snapshot(payment)
        journals = JournalEntry.objects.for_source('PaymentRecord', payment.pk).filter(
            entry_type=JournalEntry.TYPE_PAYMENT,
        ).live()
        for journal in journals:
            reverse_journal_entry(journal, reversal_date, user, note=journal_note)

        # Money this payment moved to the client's deposit comes back first
        # (refused when the deposit has already been spent).
        payment.refresh_from_db(fields=['deposited_sar'])
        posting.return_payment_deposit(payment, created_by=user, entry_date=reversal_date)

        payment.status = status
        payment.save(update_fields=['status'])
        void_bank_transactions('PaymentRecord', payment.pk)
        void_receipts_for_payment(
            payment, reason=f'Payment {payment.payment_number} {status}',
        )
        dropped = posting.clear_payment_allocations(payment)


        PaymentLog.objects.create(
            payment=payment,
            action=action,
            before_state={**old_state, 'allocations': dropped},
            after_state=_payment_snapshot(payment),
            performed_by=user,
            note=f'Payment {status}',
        )


@require_perm('payments', 'delete')
def payment_reverse(request, pk):
    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)
    if request.method == 'POST':
        # Pending money was never received: there is no journal to reverse,
        # so it must go through Reject instead.
        if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
            messages.error(
                request,
                tr(request, f'Payment {payment.payment_number} is {payment.display_status_label} and cannot be reversed.', f'Payment {payment.payment_number} berstatus {payment.display_status_label} dan tidak bisa di-reverse.'),
            )
            return redirect('payment_detail', pk=pk)

        try:
            _retire_payment(
                payment, status=PaymentRecord.STATUS_REVERSED,
                action=PaymentLog.ACTION_REVERSED,
                reversal_date=timezone.localdate(),
                journal_note=f'Reversal for {payment.payment_number}',
                user=request.user,
            )
            messages.success(request, tr(request, f'Payment {payment.payment_number} reversed.', f'Payment {payment.payment_number} di-reverse.'))
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_apply(request, pk):
    """Alokasikan payment efektif ke reservasi (minimal satu). Body sama dengan
    payment_reallocate; reservasi boleh dari invoice lain milik client yang sama."""
    return _save_allocations(
        request, pk, require_targets=True, log_action=PaymentLog.ACTION_APPLIED,
        success=('Payment {number} allocated.', 'Payment {number} berhasil dialokasikan.'),
    )


@require_perm('payments', 'delete')
def payment_void(request, pk):
    """Void a payment — posts a reversal journal entry and marks status voided.

    Only effective payments (received / partially_applied / applied / confirmed
    / allocated) may be voided. Pending payments should use reject instead.
    """
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)

    voidable = PaymentRecord.EFFECTIVE_STATUSES
    if payment.status not in voidable:
        messages.error(
            request,
            tr(request, f'Payment {payment.payment_number} is {payment.display_status_label} and cannot be voided.', f'Payment {payment.payment_number} berstatus {payment.display_status_label} dan tidak bisa di-void.'),
        )
        return redirect('payment_detail', pk=pk)

    try:
        _retire_payment(
            payment, status=PaymentRecord.STATUS_VOIDED,
            action=PaymentLog.ACTION_VOIDED,
            reversal_date=payment.payment_date,
            journal_note=f'Voided: {payment.payment_number}',
            user=request.user,
        )
        messages.success(request, tr(request, f'Payment {payment.payment_number} voided.', f'Payment {payment.payment_number} di-void.'))
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_to_deposit(request, pk):
    """Move a payment's excess (the part not allocated to any invoice line)
    to the client's deposit. An explicit step: until then the money stays on
    the payment and can only be allocated to that client's invoices."""
    payment = get_in_scope_or_404(PaymentRecord.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)
    try:
        moved = posting.move_payment_excess_to_deposit(payment, created_by=request.user)
    except FinanceError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, tr(request, f'{moved:,} SAR from {payment.payment_number} moved to {payment.client.name}\'s deposit.', f'{moved:,} SAR dari {payment.payment_number} dipindahkan ke deposit {payment.client.name}.'))
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'export')
def payment_export_csv(request):
    """Export payments as CSV."""
    # Same filters as payment_list: exporting from a filtered list must not
    # hand back every payment in the system.
    payments = _apply_payment_filters(
        _payments(request).select_related('client', 'invoice', 'confirmed_by'),
        _payment_filter_params(request),
    )

    headers = [
        'Payment #', 'Date', 'Client', 'Invoice', 'Amount', 'Currency',
        'Rate', 'Amount SAR', 'Method', 'Status', 'Confirmed By',
        'Confirmed At', 'Reference', 'Note', 'Created At',
    ]
    rows = ([
        p.payment_number,
        p.payment_date,
        p.client.name if p.client else '',
        p.invoice.invoice_number if p.invoice else '',
        p.amount,
        p.currency,
        p.exchange_rate,
        p.amount_sar,
        p.method,
        p.status,
        p.confirmed_by.username if p.confirmed_by else '',
        p.confirmed_at,
        p.reference,
        p.note,
        p.created_at,
    ] for p in payments)
    return csv_export_response(f'payments-{timezone.localdate().isoformat()}.csv', headers, rows)
