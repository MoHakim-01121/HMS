import json
import logging
import uuid
from datetime import date, datetime, time as dt_time

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import (
    ActivityLog, Client, ConfirmationLetter, Invoice, Reservation, log_activity,
    Account, AllocationReason, Allocation, CashMovement, Charge,
)
from ..permissions import require_perm
from .. import ledger
from .helpers import _is_mobile, _page_range_display, get_active_company, _to_float, _parse_date, validate_proof_file

logger = logging.getLogger(__name__)


def _company(request):
    return get_active_company(request)


@require_perm('clients', 'view')
def client_list(request):
    company = _company(request)
    qs = Client.objects.filter(company=company)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(city__icontains=q) | Q(pic__icontains=q))

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)

    qs = qs.order_by('name')
    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    data = [{
        "id": c.pk,
        "name": c.name,
        "brand": c.brand,
        "city": c.city,
        "province": c.province,
        "pic": c.pic,
        "wa": c.wa,
        "wa_group": c.wa_group,
        "reminder_target": c.reminder_target,
        "avg_days_to_pay": c.avg_days_to_pay,
        "days_since_last_order": c.days_since_last_order,
        "risk_label": c.risk_label,
        "is_active": c.is_active,
    } for c in page_obj]
    return inertia_render(request, "Client/List", props={
        "clients": data, "q": q, "status": status,
        "total_count": paginator.count,
        "pagination": {
            "number": page_obj.number,
            "num_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
            "has_other_pages": page_obj.has_other_pages(),
            "range": _page_range_display(page_obj),
            "start_index": page_obj.start_index(),
            "end_index": page_obj.end_index(),
            "count": paginator.count,
        },
    })


def _validate_client(data):
    errors = {}
    if not data.get("name", "").strip():
        errors["name"] = "Agent name is required."
    return errors


def _client_echo(data):
    """Echo submitted values back to the form on validation error."""
    return {
        "name": data.get("name", ""), "brand": data.get("brand", ""),
        "city": data.get("city", ""),
        "province": data.get("province", ""), "address": data.get("address", ""),
        "pic": data.get("pic", ""),
        "wa": data.get("wa", ""), "wa_group": data.get("wa_group", ""),
        "reminder_target": data.get("reminder_target", "GROUP"), "email": data.get("email", ""),
        "note": data.get("note", ""), "lat": data.get("lat", ""),
        "lng": data.get("lng", ""), "is_active": data.get("is_active") == "on",
    }


@require_perm('clients', 'create')
def client_new(request):
    company = _company(request)
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            return inertia_render(request, "Client/Form", props={
                "client": _client_echo(request.POST), "edit": False, "errors": errors,
            })
        c = Client(company=company)
        _save_client(c, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name, c.company)
        messages.success(request, f'Client "{c.name}" added successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={"client": None, "edit": False})


@require_perm('clients', 'edit')
def client_edit(request, pk):
    c = get_object_or_404(Client, pk=pk, company=_company(request))
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            echo = _client_echo(request.POST); echo["id"] = c.pk
            return inertia_render(request, "Client/Form", props={
                "client": echo, "edit": True, "errors": errors,
            })
        _before = {'Name': c.name, 'Brand': c.brand, 'City': c.city, 'Province': c.province, 'Address': c.address, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        _save_client(c, request.POST)
        _after  = {'Name': c.name, 'Brand': c.brand, 'City': c.city, 'Province': c.province, 'Address': c.address, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, c.company, changes)
        messages.success(request, f'Client "{c.name}" updated successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": {
            "id": c.pk, "name": c.name, "brand": c.brand, "city": c.city, "province": c.province,
            "address": c.address,
            "pic": c.pic, "wa": c.wa, "wa_group": c.wa_group, "reminder_target": c.reminder_target,
            "email": c.email, "note": c.note,
            "lat": c.lat, "lng": c.lng, "is_active": c.is_active,
        },
        "edit": True,
    })


@require_perm('clients', 'delete')
@require_POST
def client_delete(request, pk):
    c = get_object_or_404(Client, pk=pk, company=_company(request))
    name = c.name
    c.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Client', name, c.company)
    messages.success(request, f'Client "{name}" deleted.')
    return redirect('client_list')


