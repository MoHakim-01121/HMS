"""Payment views — list, detail, record, confirm, reject."""
import json
import logging

from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http.request import RawPostDataException
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from inertia import render as inertia_render

from ..models.payment import PaymentRecord, PaymentLog
from ..models.invoice import Invoice
from ..models.client import Client
from ..models.journal import JournalEntry
from ..finance_helpers import (
    create_payment_record, confirm_payment,
    reverse_journal_entry, _payment_snapshot,
    FinanceError,
)
from ..permissions import require_perm
from ..i18n import tr
from ..finance import posting
from ..utils import CURRENCIES
from .helpers import (
    serialize_journal_entry, _parse_date, _parse_search_tokens, _to_float, _is_mobile,
    pagination_props, csv_export_response, money_account_choices, resolve_money_account,
)

logger = logging.getLogger(__name__)


def _payment_props(p):
    from pathlib import PurePosixPath
    proof_url = p.proof.url if p.proof else None
    proofs = []
    if p.proof:
        proofs.append({
            'url': proof_url,
            'name': PurePosixPath(p.proof.name).name,
            'size': p.proof.size or 0,
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
    group_key, group_label, group_tone = _STATUS_GROUP[p.status]
    return {
        'id': p.pk,
        'payment_number': p.payment_number,
        'invoice_id': p.invoice_id,
        'invoice_number': p.invoice.invoice_number if p.invoice else None,
        'client_id': p.client_id,
        'client_name': p.client.name if p.client else None,
        'reservation_id': p.reservation_id,
        'service_item_id': p.service_item_id,
        # hotel/check_in/check_out ikut dikirim supaya tabel alokasi di detail
        # bisa menyebut kamar mana yang dibayar, bukan cuma nomor reservasi.
        # Alokasi ke ServiceItem tidak punya hotel/tanggal -- namanya dipakai
        # sebagai ganti di kolom yang sama.
        'allocations': [{
            'id': a.pk,
            'reservation_id': a.reservation_id,
            'reservation_number': a.reservation.reservation_number if a.reservation else None,
            'hotel': a.reservation.hotel if a.reservation else '',
            'check_in': a.reservation.check_in.isoformat() if a.reservation and a.reservation.check_in else None,
            'check_out': a.reservation.check_out.isoformat() if a.reservation and a.reservation.check_out else None,
            'service_item_id': a.service_item_id,
            'service_item_name': a.service_item.name if a.service_item else None,
            'amount_sar': a.amount_sar,
        } for a in p.allocations.select_related('reservation', 'service_item')],
        'unallocated_sar': unallocated,
        'allocated_sar': allocated,
        'payment_date': p.payment_date.isoformat() if p.payment_date else None,
        'amount': p.amount,
        'currency': p.currency,
        'exchange_rate': float(p.exchange_rate),
        'amount_sar': p.amount_sar,
        'method': p.method,
        'received_in': p.received_in,
        'received_in_display': p.get_received_in_display(),
        'receiving_account': (
            f'cash:{p.cash_account_id}' if p.cash_account_id
            else f'bank:{p.bank_account_id}' if p.bank_account_id else None
        ),
        'receiving_account_label': str(p.receiving_account) if p.receiving_account else None,
        'receiving_branch': p.receiving_branch_code,
        'bank_name': p.bank_name,
        'account_number': p.account_number,
        'reference': p.reference,
        'note': p.note,
        'proof_url': proof_url,
        'proof': proofs,
        'status': p.status,
        'status_display': p.get_status_display(),
        'status_group': group_key,
        'status_group_label': group_label,
        'status_group_tone': group_tone,
        'confirmed_by': p.confirmed_by.username if p.confirmed_by else None,
        'confirmed_at': p.confirmed_at.isoformat() if p.confirmed_at else None,
        'rejected_reason': p.rejected_reason,
        'created_by': p.created_by.username if p.created_by else None,
        'created_at': p.created_at.isoformat(),
    }


def _invoice_choices(queryset):
    """Choices daftar invoice untuk dialog Record Payment / ApplyPaymentSheet.

    Setiap entry membawa client_id + client_name supaya frontend bisa
    mengfilter invoice per client (client-first) dan menurunkan client saat
    invoice dipilih. Reservations ikut dikirim supaya ApplyPaymentSheet bisa
    menampilkan baris alokasi tanpa fetch tambahan.
    """
    from .context import _build_reservation_context
    from ..finance import queries as fq
    invoices = list(queryset)
    paid_map = fq.invoice_paid_map([inv.pk for inv in invoices])
    out = []
    for inv in invoices:
        res_ctx = _build_reservation_context(inv)
        reservations = [{
            'id': r.get('id'),
            'number': r['number'],
            'hotel': r['hotel'],
            'total': r['total_int'],
            'paid': r['paid_int'],
            'remaining': r['remaining_int'],
        } for r in res_ctx]
        client_name = inv.client.name if inv.client else inv.customer_name or ''
        out.append({
            'id': inv.pk,
            'label': f'{inv.invoice_number} - {client_name}',
            'client_id': inv.client_id,
            'client_name': client_name,
            'remaining': inv.total_sar - paid_map.get(inv.pk, 0),
            'reservations': reservations,
        })
    return out


def _resolve_target_invoice(payment, data, request):
    """Deposit (pembayaran tanpa invoice): cari invoice tujuan alokasi.

    Mengembalikan Invoice target, atau None (pesan error sudah dipasang).
    TIDAK menyimpan apa pun -- pemanggil melekatkan invoice lewat
    _attach_invoice di dalam transaksi yang sama dengan alokasinya. Dulu
    invoice disimpan di sini, sebelum reservasi divalidasi: request yang
    kemudian ditolak meninggalkan deposit menempel permanen ke invoice itu.
    """
    if payment.invoice_id:
        return payment.invoice
    invoice_id = data.get('invoice_id')
    if not invoice_id:
        messages.error(
            request,
            'Pilih invoice tujuan untuk pembayaran deposit ini.',
        )
        return None
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except (Invoice.DoesNotExist, TypeError, ValueError):
        messages.error(request, 'Invoice tujuan tidak ditemukan.')
        return None
    if invoice.client_id != payment.client_id:
        messages.error(
            request,
            'Invoice tujuan bukan milik client pembayaran ini.',
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
# What the user filters and reads on the list: five meanings instead of nine
# technical statuses. `confirmed` only lives for one request (payment_confirm
# re-derives it straight away), `allocated` is the legacy twin of `applied`,
# and rejected/reversed/voided all read as "cancelled". Stored values are
# untouched -- this is a presentation layer over them.
PAYMENT_STATUS_GROUPS = (
    ('pending',     'Awaiting confirmation', 'yellow', (PaymentRecord.STATUS_PENDING,)),
    ('unallocated', 'Unallocated',           'blue',   (PaymentRecord.STATUS_RECEIVED, PaymentRecord.STATUS_CONFIRMED)),
    ('partial',     'Partially allocated',   'yellow', (PaymentRecord.STATUS_PARTIALLY_APPLIED,)),
    ('allocated',   'Allocated',             'green',  (PaymentRecord.STATUS_APPLIED, PaymentRecord.STATUS_ALLOCATED)),
    ('cancelled',   'Cancelled',             'gray',   (PaymentRecord.STATUS_REJECTED, PaymentRecord.STATUS_REVERSED, PaymentRecord.STATUS_VOIDED)),
)
_GROUP_STATUSES = {key: statuses for key, _, _, statuses in PAYMENT_STATUS_GROUPS}
_STATUS_GROUP = {st: (key, label, tone) for key, label, tone, statuses in PAYMENT_STATUS_GROUPS for st in statuses}


def _status_group_keys(values):
    """Normalise ?status= values to group keys, keeping order and dropping junk.

    A raw status (?status=applied from an older link) maps to its group.
    """
    out = []
    for v in values:
        if v in _GROUP_STATUSES:
            key = v
        elif v in _STATUS_GROUP:
            key = _STATUS_GROUP[v][0]
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
        qs = qs.filter(status__in=[st for key in f['status_list'] for st in _GROUP_STATUSES[key]])
    if f['date_from']:
        qs = qs.filter(payment_date__gte=f['date_from'])
    if f['date_to']:
        qs = qs.filter(payment_date__lte=f['date_to'])
    if f['client_id'].isdigit():
        qs = qs.filter(client_id=f['client_id'])
    if f['invoice_id'].isdigit():
        qs = qs.filter(invoice_id=f['invoice_id'])
    return qs.order_by(*_PAYMENT_SORT_MAP.get(f['sort'], _PAYMENT_SORT_MAP['-created_at']))


@require_perm('payments', 'view')
def payment_list(request):
    base_qs = PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by')
    f = _payment_filter_params(request)
    payments = _apply_payment_filters(base_qs, f)

    sort_labels = {
        '-created_at':   tr(request, 'Created (newest)', 'Dibuat (terbaru)'),
        '-payment_date': tr(request, 'Payment date (newest)', 'Tanggal bayar (terbaru)'),
        'payment_date':  tr(request, 'Payment date (oldest)', 'Tanggal bayar (terlama)'),
        '-amount_sar':   tr(request, 'Amount (largest)', 'Jumlah (terbesar)'),
    }
    sort = f['sort'] if f['sort'] in sort_labels else '-created_at'
    # Counts filter GROUPS in use (same rule as the CL list): several ticked
    # statuses are one group, a date range is one more.
    active_filters = bool(f['status_list']) + bool(f['date_from'] or f['date_to'])
    raw_counts = {
        row['status']: row['n']
        for row in PaymentRecord.objects.values('status').annotate(n=Count('id'))
    }
    status_groups = [
        {'key': key, 'label': label, 'count': sum(raw_counts.get(st, 0) for st in statuses)}
        for key, label, _, statuses in PAYMENT_STATUS_GROUPS
    ]

    # Server-side pagination (matches the other list pages: 10 on mobile, 15
    # otherwise). Filters above are honoured so filter + pagination stay consistent.
    paginator = Paginator(payments, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_payments = list(page_obj)

    # Everything below the table -- the Record Payment dialog's dropdowns and
    # the KPI row -- is passed as a callable. inertia-django only evaluates a
    # callable on a full visit; the filter bar's partial reloads (`only:` in
    # Payment/List.jsx) skip it. _invoice_choices alone costs ~300 queries
    # (reservation context per invoice), which used to run on every keystroke
    # of the search box.
    def invoice_choices():
        return _invoice_choices(
            Invoice.objects.filter(
                status__in=[Invoice.STATUS_DRAFT, Invoice.STATUS_SENT, Invoice.STATUS_PARTIAL],
            ).select_related('client').order_by('-created_at')[:50],
        )

    # Client choices for the record dialog — deposit (tanpa invoice) butuh
    # client eksplisit, dan client-first memendekkan daftar invoice.
    def client_choices():
        return [
            {'id': c.pk, 'name': c.name, 'city': c.city}
            for c in Client.objects.filter(is_active=True).order_by('name')
        ]

    def stats():
        from ..finance import queries as fq
        effective = PaymentRecord.objects.filter(status__in=PaymentRecord.EFFECTIVE_STATUSES)
        # One aggregate pair for the whole set instead of two queries per
        # payment -- the same bulk pattern as fq.invoice_paid_map.
        unapplied_map = fq.payment_unallocated_map(effective.values_list('pk', flat=True))
        # Counts come from raw_counts (one GROUP BY, shared with the filter
        # panel) instead of a COUNT query each.
        return {
            'total': sum(raw_counts.values()),
            # The group, not the raw status: legacy `allocated` + current `applied`.
            'allocated': sum(raw_counts.get(st, 0) for st in _GROUP_STATUSES['allocated']),
            'partially_applied': raw_counts.get(PaymentRecord.STATUS_PARTIALLY_APPLIED, 0),
            'unapplied_total': sum(unapplied_map.values()),
            'unapplied_count': sum(1 for v in unapplied_map.values() if v > 0),
        }

    return inertia_render(request, 'Payment/List', props={
        'payments': [_payment_props(p) for p in page_payments],
        'invoice_choices': invoice_choices,
        'client_choices': client_choices,
        'account_choices': money_account_choices,
        'stats': stats,
        'q': f['q'],
        'status_list': f['status_list'],
        'date_from': f['date_from'].isoformat() if f['date_from'] else '',
        'date_to': f['date_to'].isoformat() if f['date_to'] else '',
        'sort': sort,
        'sort_label': sort_labels[sort],
        'sort_labels': sort_labels,
        'active_filters': active_filters,
        'status_groups': status_groups,
        'total_count': paginator.count,
        'pagination': pagination_props(page_obj),
    })


@require_perm('payments', 'view')
def payment_detail(request, pk):
    payment = get_object_or_404(
        PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by', 'period'),
        pk=pk,
    )
    logs = payment.logs.select_related('performed_by').order_by('-performed_at')

    # Get related journal entries
    journal_entries = JournalEntry.objects.filter(
        reference_type='PaymentRecord',
        reference_id=payment.pk,
    ).order_by('-entry_date')

    # Reservations for post-hoc allocation (unallocated payment). Filter to the
    # payment's own invoice only, so a user can't allocate a payment to a
    # reservation on another invoice.
    from .context import _build_reservation_context
    reservations = []
    invoice_choices = []
    if payment.invoice_id:
        reservations = _build_reservation_context(payment.invoice)
    else:
        # Deposit (tanpa invoice): tawarkan invoice milik client ini sebagai
        # target distribusi nanti — tersaring ke draft/sent/partial supaya
        # daftarnya pendek dan hanya invoice yang masih punya saldo.
        invoice_choices = _invoice_choices(
            Invoice.objects.filter(
                client=payment.client,
                status__in=[Invoice.STATUS_DRAFT, Invoice.STATUS_SENT, Invoice.STATUS_PARTIAL],
            ).select_related('client').order_by('-created_at'),
        )

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
        'invoice_choices': invoice_choices,
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
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        client = invoice.client
        if not client:
            cl = invoice.confirmation_letters.first()
            client = cl.client if cl and cl.client else None
        if not client:
            messages.error(request, 'Invoice tidak memiliki client yang valid.')
            return redirect('payment_list')
    else:
        # Deposit: invoice opsional — client wajib dipilih eksplisit.
        client_id = data.get('client_id')
        if not client_id:
            messages.error(request, 'Pilih client untuk pembayaran tanpa invoice (deposit).')
            return redirect('payment_list')
        client = get_object_or_404(Client, pk=client_id)
    amount = _to_float(data.get('amount'))
    exchange_rate = _to_float(data.get('exchange_rate'), 1) or 1
    currency = (data.get('currency') or 'SAR').upper()

    # Receiving account (v2.0 FASE C): a concrete BankAccount/CashAccount
    # picked in the UI. received_in stays the routing fallback — derived
    # from the account's branch when one is chosen, or the raw field for
    # older callers/tests that still send received_in directly.
    bank_account, cash_account = resolve_money_account(data.get('account'))
    receiving_account = bank_account or cash_account
    if receiving_account is not None:
        received_in = receiving_account.branch_id
    else:
        received_in = data.get('received_in', 'sby')
        if received_in not in ('sby', 'jkt', 'pusat'):
            received_in = 'sby'

    # amount/amount_sar are PositiveIntegerField. A negative value passes a
    # bare truthiness check, survives convert_to_sar, and only fails at the
    # database CHECK constraint -- an IntegrityError the FinanceError handler
    # below does not catch, so the user gets a 500 instead of a form message.
    # A non-positive rate does the same by flipping a positive amount.
    if not amount or amount <= 0:
        messages.error(request, 'Jumlah pembayaran harus lebih besar dari nol.')
        return redirect('payment_list')
    if exchange_rate <= 0:
        messages.error(request, 'Kurs harus lebih besar dari nol.')
        return redirect('payment_list')
    if currency not in CURRENCIES:
        messages.error(request, f'Mata uang tidak dikenal: {currency}.')
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
        messages.error(request, 'Bukti pembayaran wajib dilampirkan.')
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
            'Deposit (tanpa invoice) tidak bisa langsung dialokasikan. '
            'Pilih invoice tujuan saat distribusi nanti.',
        )
        return redirect('payment_list')

    from ..models import Reservation
    from django.utils import timezone as tz
    from ..finance import posting

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
            messages.error(request, 'Tidak ada alokasi yang valid.')
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
                pk=alloc.get('reservation_id'), invoice=invoice,
            ).first()
            if reservation is None:
                unknown.append(str(alloc.get('reservation_id')))
                continue
            targets.append((reservation, int(_to_float(alloc.get('amount', 0)))))
        if unknown:
            messages.error(
                request,
                'Reservasi berikut bukan milik invoice ini: '
                f'{", ".join(unknown)}.',
            )
            return redirect('payment_list')
        if not targets:
            messages.error(request, 'Tidak ada alokasi yang valid.')
            return redirect('payment_list')

        # Nilai SAR pembayaran (riyal patokan), untuk memvalidasi total alokasi
        # SEBELUM record dibuat -- jangan sisakan PaymentRecord yatim bila over.
        from ..utils import convert_to_sar
        sar_amount = int(round(convert_to_sar(amount, currency, exchange_rate)))
        if sum(a for _, a in targets) > sar_amount:
            messages.error(
                request,
                f'Total alokasi melebihi nilai SAR pembayaran ({sar_amount:,}).',
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
                    bank_name=data.get('bank_name', ''),
                    account_number=data.get('account_number', ''),
                    reference=data.get('reference', ''),
                    note=data.get('note', '') or f'Allocated to {len(valid_alloc)} reservation(s)',
                    created_by=request.user,
                    received_in=received_in,
                    bank_account=bank_account,
                    cash_account=cash_account,
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
            'Payment berhasil dibuat dan dialokasikan. Menunggu konfirmasi finance/admin.',
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
                    bank_name=data.get('bank_name', ''),
                    account_number=data.get('account_number', ''),
                    reference=data.get('reference', ''),
                    note=data.get('note', ''),
                    created_by=request.user,
                    received_in=received_in,
                    bank_account=bank_account,
                    cash_account=cash_account,
                )
                if proof_file:
                    payment.proof = proof_file
                    payment.save(update_fields=['proof'])
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('payment_list')

        messages.success(
            request,
            f'Payment {payment.payment_number} berhasil dibuat. Menunggu konfirmasi finance/admin.',
        )
        return redirect('payment_detail', pk=payment.pk)


@require_perm('payments', 'edit')
def payment_confirm(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
        try:
            note = ''
            if request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                    note = data.get('note', '')
                except (json.JSONDecodeError, ValueError):
                    pass

            confirm_payment(payment, confirmed_by=request.user, note=note)

            # Derive final status from the allocation sum vs amount — fully
            # allocated → applied, sebagian → partially_applied, tanpa alokasi
            # → received.
            old_state = _payment_snapshot(payment)
            payment.status = payment.derive_status()
            payment.save(update_fields=['status'])
            if payment.status != PaymentRecord.STATUS_CONFIRMED:
                PaymentLog.objects.create(
                    payment=payment,
                    action=(
                        PaymentLog.ACTION_APPLIED
                        if payment.status in (PaymentRecord.STATUS_APPLIED,
                                              PaymentRecord.STATUS_PARTIALLY_APPLIED)
                        else PaymentLog.ACTION_RECEIVED
                    ),
                    before_state=old_state,
                    after_state=_payment_snapshot(payment),
                    performed_by=request.user,
                    note='Status derived from allocations after confirm',
                )
            if payment.invoice_id:
                payment.invoice.sync_status()

            # Auto-generate the payment receipt (kwitansi) on confirmation.
            from ..finance.receipt_service import ensure_receipt
            ensure_receipt(payment, created_by=request.user)

            messages.success(request, f'Payment {payment.payment_number} berhasil dikonfirmasi.')
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_reject(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
        # Only a PENDING payment may be rejected. A confirmed/allocated payment
        # has already touched the ledger (DR Kas / CR Piutang); flipping it to
        # REJECTED without reversing its journal entry would desync the ledger
        # from the payment record. Rejection on effective payments must go
        # through payment_reverse.
        if payment.status not in (PaymentRecord.STATUS_PENDING,):
            messages.error(
                request,
                f'Payment {payment.payment_number} berstatus '
                f'{payment.get_status_display()}. Hanya payment pending yang bisa '
                'ditolak. Gunakan "Revers sebagai koreksi untuk pembayaran efektif.',
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
                messages.error(request, f'Payment {payment.payment_number} sudah diproses.')
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
        messages.success(request, f'Payment {payment.payment_number} ditolak.')
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_reallocate(request, pk):
    """Reallokasi alokasi payment yang sudah efektif (confirmed/allocated).

    Body (JSON or form): allocations = [{"reservation_id": 1, "amount": 5000}, ...]
    Sisa yang tidak dialokasikan tetap mengambang (unallocated).
    """
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        messages.error(
            request,
            f'Payment {payment.payment_number} berstatus '
            f'{payment.get_status_display()}. Hanya payment efektif yang bisa '
            'direalokasi.',
        )
        return redirect('payment_detail', pk=pk)

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
    else:
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        except (json.JSONDecodeError, ValueError):
            data = request.POST

    raw = data.get('allocations', '')
    try:
        allocations = json.loads(raw) if isinstance(raw, str) else raw or []
    except (json.JSONDecodeError, ValueError):
        allocations = []

    from ..models import Reservation
    from ..finance import posting

    # Deposit (tanpa invoice): lekatkan dulu ke invoice tujuan.
    target_invoice = _resolve_target_invoice(payment, data, request)
    if target_invoice is None:
        return redirect('payment_detail', pk=pk)

    # See payment_record: a mismatched reservation is refused, not dropped.
    targets = []
    unknown = []
    for alloc in allocations:
        amt = _to_float(alloc.get('amount', 0))
        if not amt or amt <= 0:
            continue
        reservation = Reservation.objects.filter(
            pk=alloc.get('reservation_id'), invoice=target_invoice,
        ).first()
        if reservation is None:
            unknown.append(str(alloc.get('reservation_id')))
            continue
        targets.append((reservation, int(_to_float(alloc.get('amount', 0)))))
    if unknown:
        messages.error(
            request,
            f'Reservasi berikut bukan milik invoice payment ini: {", ".join(unknown)}.',
        )
        return redirect('payment_detail', pk=pk)

    from django.db import transaction
    try:
        with transaction.atomic():
            _attach_invoice(payment, target_invoice)
            posting.reallocate_payment(payment, targets, created_by=request.user)
        messages.success(
            request,
            f'Payment {payment.payment_number} berhasil direalokasi.',
        )
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


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
                f'Payment {payment.payment_number} sudah {payment.get_status_display()}.'
            )
        old_state = _payment_snapshot(payment)
        reversed_ids = JournalEntry.objects.filter(
            reverses__isnull=False,
        ).values_list('reverses_id', flat=True)
        journals = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            entry_type__in=[JournalEntry.TYPE_PAYMENT], is_reversal=False,
        ).exclude(pk__in=reversed_ids)
        for journal in journals:
            reverse_journal_entry(journal, reversal_date, user, note=journal_note)

        payment.status = status
        payment.save(update_fields=['status'])
        void_bank_transactions('PaymentRecord', payment.pk)
        void_receipts_for_payment(
            payment, reason=f'Payment {payment.payment_number} {status}',
        )
        dropped = posting.clear_payment_allocations(payment)

        if payment.invoice_id:
            payment.invoice.sync_status()

        PaymentLog.objects.create(
            payment=payment,
            action=action,
            before_state={**old_state, 'allocations': dropped},
            after_state=_payment_snapshot(payment),
            performed_by=user,
            note=f'Payment {status}',
        )


@require_perm('payments', 'edit')
def payment_reverse(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
        # Pending money was never received: there is no journal to reverse,
        # so it must go through Reject instead.
        if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
            messages.error(
                request,
                f'Payment {payment.payment_number} berstatus '
                f'{payment.get_status_display()} dan tidak bisa di-reverse.',
            )
            return redirect('payment_detail', pk=pk)

        try:
            _retire_payment(
                payment, status=PaymentRecord.STATUS_REVERSED,
                action=PaymentLog.ACTION_REVERSED,
                reversal_date=timezone.now().date(),
                journal_note=f'Reversal for {payment.payment_number}',
                user=request.user,
            )
            messages.success(request, f'Payment {payment.payment_number} di-reverse.')
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_apply(request, pk):
    """Apply / allocate an existing payment to reservations.

    POST only. Accepts ``allocations`` JSON: ``[{"reservation_id": N, "amount": M}]``.

    Validates:
    - payment is in an effective (journal-posted) status — any of
      received / confirmed / allocated / partially_applied / applied
    - reservations belong to the payment's invoice
    - total allocations <= payment amount_sar

    Then reverses the old journal, replaces allocations, and reposts with
    new reservation dims via ``reallocate_payment``.
    """
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    payment = get_object_or_404(PaymentRecord, pk=pk)

    # Any effective status can be (re-)applied — matches reallocate_payment,
    # so a legacy confirmed/allocated payment (which the UI lets the user
    # re-apply) is accepted here instead of being silently refused.
    if payment.status not in PaymentRecord.EFFECTIVE_STATUSES:
        messages.error(
            request,
            f'Payment {payment.payment_number} berstatus '
            f'{payment.get_status_display()} dan tidak bisa dialokasi.',
        )
        return redirect('payment_detail', pk=pk)

    # Parse body — Inertia/axios sends JSON (request.POST is then empty), so
    # fall back to request.body when POST carries no allocations. This covers
    # multipart (proof uploads), urlencoded (tests/curl), and JSON regardless
    # of charset parameters. On a multipart POST request.POST has already
    # consumed the stream, so request.body raises RawPostDataException -- an
    # Exception, not a ValueError, so it escapes an except that lists only
    # ValueError and turns a missing-allocations request into a 500.
    data = request.POST
    if not data.get('allocations'):
        try:
            body = json.loads(request.body) if request.body else None
            if isinstance(body, dict):
                data = body
        except (json.JSONDecodeError, ValueError, RawPostDataException):
            pass

    raw = data.get('allocations', '')
    if not raw:
        messages.error(request, 'Alokasi tidak boleh kosong.')
        return redirect('payment_detail', pk=pk)
    try:
        allocs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, ValueError):
        messages.error(request, 'Format alokasi tidak valid.')
        return redirect('payment_detail', pk=pk)

    valid_allocs = [
        a for a in allocs
        if _to_float(a.get('amount', 0)) and _to_float(a.get('amount', 0)) > 0
    ]
    if not valid_allocs:
        messages.error(request, 'Tidak ada alokasi yang valid.')
        return redirect('payment_detail', pk=pk)

    total_alloc = sum(int(_to_float(a['amount'])) for a in valid_allocs)
    if total_alloc > payment.amount_sar:
        messages.error(
            request,
            f'Total alokasi ({total_alloc:,}) melebihi jumlah pembayaran '
            f'({payment.amount_sar:,}).',
        )
        return redirect('payment_detail', pk=pk)

    # Resolve Reservation objects — must belong to the same invoice.
    from ..models import Reservation
    # Deposit (tanpa invoice): lekatkan dulu ke invoice tujuan sebelum
    # alokasi, supaya reservasi difilter terhadap invoice yang benar.
    target_invoice = _resolve_target_invoice(payment, data, request)
    if target_invoice is None:
        return redirect('payment_detail', pk=pk)
    # See payment_record: total_alloc above was validated against the
    # unfiltered list, so silently dropping a row here would leave the
    # difference floating with no warning.
    targets = []
    unknown = []
    for a in valid_allocs:
        res = Reservation.objects.filter(
            pk=a.get('reservation_id'), invoice=target_invoice,
        ).first()
        if res is None:
            unknown.append(str(a.get('reservation_id')))
            continue
        targets.append((res, int(_to_float(a['amount']))))

    if unknown:
        messages.error(
            request,
            f'Reservasi berikut bukan milik invoice payment ini: {", ".join(unknown)}.',
        )
        return redirect('payment_detail', pk=pk)

    if not targets:
        messages.error(request, 'Tidak ada reservasi yang valid untuk alokasi ini.')
        return redirect('payment_detail', pk=pk)

    from django.db import transaction
    try:
        old_state = _payment_snapshot(payment)
        with transaction.atomic():
            _attach_invoice(payment, target_invoice)
            posting.reallocate_payment(
                payment, targets, created_by=request.user,
            )

            # Derive and save new status.
            payment.status = payment.derive_status()
            payment.save(update_fields=['status'])

        PaymentLog.objects.create(
            payment=payment,
            action=PaymentLog.ACTION_APPLIED,
            before_state=old_state,
            after_state=_payment_snapshot(payment),
            performed_by=request.user,
            note=f'Applied to {len(targets)} reservation(s)',
        )

        if payment.invoice_id:
            payment.invoice.sync_status()

    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_void(request, pk):
    """Void a payment — posts a reversal journal entry and marks status voided.

    Only effective payments (received / partially_applied / applied / confirmed
    / allocated) may be voided. Pending payments should use reject instead.
    """
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    payment = get_object_or_404(PaymentRecord, pk=pk)

    voidable = PaymentRecord.EFFECTIVE_STATUSES
    if payment.status not in voidable:
        messages.error(
            request,
            f'Payment {payment.payment_number} berstatus '
            f'{payment.get_status_display()} dan tidak bisa di-void.',
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
        messages.success(request, f'Payment {payment.payment_number} di-void.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'export')
def payment_export_csv(request):
    """Export payments as CSV."""
    # Same filters as payment_list: exporting from a filtered list must not
    # hand back every payment in the system.
    payments = _apply_payment_filters(
        PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by'),
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
    return csv_export_response(f'payments-{date.today().isoformat()}.csv', headers, rows)
