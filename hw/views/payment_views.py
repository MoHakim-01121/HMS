"""Payment views — list, detail, record, confirm, reject."""
import json
import logging

from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from inertia import render as inertia_render

from ..models.payment import PaymentRecord, PaymentLog
from ..models.invoice import Invoice
from ..models.journal import JournalEntry
from ..finance_helpers import (
    create_payment_record, confirm_payment, allocate_payment,
    reverse_journal_entry, _payment_snapshot,
    FinanceError,
)
from ..permissions import require_perm
from ..finance import posting
from .helpers import (
    serialize_journal_entry, _parse_date, _to_float, _is_mobile,
    pagination_props, csv_export_response, money_account_choices, resolve_money_account,
)

logger = logging.getLogger(__name__)


def _payment_props(p):
    from django.conf import settings
    proof_url = p.proof.url if p.proof else None
    from ..finance import queries as fq
    unallocated = fq.payment_unallocated_sar(p.pk)
    return {
        'id': p.pk,
        'payment_number': p.payment_number,
        'invoice_id': p.invoice_id,
        'invoice_number': p.invoice.invoice_number if p.invoice else None,
        'client_id': p.client_id,
        'client_name': p.client.name if p.client else None,
        'reservation_id': p.reservation_id,
        'service_item_id': p.service_item_id,
        'allocations': [{
            'id': a.pk,
            'reservation_id': a.reservation_id,
            'reservation_number': a.reservation.reservation_number if a.reservation else None,
            'service_item_id': a.service_item_id,
            'amount_sar': a.amount_sar,
        } for a in p.allocations.select_related('reservation', 'service_item')],
        'unallocated_sar': unallocated,
        'allocated_sar': p.amount_sar - unallocated,
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
        'status': p.status,
        'status_display': p.get_status_display(),
        'confirmed_by': p.confirmed_by.username if p.confirmed_by else None,
        'confirmed_at': p.confirmed_at.isoformat() if p.confirmed_at else None,
        'rejected_reason': p.rejected_reason,
        'created_by': p.created_by.username if p.created_by else None,
        'created_at': p.created_at.isoformat(),
    }