@require_perm('clients', 'view')
def client_detail(request, pk):
    company = _company(request)
    qs = Client.objects.filter(company=company).prefetch_related('cls__rooms')
    c = get_object_or_404(qs, pk=pk)
    # Invoice.client is essentially dead (never populated by any form) -- the
    # real link is resolved_invoices, via Charge.client. Using c.invoices here
    # used to render every client's invoice history as empty.
    invoices = c.resolved_invoices.prefetch_related('reservations', 'payments')
    cls = c.cls.order_by('-created_at')
    inv_data = [{
        "pk": inv.pk,
        "invoice_number": inv.invoice_number,
        "invoice_type": inv.invoice_type,
        "invoice_type_display": inv.get_invoice_type_display(),
        "total_sar": inv.total_sar,
        "remaining_sar": inv.remaining_sar,
        "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
    } for inv in invoices]
    cls_data = [{
        "pk": cl.pk,
        "confirmation_number": cl.confirmation_number,
        "guest_name": cl.guest_name,
        "hotel_name": cl.hotel_name,
        "check_in": cl.check_in.strftime("%d/%m/%Y") if cl.check_in else None,
    } for cl in cls]

    statement_rows = ledger.client_statement(c)
    activity = [{
        "date": r["date"].strftime("%d/%m/%Y") if r["date"] else None,
        "type": r["type"],
        "description": r["description"],
        "debit": r["debit"],
        "credit": r["credit"],
        "balance": r["balance"],
    } for r in statement_rows[-15:]]

    return inertia_render(request, "Client/Detail", props={
        "client": {
            "pk": c.pk,
            "name": c.name,
            "brand": c.brand,
            "city": c.city,
            "province": c.province,
            "address": c.address,
            "pic": c.pic,
            "wa": c.wa,
            "wa_group": c.wa_group,
            "reminder_target": c.reminder_target,
            "email": c.email,
            "note": c.note,
            "is_active": c.is_active,
            "total_billed": c.total_billed,
            "outstanding": c.outstanding,
            "saldo_dana": ledger.saldo_dana(c),
            "avg_days_to_pay": c.avg_days_to_pay,
            "score": c.score,
            "risk_label": c.risk_label,
            "days_since_last_order": c.days_since_last_order,
        },
        "invoices": inv_data,
        "cls": cls_data,
        "activity": activity,
    })


@require_perm('clients', 'view')
def client_map(request):
    company = _company(request)
    qs = Client.objects.filter(company=company, lat__isnull=False, lng__isnull=False)
    return inertia_render(request, "Client/Map", props={"clients_count": qs.count()})


@require_perm('clients', 'view')
def client_map_data(request):
    company = _company(request)
    qs = (
        Client.objects
        .filter(company=company, lat__isnull=False, lng__isnull=False)
        .prefetch_related('invoices__payments', 'invoices__reservations')
    )

    data = [
        {
            'id': c.pk,
            'name': c.name,
            'brand': c.brand,
            'city': c.city,
            'province': c.province,
            'lat': c.lat,
            'lng': c.lng,
            'outstanding': c.outstanding,
            'total_billed': c.total_billed,
            'score': c.score,
            'risk': c.risk_label,
            'url': reverse('client_detail', args=[c.pk]),
            'wa': c.wa,
            'pic': c.pic,
        }
        for c in qs
    ]
    return JsonResponse({'clients': data})


def _save_client(c, data):
    c.name      = data.get('name', '').strip()
    c.brand     = data.get('brand', '').strip()
    c.city      = data.get('city', '').strip()
    c.province  = data.get('province', '').strip()
    c.address   = data.get('address', '').strip()
    c.pic       = data.get('pic', '').strip()
    c.wa        = data.get('wa', '').strip()
    c.wa_group  = data.get('wa_group', '').strip()
    rt = data.get('reminder_target', '').strip()
    c.reminder_target = rt if rt in dict(Client.REMINDER_TARGET_CHOICES) else 'GROUP'
    c.email     = data.get('email', '').strip()
    c.note      = data.get('note', '').strip()
    c.is_active = data.get('is_active') == 'on'
    try: c.lat = float(data.get('lat') or 0) or None
    except (ValueError, TypeError): c.lat = None
    try: c.lng = float(data.get('lng') or 0) or None
    except (ValueError, TypeError): c.lng = None
    c.save()


