"""Period management views -- list, detail, close, lock, create; seasons."""
import logging
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..finance import period_checklist, seasons
from ..models.period import FinancialPeriod, Season
from ..permissions import require_perm
from .helpers import _parse_date, serialize_journal_entry

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


@require_perm('periods', 'view')
def period_list(request):
    periods = FinancialPeriod.objects.all()
    return inertia_render(request, 'Period/List', props={
        'periods': [_period_props(p) for p in periods],
        'seasons': seasons.season_choices(),
    })


@require_perm('periods', 'view')
def period_detail(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    entries = period.journal_entries.select_related('created_by').order_by('-entry_date', '-created_at')[:50]
    payments = period.payments.select_related('client', 'invoice', 'confirmed_by').order_by('-created_at')[:50]

    # Calculate account balances for this period (debit - credit)
    from ..models.journal import JournalLine, LedgerAccount
    totals = {
        row['account']: (row['d'] or 0) - (row['c'] or 0)
        for row in JournalLine.objects.filter(journal_entry__period=period)
        .values('account').annotate(d=Sum('debit'), c=Sum('credit'))
    }
    account_balances = [
        {'account': acc.code, 'label': acc.name, 'balance': total}
        for acc in LedgerAccount.objects.all()
        if (total := totals.get(acc.code))
    ]

    # Period totals
    total_debit = sum(e.total_debit for e in entries)
    total_credit = sum(e.total_credit for e in entries)

    return inertia_render(request, 'Period/Detail', props={
        'period': _period_props(period),
        'entries': [serialize_journal_entry(e, total_debit=e.total_debit, total_credit=e.total_credit, is_balanced=e.is_balanced, created_by=e.created_by.username if e.created_by else None) for e in entries],
        'payments': [{
            'id': p.pk,
            'payment_number': p.payment_number,
            'client_name': p.client.name if p.client else None,
            'amount_sar': p.amount_sar,
            'status': p.display_status,
            'status_display': p.display_status_label,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'created_at': p.created_at.isoformat(),
        } for p in payments],
        'account_balances': account_balances,
        'total_debit': total_debit,
        'total_credit': total_credit,
        # A locked period is sealed; the checklist is for getting there.
        'checklist': None if period.status == FinancialPeriod.STATUS_LOCKED else period_checklist.checklist(period),
    })


@require_perm('periods', 'edit')
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


@require_perm('periods', 'edit')
def period_lock(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    if request.method == 'POST':
        fails = [i for i in period_checklist.checklist(period)['items'] if i['status'] == period_checklist.FAIL]
        if fails:
            why = {'pending_payments': 'pembayaran pending', 'integrity': 'temuan integritas jurnal'}
            messages.error(request, 'Periode belum bisa di-lock — selesaikan dulu: ' + ', '.join(
                f"{i['params']['n']} {why.get(i['key'], i['label'])}" for i in fails))
            return redirect('period_detail', pk=pk)
        try:
            period.lock(request.user)
            messages.success(request, f'Periode {period.name} berhasil di-lock.')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('period_detail', pk=pk)
    return redirect('period_detail', pk=pk)


def _post_data(request):
    import json
    if request.content_type == 'application/json':
        try:
            return json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            pass
    return request.POST


@require_perm('periods', 'edit')
def period_create(request):
    """Create the monthly periods of a year that do not exist yet."""
    if request.method == 'POST':
        try:
            year = int(_post_data(request).get('year', date.today().year))
            if not 2000 <= year <= 2100:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Tahun tidak valid.')
            return redirect('period_list')
        created = seasons.ensure_monthly_periods(date(year, 1, 1), date(year, 12, 31))
        messages.success(request, f'{len(created)} periode untuk tahun {year} berhasil dibuat.')
    return redirect('period_list')


@require_perm('periods', 'edit')
def season_save(request, pk=None):
    """Create a season (no pk) or change one; adds the months it needs."""
    season = get_object_or_404(Season, pk=pk) if pk else None
    if request.method == 'POST':
        data = _post_data(request)
        try:
            saved = seasons.save_season(
                season, name=data.get('name'),
                date_from=_parse_date(data.get('date_from')), date_to=_parse_date(data.get('date_to')),
            )
            messages.success(request, f'Musim {saved.name} tersimpan.')
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
    return redirect('period_list')


@require_perm('periods', 'edit')
def season_delete(request, pk):
    """A season only names a date range: deleting it leaves periods and journal as they are."""
    season = get_object_or_404(Season, pk=pk)
    if request.method == 'POST':
        season.delete()
        messages.success(request, f'Musim {season.name} dihapus.')
    return redirect('period_list')
