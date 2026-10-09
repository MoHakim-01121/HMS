"""Void invoice and credit notes (Nota Kredit) — hw/finance/credit_note_service.py.

Both reduce revenue, so both sit behind invoice/delete: managers and admins
only, never day-to-day staff.
"""
import json
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from inertia import render as inertia_render

from ..finance import credit_note_service as cns
from ..finance import queries as fq
from ..finance.errors import FinanceError
from ..models import ActivityLog, log_activity
from ..models.choices import InvoiceType
from ..models.credit_note import CreditNote
from ..models.invoice import Invoice
from ..branch_scope import get_in_scope_or_404, scope
from ..permissions import require_perm
from .helpers import _parse_date, request_data


def _detail_url(invoice):
    name = 'invoice_detail' if invoice.invoice_type == InvoiceType.HOTEL else 'services_detail'
    return reverse(name, args=[invoice.pk])


def _void_props(*, kicker, title, number, sub, action, cancel, blockers=(), error=None, reason=''):
    return {
        'kicker': kicker, 'title': title, 'number': number, 'sub': sub,
        'action': action, 'cancel': cancel, 'blockers': list(blockers),
        'error': error, 'reason': reason,
    }


@require_perm('payments', 'approve')
def invoice_void(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.all(), request.user, pk=pk)
    props = dict(
        kicker='Invoice', title='Void Invoice', number=invoice.invoice_number,
        sub='The charge is reversed and the invoice stays on record as void, with its number. '
            'Its confirmation letters can be billed again.',
        action=reverse('invoice_void', args=[pk]), cancel=_detail_url(invoice),
        blockers=cns.void_blockers(invoice),
    )
    if request.method != 'POST':
        return inertia_render(request, 'Finance/VoidForm', props=_void_props(**props))
    reason = str(request_data(request).get('reason') or '').strip()
    try:
        released = cns.void_invoice(invoice, reason=reason, created_by=request.user)
    except FinanceError as e:
        return inertia_render(request, 'Finance/VoidForm', props=_void_props(**props, error=str(e), reason=reason))
    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice', f'{invoice.invoice_number} void')
    msg = f'Invoice {invoice.invoice_number} di-void.'
    if released:
        msg += f' CL {", ".join(released)} bisa ditagih lagi.'
    messages.success(request, msg)
    return redirect(_detail_url(invoice))


@require_perm('payments', 'edit')
def invoice_excess_to_deposit(request, pk):
    """Move what the client overpaid on this invoice's reservations to their
    deposit (a reservation already paid whose value dropped: the CL changed,
    or it was cancelled with a penalty smaller than what was paid)."""
    from ..finance.posting import move_invoice_excess_to_deposit
    invoice = get_in_scope_or_404(Invoice.objects.all(), request.user, pk=pk)
    if request.method != 'POST':
        return redirect(_detail_url(invoice))
    try:
        moved = move_invoice_excess_to_deposit(invoice, created_by=request.user)
    except FinanceError as e:
        messages.error(request, str(e))
    else:
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice', f'{invoice.invoice_number} excess to deposit')
        messages.success(request, f'{moved:,} SAR kelebihan bayar dipindahkan ke deposit {invoice.client.name}.')
    return redirect(_detail_url(invoice))


def _cn_form_props(invoice, data=None, error=None):
    return {
        'invoice': {
            'id': invoice.pk, 'number': invoice.invoice_number, 'client': invoice.customer_name,
            'total': invoice.total_sar, 'credited': invoice.credited_sar,
            'paid': invoice.total_paid_sar, 'remaining': invoice.remaining_sar,
        },
        'lines': cns.creditable_lines(invoice),
        'cancel': _detail_url(invoice),
        'form': data or {'issued_date': date.today().isoformat(), 'reason': '', 'amounts': {}},
        'error': error,
    }


@require_perm('payments', 'approve')
def credit_note_new(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.all(), request.user, pk=pk)
    if invoice.is_void:
        messages.error(request, 'Invoice void tidak bisa diberi nota kredit.')
        return redirect(_detail_url(invoice))
    if request.method != 'POST':
        return inertia_render(request, 'Finance/CreditNoteForm', props=_cn_form_props(invoice))
    P = request_data(request)
    amounts = P.get('amounts') or '{}'
    try:
        amounts = json.loads(amounts) if isinstance(amounts, str) else amounts
        if not isinstance(amounts, dict):
            raise ValueError
    except ValueError:
        amounts = {}
    data = {
        'issued_date': str(P.get('issued_date') or ''),
        'reason': str(P.get('reason') or ''),
        'amounts': amounts,
    }
    lines = []
    for key, amount in amounts.items():
        kind, _sep, line_id = str(key).partition(':')
        lines.append({'kind': kind, 'id': line_id if line_id.isdigit() else 0, 'amount_sar': amount})
    try:
        cn = cns.issue_credit_note(
            invoice, lines=lines, reason=data['reason'],
            issued_date=_parse_date(data['issued_date']), created_by=request.user,
        )
    except FinanceError as e:
        return inertia_render(request, 'Finance/CreditNoteForm', props=_cn_form_props(invoice, data, str(e)))
    log_activity(request.user, ActivityLog.ACTION_CREATE, 'Credit Note', cn.credit_note_number)
    msg = f'Nota kredit {cn.credit_note_number} ({cn.amount_sar:,} SAR) dibuat.'
    if cn.to_deposit_sar:
        msg += f' {cn.to_deposit_sar:,} SAR sudah dibayar dan kini jadi titipan client.'
    messages.success(request, msg)
    return redirect(_detail_url(invoice))


