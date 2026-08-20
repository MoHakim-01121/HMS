"""Payment views — list, detail, record, confirm, reject."""
import json
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models.payment import PaymentRecord, PaymentLog
from ..models.invoice import Invoice
from ..models.journal import JournalEntry
from ..finance_helpers import (
    create_payment_record, confirm_payment, allocate_payment,
    reverse_journal_entry, FinanceError,
)
from ..permissions import require_perm
from .helpers import get_active_company, _parse_date, _to_float

logger = logging.getLogger(__name__)


def _payment_props(p):
    return {
        'id': p.pk,
        'payment_number': p.payment_number,
        'invoice_id': p.invoice_id,
        'invoice_number': p.invoice.invoice_number if p.invoice else None,
        'client_id': p.client_id,
        'client_name': p.client.name if p.client else None,
        'reservation_id': p.reservation_id,
        'service_item_id': p.service_item_id,
        'payment_date': p.payment_date.isoformat() if p.payment_date else None,
        'amount': p.amount,
        'currency': p.currency,
        'exchange_rate': float(p.exchange_rate),
        'amount_sar': p.amount_sar,
        'method': p.method,
        'bank_name': p.bank_name,
        'account_number': p.account_number,
        'reference': p.reference,
        'note': p.note,
        'status': p.status,
        'status_display': p.get_status_display(),
        'confirmed_by': p.confirmed_by.username if p.confirmed_by else None,
        'confirmed_at': p.confirmed_at.isoformat() if p.confirmed_at else None,
        'rejected_reason': p.rejected_reason,
        'company': p.company,
        'created_by': p.created_by.username if p.created_by else None,
        'created_at': p.created_at.isoformat(),
    }


@require_perm('invoice', 'view')
def payment_list(request):
    company = get_active_company(request)
    payments = PaymentRecord.objects.select_related('client', 'invoice', 'confirmed_by')

    # Filter by status
    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)

    # Filter by client
    client_id = request.GET.get('client')
    if client_id:
        payments = payments.filter(client_id=client_id)

    payments = payments.order_by('-created_at')

    return inertia_render(request, 'Payment/List', props={
        'payments': [_payment_props(p) for p in payments[:100]],
        'status_choices': PaymentRecord.STATUS_CHOICES,
    })


@require_perm('invoice', 'view')
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

    return inertia_render(request, 'Payment/Detail', props={
        'payment': _payment_props(payment),
        'logs': [{
            'action': l.action,
            'action_display': l.get_action_display(),
            'before_state': l.before_state,
            'after_state': l.after_state,
            'performed_by': l.performed_by.username if l.performed_by else None,
            'performed_at': l.performed_at.isoformat(),
            'note': l.note,
        } for l in logs],
        'journal_entries': [{
            'id': e.pk,
            'entry_number': e.entry_number,
            'entry_type': e.entry_type,
            'entry_type_display': e.get_entry_type_display(),
            'description': e.description,
            'entry_date': e.entry_date.isoformat(),
            'total_debit': e.total_debit,
            'total_credit': e.total_credit,
        } for e in journal_entries],
    })


@require_perm('invoice', 'edit')
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


@require_perm('invoice', 'edit')
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
            messages.success(request, f'Payment {payment.payment_number} berhasil dikonfirmasi.')
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)


@require_perm('invoice', 'edit')
def payment_reject(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
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


@require_perm('invoice', 'edit')
def payment_reverse(request, pk):
    payment = get_object_or_404(PaymentRecord, pk=pk)
    if request.method == 'POST':
        try:
            from django.utils import timezone
            # Find related journal entry
            journal = JournalEntry.objects.filter(
                reference_type='PaymentRecord',
                reference_id=payment.pk,
            ).first()

            if journal:
                reversal = reverse_journal_entry(
                    journal, timezone.now().date(), request.user,
                    note=f'Reversal for {payment.payment_number}',
                )
                # Reverse allocation
                if payment.invoice and payment.amount_sar:
                    payment.invoice.paid_sar = max(0, payment.invoice.paid_sar - payment.amount_sar)
                    payment.invoice.save(update_fields=['paid_sar'])

            payment.status = PaymentRecord.STATUS_REVERSED
            payment.save(update_fields=['status'])

            PaymentLog.objects.create(
                payment=payment,
                action=PaymentLog.ACTION_REVERSED,
                performed_by=request.user,
                note='Payment reversed',
            )
            messages.success(request, f'Payment {payment.payment_number} di-reverse.')
        except FinanceError as e:
            messages.error(request, str(e))
        return redirect('payment_detail', pk=pk)
    return redirect('payment_detail', pk=pk)
