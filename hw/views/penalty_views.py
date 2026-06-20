from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string

from inertia import render as inertia_render

from ..models import CancellationPenalty, ConfirmationLetter
from .helpers import _parse_date
from .pdf import _logo_file_url


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


@login_required
def penalty_new(request, cl_pk):
    cl = get_object_or_404(ConfirmationLetter, pk=cl_pk)
    if hasattr(cl, 'penalty'):
        return redirect('penalty_detail', pk=cl.penalty.pk)

    suggested_number = CancellationPenalty.generate_number()

    if request.method == 'POST':
        penalty = CancellationPenalty.objects.create(
            cl=cl,
            penalty_number=request.POST.get('penalty_number', suggested_number),
            cancellation_date=_parse_date(request.POST.get('cancellation_date')),
            reason=request.POST.get('reason', ''),
            penalty_amount=float(request.POST.get('penalty_amount', 0) or 0),
            penalty_currency=request.POST.get('penalty_currency', 'SAR'),
            exchange_rate=float(request.POST.get('exchange_rate', 1) or 1),
            is_paid=request.POST.get('is_paid') == 'on',
            payment_date=_parse_date(request.POST.get('payment_date')),
            payment_method=request.POST.get('payment_method', ''),
            payment_note=request.POST.get('payment_note', ''),
            note=request.POST.get('note', ''),
        )
        messages.success(request, f"Penalty document {penalty.penalty_number} created successfully.")
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": None,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": suggested_number,
        "today": date.today().isoformat(),
        "edit": False,
    })


@login_required
def penalty_detail(request, pk):
    penalty = get_object_or_404(CancellationPenalty.objects.select_related('cl'), pk=pk)
    return inertia_render(request, "Penalty/Detail", props={"penalty": _penalty_props(penalty)})


@login_required
def penalty_edit(request, pk):
    penalty = get_object_or_404(CancellationPenalty.objects.select_related('cl'), pk=pk)
    cl = penalty.cl

    if request.method == 'POST':
        penalty.penalty_number  = request.POST.get('penalty_number', penalty.penalty_number)
        penalty.cancellation_date = _parse_date(request.POST.get('cancellation_date')) or penalty.cancellation_date
        penalty.reason          = request.POST.get('reason', '')
        penalty.penalty_amount  = float(request.POST.get('penalty_amount', 0) or 0)
        penalty.penalty_currency = request.POST.get('penalty_currency', 'SAR')
        penalty.exchange_rate   = float(request.POST.get('exchange_rate', 1) or 1)
        penalty.is_paid         = request.POST.get('is_paid') == 'on'
        penalty.payment_date    = _parse_date(request.POST.get('payment_date'))
        penalty.payment_method  = request.POST.get('payment_method', '')
        penalty.payment_note    = request.POST.get('payment_note', '')
        penalty.note            = request.POST.get('note', '')
        penalty.save()
        messages.success(request, f"Penalty document {penalty.penalty_number} updated successfully.")
        return redirect('penalty_detail', pk=penalty.pk)

    return inertia_render(request, "Penalty/Form", props={
        "penalty": _penalty_props(penalty),
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": penalty.penalty_number,
        "today": date.today().isoformat(),
        "edit": True,
    })


@login_required
def penalty_delete(request, pk):
    penalty = get_object_or_404(CancellationPenalty, pk=pk)
    cl_pk = penalty.cl_id
    if request.method == 'POST':
        num = penalty.penalty_number
        penalty.delete()
        messages.success(request, f"Penalty document {num} deleted successfully.")
        return redirect('cl_detail', pk=cl_pk)
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect('cl_detail', pk=cl_pk)


@login_required
def penalty_pdf(request, pk):
    penalty = get_object_or_404(CancellationPenalty.objects.select_related('cl'), pk=pk)
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