def credit_note_rows(qs):
    return [{
        'id': cn.pk,
        'number': cn.credit_note_number,
        'date': cn.issued_date.isoformat(),
        'invoice_id': cn.invoice_id,
        'invoice_number': cn.invoice.invoice_number,
        'invoice_url': _detail_url(cn.invoice),
        'client': cn.client.name,
        'amount_sar': sum(line.amount_sar for line in cn.lines.all()),
        'to_deposit_sar': cn.to_deposit_sar,
        'reason': cn.reason,
        'status': cn.status,
        'voided_reason': cn.voided_reason,
    } for cn in qs]


@require_perm('invoice', 'view')
def credit_note_list(request):
    qs = scope(CreditNote.objects.all(), request.user).select_related('invoice', 'client').prefetch_related('lines')
    return inertia_render(request, 'Finance/CreditNotes', props={'credit_notes': credit_note_rows(qs)})


@require_perm('payments', 'approve')
def credit_note_void(request, pk):
    cn = get_in_scope_or_404(CreditNote.objects.select_related('invoice'), request.user, pk=pk)
    props = dict(
        kicker='Credit Note', title='Void Credit Note', number=cn.credit_note_number,
        sub=f'{cn.invoice.invoice_number} goes back to billing the credited amount.',
        action=reverse('credit_note_void', args=[pk]), cancel=_detail_url(cn.invoice),
        blockers=['Nota kredit ini sudah dibatalkan.'] if cn.status == CreditNote.STATUS_VOIDED else [],
    )
    if request.method != 'POST':
        return inertia_render(request, 'Finance/VoidForm', props=_void_props(**props))
    reason = str(request_data(request).get('reason') or '').strip()
    try:
        cns.void_credit_note(cn, reason=reason, created_by=request.user)
    except FinanceError as e:
        return inertia_render(request, 'Finance/VoidForm', props=_void_props(**props, error=str(e), reason=reason))
    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Credit Note', f'{cn.credit_note_number} void')
    messages.success(request, f'Nota kredit {cn.credit_note_number} dibatalkan.')
    return redirect(_detail_url(cn.invoice))


@require_perm('invoice', 'export')
def credit_note_pdf(request, pk):
    from weasyprint import HTML
    from .pdf import _logo_file_url
    from .receipt_views import _number_in_words
    cn = get_in_scope_or_404(CreditNote.objects.select_related('invoice', 'client', 'created_by'), request.user, pk=pk)
    invoice = cn.invoice
    lines = list(cn.lines.all())
    amount = sum(line.amount_sar for line in lines)
    credited = fq.invoice_credited_sar(invoice.pk)
    context = {
        'cn': cn,
        'invoice': invoice,
        'client_name': cn.client.name,
        'logo_rel_path': _logo_file_url(),
        'lines': [{'description': line.description, 'amount_fmt': f'{line.amount_sar:,}'} for line in lines],
        'amount_fmt': f'{amount:,}',
        'amount_in_words': _number_in_words(amount).capitalize(),
        'invoice_total_fmt': f'{invoice.total_sar:,}',
        'credited_fmt': f'{credited:,}',
        'due_fmt': f'{invoice.total_sar - credited:,}',
        'to_deposit_fmt': f'{cn.to_deposit_sar:,}' if cn.to_deposit_sar else None,
        'issued_by': cn.created_by.get_full_name() or cn.created_by.username,
        'printed_at_ts': timezone.localtime(timezone.now()),
    }
    html = render_to_string('hw/credit_note/credit_note_pdf.html', context)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{cn.credit_note_number}.pdf"'
    return response


def invoice_credit_props(invoice):
    """Void state and credit notes for an invoice detail page (hotel or service)."""
    qs = invoice.credit_notes.select_related('invoice', 'client').prefetch_related('lines')
    return {
        'void': {
            'reason': invoice.void_reason,
            'at': timezone.localtime(invoice.voided_at).strftime('%d %b %Y %H:%M') if invoice.voided_at else None,
            'by': (invoice.voided_by.get_full_name() or invoice.voided_by.username) if invoice.voided_by_id else None,
        } if invoice.is_void else None,
        'credit_notes': credit_note_rows(qs),
        'credited_sar': invoice.credited_sar,
        'can_void': not cns.void_blockers(invoice),
    }
