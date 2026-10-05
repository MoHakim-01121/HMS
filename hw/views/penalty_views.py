import logging
from datetime import date, datetime

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string

from inertia import render as inertia_render

from ..models import CancellationPenalty, ConfirmationLetter
from ..finance.penalty_billing import bill_penalty, penalty_state, unbill_penalty
from ..finance_helpers import FinanceError
from ..permissions import require_perm
from ..utils import round_half_up
from .helpers import _parse_date, _to_float
from .pdf import _logo_file_url

logger = logging.getLogger(__name__)


def _billing_notice(cl):
    """What saving a penalty on `cl` will do to its billing, for the form."""
    invoice = cl.invoice
    if invoice is not None:
        return {"invoice_number": invoice.invoice_number, "invoice_id": invoice.pk, "creates_invoice": False}
    return {"invoice_number": None, "invoice_id": None, "creates_invoice": True,
            "branch": cl.client.owner_branch.name}


def _penalty_amount(request):
    """Nominal denda (SAR, bilangan bulat > 0) dari form, atau None bila tidak sah."""
    amount = round_half_up(_to_float(request.POST.get('penalty_amount')) or 0)
    return amount if amount > 0 else None


def _get_cl(request, cl_pk):
    """Fetch a CL by pk."""
    return get_object_or_404(ConfirmationLetter, pk=cl_pk)


def _get_penalty(request, pk, qs=None):
    """Fetch a penalty by pk."""
    qs = qs if qs is not None else CancellationPenalty.objects.all()
    return get_object_or_404(qs, pk=pk)


def _state_props(penalty):
    """Billing and payment state of a penalty: both derived, never stored."""
    state = penalty_state(penalty)
    invoice = state['invoice']
    return {
        "is_paid": state['is_paid'],
        "paid_sar": state['paid'],
        "due_sar": state['due'],
        "payment_date": state['paid_on'].isoformat() if state['paid_on'] else None,
        "invoice": {"id": invoice.pk, "invoice_number": invoice.invoice_number} if invoice else None,
    }


def _penalty_props(penalty):
    cl = penalty.cl
    return {
        "id": penalty.pk,
        "penalty_number": penalty.penalty_number,
        "cancellation_date": penalty.cancellation_date.isoformat() if penalty.cancellation_date else None,
        "reason": penalty.reason,
        "penalty_amount": float(penalty.penalty_amount or 0),
        "penalty_currency": penalty.penalty_currency,
        "exchange_rate": float(penalty.exchange_rate or 1),
        **_state_props(penalty),
        "note": penalty.note,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
    }


@require_perm('penalty', 'create')
def penalty_new(request, cl_pk):
    cl = _get_cl(request, cl_pk)
    if hasattr(cl, 'penalty'):
        return redirect('penalty_detail', pk=cl.penalty.pk)

    # Denda hanya ada untuk reservasi yang dibatalkan (aturan bisnis B14).
    if not cl.is_cancelled:
        messages.error(request, 'Set the reservation status to Cancelled before adding a penalty.')
        return redirect('cl_detail', pk=cl.pk)

    suggested_number = CancellationPenalty.suggest_number()

    if request.method == 'POST':
        amount = _penalty_amount(request)
        if amount is None:
            messages.error(request, 'Penalty amount must be more than 0 (in SAR).')
            return redirect('penalty_new', cl_pk=cl.pk)
        number = request.POST.get('penalty_number', suggested_number)
        if CancellationPenalty.objects.filter(penalty_number=number).exists():
            messages.error(request, f"Penalty number '{number}' is already in use.")
            return redirect('penalty_new', cl_pk=cl.pk)
        try:
            with transaction.atomic():
                penalty = CancellationPenalty.objects.create(
                    cl=cl,
                    penalty_number=number,
                    cancellation_date=_parse_date(request.POST.get('cancellation_date')) or date.today(),
                    reason=request.POST.get('reason', ''),
                    penalty_amount=amount,
                    note=request.POST.get('note', ''),
                )
                CancellationPenalty.claim_number(penalty.penalty_number)
                # A penalty is always billed: on the invoice that bills its
                # reservation, or on a new invoice issued right here.
                invoice, created = bill_penalty(penalty, user=request.user)
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('penalty_new', cl_pk=cl.pk)
        logger.info("ledger: penalty %s billed on invoice %s", penalty.penalty_number, invoice.invoice_number)
        messages.success(request, (
            f"Penalty document {penalty.penalty_number} created and invoice {invoice.invoice_number} issued for it."
            if created else
            f"Penalty document {penalty.penalty_number} created and billed on invoice {invoice.invoice_number}."
        ))
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": None,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": suggested_number,
        "today": date.today().isoformat(),
        "edit": False,
        "billing": _billing_notice(cl),
    })