def _client_reservation_options(client_obj):
    """Reservations for this client's from/to transfer pickers.

    Sourced from Charge.client rather than Invoice.client/CL.client: those
    two are frequently unpopulated for older records (see the migration's
    client-resolution audit), while Charge.client is always the resolved
    value written by _billing_client() at dual-write/migration time.
    """
    reservation_ids = Charge.objects.filter(
        client=client_obj, reservation__isnull=False,
    ).values_list('reservation_id', flat=True).distinct()
    reservations = Reservation.objects.filter(pk__in=reservation_ids).select_related('invoice').order_by('-check_in')
    return [{
        'id': r.id,
        'label': f'{r.reservation_number} — {r.invoice.invoice_number}',
        'piutang': ledger.piutang(r),
    } for r in reservations]


@require_perm('clients', 'edit')
def client_transfer(request, pk):
    company = _company(request)
    client_obj = get_object_or_404(Client, pk=pk, company=company)

    if request.method == 'POST':
        try:
            from_id = int(request.POST.get('from_reservation') or 0)
            to_id = int(request.POST.get('to_reservation') or 0)
        except (ValueError, TypeError):
            from_id = to_id = 0
        amount = int(round(_to_float(request.POST.get('amount_sar'))))
        note = (request.POST.get('note') or '').strip()

        errors = {}
        if not from_id or not to_id:
            errors['from_reservation'] = 'Choose both reservations.'
        elif from_id == to_id:
            errors['to_reservation'] = 'Choose a different reservation to move to.'
        if amount <= 0:
            errors['amount_sar'] = 'Enter an amount greater than zero.'

        # Scoped to this client's own reservations (same Charge.client lookup as
        # _client_reservation_options), not just the active company -- otherwise a
        # tampered reservation id from another client in the same company would
        # get its Allocation mislabelled with client_obj below.
        client_reservation_ids = set(
            Charge.objects.filter(client=client_obj, reservation__isnull=False)
            .values_list('reservation_id', flat=True)
        )
        from_res = Reservation.objects.filter(pk=from_id).first() if from_id in client_reservation_ids else None
        to_res = Reservation.objects.filter(pk=to_id).first() if to_id in client_reservation_ids else None
        if from_id and not from_res:
            errors['from_reservation'] = 'Reservation not found.'
        if to_id and not to_res:
            errors['to_reservation'] = 'Reservation not found.'

        if not errors:
            group = uuid.uuid4()
            today = date.today()
            with transaction.atomic():
                Allocation.objects.create(
                    company=company, client=client_obj, date=today, amount_sar=-amount,
                    invoice=from_res.invoice, reservation=from_res,
                    reason=AllocationReason.TRANSFER, transfer_group=group, note=note,
                    created_by=request.user,
                )
                Allocation.objects.create(
                    company=company, client=client_obj, date=today, amount_sar=amount,
                    invoice=to_res.invoice, reservation=to_res,
                    reason=AllocationReason.TRANSFER, transfer_group=group, note=note,
                    created_by=request.user,
                )
            logger.info(
                "ledger: transfer %s SAR from reservation %s to %s (client %s)",
                amount, from_res.reservation_number, to_res.reservation_number, client_obj.pk,
            )
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Fund Transfer', client_obj.name, company)
            messages.success(request, f'Moved {amount} SAR from {from_res.reservation_number} to {to_res.reservation_number}.')
            return redirect('client_detail', pk=pk)

        return inertia_render(request, 'Client/Transfer', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': ledger.saldo_dana(client_obj)},
            'reservations': _client_reservation_options(client_obj),
            'errors': errors,
            'initial': {'from_reservation': from_id or '', 'to_reservation': to_id or '', 'amount_sar': request.POST.get('amount_sar', ''), 'note': note},
        })

    return inertia_render(request, 'Client/Transfer', props={
        'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': ledger.saldo_dana(client_obj)},
        'reservations': _client_reservation_options(client_obj),
    })


