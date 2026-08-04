import json
from datetime import date, timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import ActivityLog, Client, ConfirmationLetter, Invoice, log_activity
from ..permissions import require_perm
from .helpers import get_active_company


def _company(request):
    return get_active_company(request)


@require_perm('clients', 'view')
def client_list(request):
    company = _company(request)
    qs = Client.objects.filter(company=company)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(pic__icontains=q))

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)

    clients = list(
        qs.order_by('name')
        .prefetch_related('invoices__payments', 'invoices__reservations', 'cls')
    )
    data = [{
        "id": c.pk,
        "name": c.name,
        "city": c.city,
        "province": c.province,
        "pic": c.pic,
        "wa": c.wa,
        "wa_group": c.wa_group,
        "reminder_target": c.reminder_target,
        "invoices_count": len(c.invoices.all()),
        "outstanding": c.outstanding,
        "score": c.score,
        "risk_label": c.risk_label,
        "is_active": c.is_active,
    } for c in clients]
    return inertia_render(request, "Client/List", props={
        "clients": data, "q": q, "status": status,
    })


def _validate_client(data):
    errors = {}
    if not data.get("name", "").strip():
        errors["name"] = "Agent name is required."
    return errors


def _client_echo(data):
    """Echo submitted values back to the form on validation error."""
    return {
        "name": data.get("name", ""), "city": data.get("city", ""),
        "province": data.get("province", ""), "pic": data.get("pic", ""),
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
        _before = {'Name': c.name, 'City': c.city, 'Province': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        _save_client(c, request.POST)
        _after  = {'Name': c.name, 'City': c.city, 'Province': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, c.company, changes)
        messages.success(request, f'Client "{c.name}" updated successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": {
            "id": c.pk, "name": c.name, "city": c.city, "province": c.province,
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
    qs = Client.objects.filter(company=company).prefetch_related(
        'invoices__payments',
        'invoices__reservations',
        'cls__rooms',
    )
    c = get_object_or_404(qs, pk=pk)
    invoices = c.invoices.order_by('-created_at')
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
    return inertia_render(request, "Client/Detail", props={
        "client": {
            "pk": c.pk,
            "name": c.name,
            "city": c.city,
            "province": c.province,
            "pic": c.pic,
            "wa": c.wa,
            "wa_group": c.wa_group,
            "reminder_target": c.reminder_target,
            "email": c.email,
            "note": c.note,
            "is_active": c.is_active,
            "total_billed": c.total_billed,
            "outstanding": c.outstanding,
            "avg_days_to_pay": c.avg_days_to_pay,
            "score": c.score,
            "risk_label": c.risk_label,
            "days_since_last_order": c.days_since_last_order,
        },
        "invoices": inv_data,
        "cls": cls_data,
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
    c.city      = data.get('city', '').strip()
    c.province  = data.get('province', '').strip()
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
