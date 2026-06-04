import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import ActivityLog, Client, ConfirmationLetter, Invoice, log_activity


def _company(request):
    return request.session.get('active_company')


@login_required
def client_list(request):
    company = _company(request)
    qs = Client.objects.filter(company=company) if company else Client.objects.all()

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(city__icontains=q) | qs.filter(pic__icontains=q)

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)

    clients = list(
        qs.order_by('name')
        .prefetch_related('invoices__payments', 'invoices__reservations', 'cls')
    )
    return render(request, 'hw/client/client_list.html', {
        'clients': clients, 'q': q, 'status': status,
    })


@login_required
def client_new(request):
    company = _company(request)
    if request.method == 'POST':
        c = Client(company=company or 'konoz')
        _save_client(c, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name, c.company)
        messages.success(request, f'Client "{c.name}" berhasil ditambahkan.')
        return redirect('client_detail', pk=c.pk)
    return render(request, 'hw/client/client_form.html', {'edit': False})


@login_required
def client_edit(request, pk):
    c = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        _before = {'Nama': c.name, 'Kota': c.city, 'Provinsi': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        _save_client(c, request.POST)
        _after  = {'Nama': c.name, 'Kota': c.city, 'Provinsi': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, c.company, changes)
        messages.success(request, f'Client "{c.name}" berhasil diupdate.')
        return redirect('client_detail', pk=c.pk)
    return render(request, 'hw/client/client_form.html', {'edit': True, 'client': c})


@login_required
@require_POST
def client_delete(request, pk):
    c = get_object_or_404(Client, pk=pk)
    name = c.name
    c.delete()
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Client', name, c.company)
    messages.success(request, f'Client "{name}" dihapus.')
    return redirect('client_list')


@login_required
def client_detail(request, pk):
    c = get_object_or_404(
        Client.objects.prefetch_related('invoices', 'cls'),
        pk=pk,
    )
    invoices = c.invoices.order_by('-created_at')
    cls = c.cls.order_by('-created_at')
    return render(request, 'hw/client/client_detail.html', {
        'client': c,
        'invoices': invoices,
        'cls': cls,
    })


@login_required
def client_map(request):
    company = _company(request)
    qs = Client.objects.filter(company=company) if company else Client.objects.all()
    qs = qs.filter(lat__isnull=False, lng__isnull=False)
    return render(request, 'hw/client/client_map.html', {'clients_count': qs.count()})


@login_required
def client_map_data(request):
    company = _company(request)
    qs = (
        Client.objects
        .filter(company=company) if company else Client.objects.all()
    )
    qs = qs.filter(lat__isnull=False, lng__isnull=False)
    qs = qs.prefetch_related('invoices__payments', 'invoices__reservations')

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
    c.email     = data.get('email', '').strip()
    c.note      = data.get('note', '').strip()
    c.is_active = data.get('is_active') == 'on'
    try: c.lat = float(data.get('lat') or 0) or None
    except (ValueError, TypeError): c.lat = None
    try: c.lng = float(data.get('lng') or 0) or None
    except (ValueError, TypeError): c.lng = None
    c.save()