@require_perm('penalty', 'view')
def penalty_detail(request, pk):
    penalty = _get_penalty(request, pk, CancellationPenalty.objects.select_related('cl'))
    return inertia_render(request, "Penalty/Detail", props={"penalty": _penalty_props(penalty)})


@require_perm('penalty', 'edit')
def penalty_edit(request, pk):
    penalty = _get_penalty(request, pk, CancellationPenalty.objects.select_related('cl'))
    cl = penalty.cl

    if request.method == 'POST':
        amount = _penalty_amount(request)
        if amount is None:
            messages.error(request, 'Penalty amount must be more than 0 (in SAR).')
            return redirect('penalty_edit', pk=penalty.pk)
        try:
            with transaction.atomic():
                penalty.penalty_number  = request.POST.get('penalty_number', penalty.penalty_number)
                penalty.cancellation_date = _parse_date(request.POST.get('cancellation_date')) or penalty.cancellation_date
                penalty.reason          = request.POST.get('reason', '')
                penalty.penalty_amount  = amount
                penalty.note            = request.POST.get('note', '')
                penalty.save()
                CancellationPenalty.claim_number(penalty.penalty_number)
                bill_penalty(penalty, user=request.user)
        except FinanceError as e:
            messages.error(request, str(e))
            return redirect('penalty_edit', pk=penalty.pk)
        messages.success(request, f"Penalty document {penalty.penalty_number} updated successfully.")
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": _penalty_props(penalty),
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": penalty.penalty_number,
        "today": date.today().isoformat(),
        "edit": True,
        "billing": _billing_notice(cl),
    })


@require_perm('penalty', 'delete')
def penalty_delete(request, pk):
    penalty = _get_penalty(request, pk)
    cl_pk = penalty.cl_id
    if request.method == 'POST':
        num = penalty.penalty_number
        # System of record: penalty yang sudah menyentuh jurnal tidak bisa
        # dihapus dari riwayat keuangan. Denda yang keliru dikoreksi nominalnya,
        # atau dibebaskan lewat nota kredit pada baris dendanya.
        from ..models.journal import JournalLine
        if JournalLine.objects.filter(penalty=penalty).exists():
            messages.error(
                request,
                f'Penalty {num} tidak bisa dihapus karena sudah tercatat di jurnal keuangan. '
                'Ubah nominalnya, atau bebaskan lewat nota kredit di invoice-nya.',
            )
            return redirect('penalty_detail', pk=penalty.pk)
        with transaction.atomic():
            unbill_penalty(penalty, user=request.user)
            penalty.delete()
        messages.success(request, f"Penalty document {num} deleted successfully.")
        return redirect('cl_detail', pk=cl_pk)
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect('cl_detail', pk=cl_pk)


@require_perm('penalty', 'export')
def penalty_pdf(request, pk):
    penalty = _get_penalty(request, pk, CancellationPenalty.objects.select_related('cl'))
    cl = penalty.cl

    rooms = []
    for r in cl.rooms.all():
        nights = cl.num_nights or 1
        rooms.append({
            'type': r.room_type,
            'meals': r.meals,
            'quantity': r.quantity,
            'price': float(r.price),
            'subtotal': float(r.price) * r.quantity * nights,
        })

    ctx = {
        'penalty': penalty,
        'cl': cl,
        'rooms': rooms,
        'logo_rel_path': _logo_file_url(),
        'now': datetime.now(),
    }
    html = render_to_string('hw/penalty/penalty_pdf.html', ctx)

    from django.conf import settings
    from weasyprint import HTML
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="penalty-{penalty.penalty_number}.pdf"'
    return response


@require_perm('penalty', 'view')
def penalty_list(request):
    qs = CancellationPenalty.objects.select_related('cl', 'cl__client')

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(penalty_number__icontains=q)
            | Q(cl__confirmation_number__icontains=q)
            | Q(cl__client__name__icontains=q),
        )
    status = request.GET.get('status', '')

    # Paid or not is derived from the ledger, so that filter runs here.
    rows = []
    for p in qs[:300]:
        state = _state_props(p)
        if (status == 'paid' and not state['is_paid']) or (status == 'unpaid' and state['is_paid']):
            continue
        rows.append({
            'id': p.id,
            'penalty_number': p.penalty_number,
            'cl_id': p.cl_id,
            'confirmation_number': p.cl.confirmation_number,
            'client_id': p.cl.client_id,
            'client_name': p.cl.client.name,
            'cancellation_date': p.cancellation_date.isoformat(),
            'amount_sar': p.amount_sar,
            **state,
        })
    return inertia_render(request, 'Penalty/List', props={
        'penalties': rows[:100],
        'total': len(rows),
        'filters': {'q': q, 'status': status},
    })