@require_perm('clients', 'edit')
def client_refund(request, pk):
    company = _company(request)
    client_obj = get_object_or_404(Client, pk=pk, company=company)

    if request.method == 'POST':
        from_account = request.POST.get('from_account') or Account.SBY
        amount = int(round(_to_float(request.POST.get('amount_sar'))))
        note = (request.POST.get('note') or '').strip()
        proof = request.FILES.get('proof')

        errors = {}
        if from_account not in (Account.SBY, Account.PUSAT):
            errors['from_account'] = 'Choose where the refund is paid from.'
        if amount <= 0:
            errors['amount_sar'] = 'Enter an amount greater than zero.'
        if proof:
            proof_error = validate_proof_file(proof)
            if proof_error:
                errors['proof'] = proof_error

        if not errors:
            mov = CashMovement.objects.create(
                company=company, client=client_obj, date=date.today(),
                from_account=from_account, to_account=Account.CLIENT,
                amount=amount, currency='SAR', exchange_rate=1,
                note=note or f'Refund to {client_obj.name}', created_by=request.user,
            )
            if proof:
                mov.proof = proof
                mov.save(update_fields=['proof'])
            logger.info(
                "ledger: refund %s SAR to client %s from %s",
                amount, client_obj.pk, from_account,
            )
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Refund', client_obj.name, company)
            messages.success(request, f'Refunded {amount} SAR to {client_obj.name}.')
            return redirect('client_detail', pk=pk)

        return inertia_render(request, 'Client/Refund', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': ledger.saldo_dana(client_obj)},
            'errors': errors,
            'initial': {'from_account': from_account, 'amount_sar': request.POST.get('amount_sar', ''), 'note': note},
        })

    return inertia_render(request, 'Client/Refund', props={
        'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': ledger.saldo_dana(client_obj)},
    })


@require_perm('clients', 'export')
def client_statement_pdf(request, pk):
    """Full customer statement (rekening koran), bitemporal via `as_of`.

    `from`/`to` scope which events show; `as_of` (also a date, taken as
    end-of-day) locks out anything recorded after that point so a reprint of
    a past period always reproduces identical numbers -- see
    hw/ledger.py::client_statement. Rows before `from` aren't dropped, just
    folded into a single opening-balance line computed with the same
    `as_of`, so the closing balance always reconciles with a full statement.
    """
    from django.utils import timezone as dj_timezone

    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url

    company = _company(request)
    c = get_object_or_404(Client, pk=pk, company=company)

    date_from = _parse_date(request.GET.get('from', ''))
    date_to = _parse_date(request.GET.get('to', ''))
    as_of_date = _parse_date(request.GET.get('as_of', ''))
    as_of = dj_timezone.make_aware(datetime.combine(as_of_date, dt_time.max)) if as_of_date else None

    statement = ledger.client_statement_with_opening(c, date_from=date_from, date_to=date_to, as_of=as_of)
    opening_balance = statement['opening_balance']
    closing_balance = statement['closing_balance']
    total_debit = statement['total_debit']
    total_credit = statement['total_credit']
    formatted_rows = [{
        'date': r['date'].strftime('%d/%m/%Y') if r['date'] else '—',
        'type': r['type'],
        'description': r['description'],
        'debit': r['debit'],
        'credit': r['credit'],
        'balance': r['balance'],
    } for r in statement['rows']]

    if date_from and date_to:
        period_label = f"{date_from.strftime('%d %b %Y')} — {date_to.strftime('%d %b %Y')}"
    elif date_from:
        period_label = f"Sejak {date_from.strftime('%d %b %Y')}"
    elif date_to:
        period_label = f"Sampai {date_to.strftime('%d %b %Y')}"
    else:
        period_label = 'Semua transaksi'

    return _render_list_pdf(
        request, Client.objects.none(),
        template='hw/client/client_statement_pdf.html',
        filename=f'statement_{c.name}_{date.today()}.pdf'.replace(' ', '_'),
        extra_ctx={
            'client': c,
            'rows': formatted_rows,
            'period_label': period_label,
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'logo_url': _logo_file_url(company),
        },
    )
