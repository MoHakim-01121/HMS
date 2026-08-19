import logging
from datetime import date, datetime

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string

from inertia import render as inertia_render

from ..models import (
    CancellationPenalty, ConfirmationLetter,
    Charge, Allocation, CashMovement, ChargeReason, AllocationReason, Account,
)
from ..permissions import require_perm
from .helpers import _parse_date, _to_float, get_active_company
from .pdf import _logo_file_url

logger = logging.getLogger(__name__)


def _sync_penalty_ledger(penalty):
    """Dual-write (remittance ledger redesign, Fase 5): a penalty always
    represents a charge, and -- once marked paid -- a real cash movement.
    Full resync scoped to `penalty=penalty`, which only this function ever
    sets, so it's safe to call on every create/edit."""
    cl = penalty.cl
    with transaction.atomic():
        Charge.objects.filter(penalty=penalty).delete()
        Allocation.objects.filter(penalty=penalty).delete()
        CashMovement.objects.filter(penalty_label=penalty).delete()

        if not penalty.penalty_amount_sar:
            return

        Charge.objects.create(
            company=cl.company, client=cl.client, invoice=cl.invoice, date=penalty.cancellation_date or date.today(),
            amount_sar=penalty.penalty_amount_sar, penalty=penalty, reason=ChargeReason.CANCELLATION,
            description=f'Penalty {penalty.penalty_number}',
        )
        if penalty.is_paid:
            pay_date = penalty.payment_date or penalty.cancellation_date or date.today()
            to_account = Account.PUSAT if (penalty.payment_method or '').strip().lower() == 'direct' else Account.SBY
            mov = CashMovement.objects.create(
                company=cl.company, client=cl.client, invoice=cl.invoice, date=pay_date,
                from_account=Account.CLIENT, to_account=to_account,
                amount=penalty.penalty_amount, currency=penalty.penalty_currency, exchange_rate=penalty.exchange_rate,
                method=penalty.payment_method, penalty_label=penalty,
                note=f'Pembayaran penalty {penalty.penalty_number}',
            )
            Allocation.objects.create(
                company=cl.company, client=cl.client, invoice=cl.invoice, date=pay_date,
                amount_sar=mov.amount_sar, penalty=penalty, reason=AllocationReason.CANCELLATION,
                note=f'Pembayaran penalty {penalty.penalty_number}',
            )
    logger.info(
        "ledger: penalty %s synced (%s SAR, paid=%s)",
        penalty.penalty_number, penalty.penalty_amount_sar, penalty.is_paid,
    )


def _get_cl(request, cl_pk):
    """Fetch a CL scoped to the active company (consistent with cl/invoice views)."""
    return get_object_or_404(ConfirmationLetter, pk=cl_pk, company=get_active_company(request))


def _get_penalty(request, pk, qs=None):
    """Fetch a penalty scoped to the active company via its CL."""
    qs = qs if qs is not None else CancellationPenalty.objects.all()
    qs = qs.filter(cl__company=get_active_company(request))
    return get_object_or_404(qs, pk=pk)


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
        "is_paid": penalty.is_paid,
        "payment_date": penalty.payment_date.isoformat() if penalty.payment_date else None,
        "payment_method": penalty.payment_method,
        "payment_note": penalty.payment_note,
        "note": penalty.note,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
    }


@require_perm('penalty', 'create')
def penalty_new(request, cl_pk):
    cl = _get_cl(request, cl_pk)
    if hasattr(cl, 'penalty'):
        return redirect('penalty_detail', pk=cl.penalty.pk)

    suggested_number = CancellationPenalty.generate_number()

    if request.method == 'POST':
        penalty = CancellationPenalty.objects.create(
            cl=cl,
            penalty_number=request.POST.get('penalty_number', suggested_number),
            cancellation_date=_parse_date(request.POST.get('cancellation_date')),
            reason=request.POST.get('reason', ''),
            penalty_amount=_to_float(request.POST.get('penalty_amount')),
            penalty_currency=request.POST.get('penalty_currency', 'SAR'),
            exchange_rate=_to_float(request.POST.get('exchange_rate'), 1) or 1,
            is_paid=request.POST.get('is_paid') == 'on',
            payment_date=_parse_date(request.POST.get('payment_date')),
            payment_method=request.POST.get('payment_method', ''),
            payment_note=request.POST.get('payment_note', ''),
            note=request.POST.get('note', ''),
        )
        _sync_penalty_ledger(penalty)
        messages.success(request, f"Penalty document {penalty.penalty_number} created successfully.")
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": None,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": suggested_number,
        "today": date.today().isoformat(),
        "edit": False,
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
        penalty.penalty_number  = request.POST.get('penalty_number', penalty.penalty_number)
        penalty.cancellation_date = _parse_date(request.POST.get('cancellation_date')) or penalty.cancellation_date
        penalty.reason          = request.POST.get('reason', '')
        penalty.penalty_amount  = _to_float(request.POST.get('penalty_amount'))
        penalty.penalty_currency = request.POST.get('penalty_currency', 'SAR')
        penalty.exchange_rate   = _to_float(request.POST.get('exchange_rate'), 1) or 1
        penalty.is_paid         = request.POST.get('is_paid') == 'on'
        penalty.payment_date    = _parse_date(request.POST.get('payment_date'))
        penalty.payment_method  = request.POST.get('payment_method', '')
        penalty.payment_note    = request.POST.get('payment_note', '')
        penalty.note            = request.POST.get('note', '')
        penalty.save()
        _sync_penalty_ledger(penalty)
        messages.success(request, f"Penalty document {penalty.penalty_number} updated successfully.")
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": _penalty_props(penalty),
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": penalty.penalty_number,
        "today": date.today().isoformat(),
        "edit": True,
    })


@require_perm('penalty', 'delete')
def penalty_delete(request, pk):
    penalty = _get_penalty(request, pk)
    cl_pk = penalty.cl_id
    if request.method == 'POST':
        num = penalty.penalty_number
        # System of record: dokumen yang sudah masuk ledger tidak bisa
        # dihapus -- Charge/Allocation mereferensikan penalty via CASCADE,
        # jadi hapus = menghilangkan jejak tagihan. Nolkan nominalnya untuk
        # membatalkan dampak ledger (lihat _sync_penalty_ledger).
        has_ledger = (
            Charge.objects.filter(penalty=penalty).exists()
            or Allocation.objects.filter(penalty=penalty).exists()
        )
        if has_ledger:
            messages.error(request, f'Penalty {num} tidak bisa dihapus karena sudah tercatat di ledger keuangan.')
            return redirect('penalty_detail', pk=penalty.pk)
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
        'logo_rel_path': _logo_file_url(cl.company),
        'now': datetime.now(),
    }
    html = render_to_string('hw/penalty/penalty_pdf.html', ctx)

    from django.conf import settings
    from weasyprint import HTML
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="penalty-{penalty.penalty_number}.pdf"'
    return response
