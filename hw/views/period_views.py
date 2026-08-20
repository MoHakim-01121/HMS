"""Period management views — list, detail, close, lock."""
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models.period import FinancialPeriod
from ..permissions import require_perm
from .helpers import get_active_company

logger = logging.getLogger(__name__)


def _period_props(p):
    return {
        'id': p.pk,
        'name': p.name,
        'date_from': p.date_from.isoformat(),
        'date_to': p.date_to.isoformat(),
        'status': p.status,
        'status_display': p.get_status_display(),
        'is_editable': p.is_editable,
        'is_postable': p.is_postable,
        'closed_by': p.closed_by.username if p.closed_by else None,
        'closed_at': p.closed_at.isoformat() if p.closed_at else None,
        'locked_by': p.locked_by.username if p.locked_by else None,
        'locked_at': p.locked_at.isoformat() if p.locked_at else None,
        'journal_count': p.journal_entries.count(),
        'payment_count': p.payments.count(),
    }


@require_perm('remittance', 'view')
def period_list(request):
    periods = FinancialPeriod.objects.all()
    return inertia_render(request, 'Period/List', props={
        'periods': [_period_props(p) for p in periods],
    })


@require_perm('remittance', 'view')
def period_detail(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    entries = period.journal_entries.select_related('created_by').order_by('-entry_date', '-created_at')[:50]
    payments = period.payments.select_related('client', 'invoice', 'confirmed_by').order_by('-created_at')[:50]

    return inertia_render(request, 'Period/Detail', props={
        'period': _period_props(period),
        'entries': [{
            'id': e.pk,
            'entry_number': e.entry_number,
            'entry_type': e.entry_type,
            'entry_type_display': e.get_entry_type_display(),
            'description': e.description,
            'entry_date': e.entry_date.isoformat(),
            'total_debit': e.total_debit,
            'total_credit': e.total_credit,
            'is_balanced': e.is_balanced,
            'created_by': e.created_by.username if e.created_by else None,
        } for e in entries],
        'payments': [{
            'id': p.pk,
            'payment_number': p.payment_number,
            'client': p.client.name if p.client else None,
            'amount_sar': p.amount_sar,
            'status': p.status,
            'status_display': p.get_status_display(),
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'created_at': p.created_at.isoformat(),
        } for p in payments],
    })


@require_perm('remittance', 'edit')
def period_close(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    if request.method == 'POST':
        try:
            period.close(request.user)
            messages.success(request, f'Periode {period.name} berhasil ditutup.')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('period_detail', pk=pk)
    return redirect('period_detail', pk=pk)


@require_perm('remittance', 'edit')
def period_lock(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    if request.method == 'POST':
        try:
            period.lock(request.user)
            messages.success(request, f'Periode {period.name} berhasil di-lock.')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('period_detail', pk=pk)
    return redirect('period_detail', pk=pk)