@require_perm('payments', 'view')
def payment_list(request):
    payments = PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by')

    # Filter by status
    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)

    # Filter by client
    client_id = request.GET.get('client')
    if client_id:
        payments = payments.filter(client_id=client_id)

    # Filter by invoice
    invoice_id = request.GET.get('invoice')
    if invoice_id:
        payments = payments.filter(invoice_id=invoice_id)

    payments = payments.order_by('-created_at')

    # Server-side pagination (matches the other list pages: 10 on mobile, 15
    # otherwise). The `status` filter above is honoured so a filter + pagination
    # combination stays consistent.
    paginator = Paginator(payments, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_payments = list(page_obj)

    # Invoice choices for the record dialog — include per-reservation breakdown.
    invoices = Invoice.objects.filter(
        status__in=[Invoice.STATUS_DRAFT, Invoice.STATUS_SENT, Invoice.STATUS_PARTIAL],
    ).select_related('client').order_by('-created_at')[:50]
    from ..finance import queries as fq
    paid_map = fq.invoice_paid_map([inv.pk for inv in invoices])
    invoice_choices = []
    for inv in invoices:
        # Fetch reservations via linked CLs
        from .context import _build_reservation_context
        res_ctx = _build_reservation_context(inv)
        reservations = [{
            'id': r.get('id'),
            'number': r['number'],
            'hotel': r['hotel'],
            'total': r['total_int'],
            'paid': r['paid_int'],
            'remaining': r['remaining_int'],
        } for r in res_ctx]
        invoice_choices.append({
            'id': inv.pk,
            'label': f'{inv.invoice_number} - {inv.client.name if inv.client else inv.customer_name}',
            'remaining': inv.total_sar - paid_map.get(inv.pk, 0),
            'reservations': reservations,
        })

    # Summary stats
    all_payments = PaymentRecord.objects.all()
    stat_effective = all_payments.filter(status__in=PaymentRecord.EFFECTIVE_STATUSES)
    unapplied_rows = [fq.payment_unallocated_sar(p.pk) for p in stat_effective]
    unapplied_total = sum(unapplied_rows)
    stats = {
        'total': all_payments.count(),
        'pending': all_payments.filter(status=PaymentRecord.STATUS_PENDING).count(),
        'confirmed': all_payments.filter(status=PaymentRecord.STATUS_CONFIRMED).count(),
        'allocated': all_payments.filter(status=PaymentRecord.STATUS_ALLOCATED).count(),
        'received': all_payments.filter(status=PaymentRecord.STATUS_RECEIVED).count(),
        'partially_applied': all_payments.filter(status=PaymentRecord.STATUS_PARTIALLY_APPLIED).count(),
        'applied': all_payments.filter(status=PaymentRecord.STATUS_APPLIED).count(),
        'total_amount': sum(p.amount_sar for p in stat_effective),
        'unapplied_total': unapplied_total,
        'unapplied_count': sum(1 for v in unapplied_rows if v > 0),
    }

    return inertia_render(request, 'Payment/List', props={
        'payments': [_payment_props(p) for p in page_payments],
        'status_choices': PaymentRecord.STATUS_CHOICES,
        'invoice_choices': invoice_choices,
        'account_choices': money_account_choices(),
        'stats': stats,
        'status_filter': status or 'all',
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
    if payment.invoice_id:
        reservations = _build_reservation_context(payment.invoice)

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
def payment_record_new(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        except (json.JSONDecodeError, ValueError):
            data = request.POST

        payment_date = _parse_date(data.get('payment_date'))
        amount = _to_float(data.get('amount'))
        exchange_rate = _to_float(data.get('exchange_rate'), 1) or 1
        currency = (data.get('currency') or 'SAR').upper()

        if not amount:
            messages.error(request, 'Jumlah pembayaran harus diisi.')
            return redirect('invoice_detail', pk=invoice.pk)

        client = invoice.client or invoice.confirmation_letters.first()
        client = client.client if client and hasattr(client, 'client') else None
        if not client:
            messages.error(request, 'Invoice tidak memiliki client yang valid.')
            return redirect('invoice_detail', pk=invoice.pk)

        payment = create_payment_record(
            invoice=invoice,
            client=client,
            payment_date=payment_date or invoice.issued_date,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            method=data.get('method', ''),
            bank_name=data.get('bank_name', ''),
            account_number=data.get('account_number', ''),
            reference=data.get('reference', ''),
            note=data.get('note', ''),
            created_by=request.user,
        )
        messages.success(request, f'Payment {payment.payment_number} berhasil dibuat.')
        return redirect('payment_detail', pk=payment.pk)

    return redirect('invoice_detail', pk=invoice.pk)


@require_perm('payments', 'create')
def payment_record(request):
    """Record a new payment from the Payment List page.
    
    Supports per-reservation allocation via `allocations` JSON field:
    [{"reservation_id": 1, "amount": 5000}, {"reservation_id": 2, "amount": 3000}]
    
    Each allocation creates a separate PaymentRecord, auto-confirmed and allocated.
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
    if not invoice_id:
        messages.error(request, 'Invoice harus dipilih.')
        return redirect('payment_list')

    invoice = get_object_or_404(Invoice, pk=invoice_id)
    payment_date = _parse_date(data.get('payment_date'))
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

    if not amount:
        messages.error(request, 'Jumlah pembayaran harus diisi.')
        return redirect('payment_list')

    client = invoice.client
    if not client:
        cl = invoice.confirmation_letters.first()
        client = cl.client if cl and cl.client else None
    if not client:
        messages.error(request, 'Invoice tidak memiliki client yang valid.')
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
        targets = []
        for alloc in valid_alloc:
            reservation = Reservation.objects.filter(
                pk=alloc.get('reservation_id'), invoice=invoice,
            ).first()
            if reservation is None:
                continue
            targets.append((reservation, int(_to_float(alloc.get('amount', 0)))))
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

                posting.allocate_payment(payment, targets, created_by=request.user)

                # Auto-post journal immediately — no manual confirm step.
                posting.post_payment(payment, created_by=request.user)

                # Derive status from allocation sum vs amount.
                old_state = _payment_snapshot(payment)
                payment.status = payment.derive_status()
                payment.confirmed_by = request.user
                payment.confirmed_at = tz.now()
                payment.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])

                from ..finance.receipt_service import ensure_receipt
                ensure_receipt(payment, created_by=request.user)

                PaymentLog.objects.create(
                    payment=payment,
                    action=PaymentLog.ACTION_RECEIVED,
                    before_state=old_state,
                    after_state=_payment_snapshot(payment),
                    performed_by=request.user,
                    note='Payment received and journal posted',
                )
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('payment_list')

        messages.success(request, 'Payment berhasil dibuat dan dialokasikan.')
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

                # Auto-post journal immediately — unallocated.
                posting.post_payment(payment, created_by=request.user)

                old_state = _payment_snapshot(payment)
                payment.status = PaymentRecord.STATUS_RECEIVED
                payment.confirmed_by = request.user
                payment.confirmed_at = tz.now()
                payment.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])

                from ..finance.receipt_service import ensure_receipt
                ensure_receipt(payment, created_by=request.user)

                PaymentLog.objects.create(
                    payment=payment,
                    action=PaymentLog.ACTION_RECEIVED,
                    before_state=old_state,
                    after_state=_payment_snapshot(payment),
                    performed_by=request.user,
                    note='Payment received and journal posted (unallocated)',
                )
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('payment_list')

        messages.success(request, f'Payment {payment.payment_number} berhasil dibuat.')
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
            allocate_payment(payment, allocation_date=payment.payment_date, created_by=request.user)

            # Auto-generate the payment receipt (kwitansi) on confirmation.
            from ..finance.receipt_service import ensure_receipt
            receipt = ensure_receipt(payment, created_by=request.user)
            if receipt is None:
                logger.warning("Receipt tidak dibuat utk payment %s: data kurang (invoice/client).", payment.payment_number)

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
        payment.status = PaymentRecord.STATUS_REJECTED
        payment.rejected_reason = reason
        payment.save(update_fields=['status', 'rejected_reason'])

        PaymentLog.objects.create(
            payment=payment,
            action=PaymentLog.ACTION_REJECTED,
            before_state=old_state,
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

    targets = []
    for alloc in allocations:
        amt = _to_float(alloc.get('amount', 0))
        if not amt or amt <= 0:
            continue
        reservation = Reservation.objects.filter(
            pk=alloc.get('reservation_id'), invoice=payment.invoice,
        ).first()
        if reservation is None:
            continue
        targets.append((reservation, int(_to_float(alloc.get('amount', 0)))))

    try:
        posting.reallocate_payment(payment, targets, created_by=request.user)
        messages.success(
            request,
            f'Payment {payment.payment_number} berhasil direalokasi.',
        )
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'edit')
def payment_reverse(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
        try:
            # Resilai habis: sebuah payment efektif (confirmed/allocated) yang
            # masih punya journal entry hidup harus di-reverse dulu jurnalnya,
            # baru status payment-nya di-flip ke REVERSED.
            if payment.status not in PaymentRecord.EFFECTIVE_STATUSES + (PaymentRecord.STATUS_PENDING,):
                messages.error(
                    request,
                    f'Payment {payment.payment_number} berstatus '
                    f'{payment.get_status_display()} dan tidak bisa di-reverse.',
                )
                return redirect('payment_detail', pk=pk)
            reversed_ids = JournalEntry.objects.filter(
                reverses__isnull=False,
            ).values_list('reverses_id', flat=True)
            journals = JournalEntry.objects.filter(
                reference_type='PaymentRecord', reference_id=payment.pk,
                entry_type__in=[JournalEntry.TYPE_PAYMENT], is_reversal=False,
            ).exclude(pk__in=reversed_ids)

            for journal in journals:
                reverse_journal_entry(
                    journal, timezone.now().date(), request.user,
                    note=f'Reversal for {payment.payment_number}',
                )

            if payment.invoice_id:
                payment.invoice.sync_status()

            PaymentLog.objects.create(
                payment=payment,
                action=PaymentLog.ACTION_REVERSED,
                performed_by=request.user,
                note='Payment reversed',
            )
            payment.status = PaymentRecord.STATUS_REVERSED
            payment.save(update_fields=['status'])

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
    - payment is in an allocatable status (received or partially_applied)
    - reservations belong to the payment's invoice
    - total allocations <= payment amount_sar

    Then reverses the old journal, replaces allocations, and reposts with
    new reservation dims via ``reallocate_payment``.
    """
    if request.method != 'POST':
        return redirect('payment_detail', pk=pk)

    payment = get_object_or_404(PaymentRecord, pk=pk)

    # Only received / partially_applied payments can be (re-)applied.
    allocatable = (
        PaymentRecord.STATUS_RECEIVED,
        PaymentRecord.STATUS_PARTIALLY_APPLIED,
        # Also allow re-apply on already-applied (change the split).
        PaymentRecord.STATUS_APPLIED,
    )
    if payment.status not in allocatable:
        messages.error(
            request,
            f'Payment {payment.payment_number} berstatus '
            f'{payment.get_status_display()} dan tidak bisa dialokasi.',
        )
        return redirect('payment_detail', pk=pk)

    # Parse allocations JSON
    raw = request.POST.get('allocations', '')
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
    targets = []
    for a in valid_allocs:
        res = Reservation.objects.filter(
            pk=a.get('reservation_id'), invoice=payment.invoice,
        ).first()
        if res is None:
            continue
        targets.append((res, int(_to_float(a['amount']))))

    if not targets:
        messages.error(request, 'Tidak ada reservasi yang valid untuk alokasi ini.')
        return redirect('payment_detail', pk=pk)

    try:
        posting.reallocate_payment(
            payment, targets, created_by=request.user,
        )

        # Derive and save new status.
        old_state = _payment_snapshot(payment)
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
        reversed_ids = JournalEntry.objects.filter(
            reverses__isnull=False,
        ).values_list('reverses_id', flat=True)
        journals = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            entry_type__in=[JournalEntry.TYPE_PAYMENT], is_reversal=False,
        ).exclude(pk__in=reversed_ids)

        for journal in journals:
            reverse_journal_entry(
                journal, payment.payment_date, request.user,
                note=f'Voided: {payment.payment_number}',
            )

        if payment.invoice_id:
            payment.invoice.sync_status()

        old_state = _payment_snapshot(payment)
        payment.status = PaymentRecord.STATUS_VOIDED
        payment.save(update_fields=['status'])

        PaymentLog.objects.create(
            payment=payment,
            action=PaymentLog.ACTION_VOIDED,
            before_state=old_state,
            after_state=_payment_snapshot(payment),
            performed_by=request.user,
            note='Payment voided',
        )

        messages.success(request, f'Payment {payment.payment_number} di-void.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('payment_detail', pk=pk)


@require_perm('payments', 'export')
def payment_export_csv(request):
    """Export payments as CSV."""
    payments = PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by').order_by('-created_at')

    # Apply filters
    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)

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
