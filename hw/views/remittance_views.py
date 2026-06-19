import csv
import json

from collections import defaultdict
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import Invoice, Payment, Remittance, RemittanceLine
from ..utils import convert_to_sar

SURABAYA_METHODS = {'cash', 'bank transfer', 'deposit'}
KONOZ = 'konoz'


def _compute_stats():
    """Hitung 5 stats remittance global untuk company Konoz."""
    from django.db.models import Sum as _Sum

    total_tagihan = int(Invoice.objects.filter(company=KONOZ).aggregate(
        t=_Sum('reservations__total_sar')
    )['t'] or 0)

    payments = Payment.objects.filter(
        invoice__company=KONOZ,
    ).values('method', 'amount', 'currency', 'exchange_rate')

    terbayar_surabaya = 0
    terbayar_pusat = 0
    for p in payments:
        sar = int(round(convert_to_sar(float(p['amount']), p['currency'], float(p['exchange_rate']))))
        if (p['method'] or '').lower() == 'direct':
            terbayar_pusat += sar
        elif (p['method'] or '').lower() in SURABAYA_METHODS:
            terbayar_surabaya += sar

    sudah_dikirim = int(RemittanceLine.objects.filter(
        remittance__company=KONOZ
    ).aggregate(total=_Sum('amount_sar'))['total'] or 0)

    mengendap = max(0, terbayar_surabaya - sudah_dikirim)
    terkirim_ke_pusat = sudah_dikirim + terbayar_pusat

    return {
        'total_tagihan': total_tagihan,
        'terkirim_ke_pusat': terkirim_ke_pusat,
        'mengendap': mengendap,
    }


def _build_reservasi_mengendap():
    from ..models import Reservation

    # Semua payments untuk Konoz
    all_payments = Payment.objects.filter(
        invoice__company=KONOZ,
    ).select_related('invoice').values(
        'linked_number', 'method', 'amount', 'currency', 'exchange_rate',
        'invoice_id', 'invoice__invoice_number', 'invoice__customer_name',
    )

    # Pool semua linked_number dengan info invoice
    pool = defaultdict(lambda: {
        'sar_sby': 0, 'sar_direct': 0,
        'invoice_id': None, 'invoice_number': '', 'customer_name': '',
    })
    for p in all_payments:
        key = p['linked_number']
        sar = int(round(convert_to_sar(float(p['amount']), p['currency'], float(p['exchange_rate']))))
        m = (p['method'] or '').lower()
        if m == 'direct':
            pool[key]['sar_direct'] += sar
        elif m in ('cash', 'bank transfer', 'deposit'):
            pool[key]['sar_sby'] += sar
        pool[key]['invoice_id'] = p['invoice_id']
        pool[key]['invoice_number'] = p['invoice__invoice_number']
        pool[key]['customer_name'] = p['invoice__customer_name']

    # Fetch reservation details (check_in, check_out, total_sar)
    res_data = Reservation.objects.filter(
        reservation_number__in=list(pool.keys()),
        invoice__company=KONOZ,
    ).values('reservation_number', 'check_in', 'check_out', 'total_sar')
    res_details = {r['reservation_number']: r for r in res_data}

    # Sudah dikirim via RemittanceLine
    lines = RemittanceLine.objects.filter(
        remittance__company=KONOZ
    ).values('linked_number').annotate(total=Sum('amount_sar'))
    remit_by_res = {l['linked_number']: int(l['total'] or 0) for l in lines}

    result = []
    for linked_number, data in sorted(pool.items(), key=lambda x: (res_details.get(x[0], {}).get('check_in') or date.max)):
        terbayar_sby = data['sar_sby']
        terbayar_direct = data['sar_direct']
        remit_amount = remit_by_res.get(linked_number, 0)
        sudah_dikirim = remit_amount + terbayar_direct
        mengendap = max(0, terbayar_sby - remit_amount)
        rd = res_details.get(linked_number, {})
        result.append({
            'linked_number': linked_number,
            'invoice_id': data['invoice_id'],
            'invoice_number': data['invoice_number'],
            'customer_name': data['customer_name'],
            'check_in': rd.get('check_in'),
            'check_out': rd.get('check_out'),
            'total_sar': rd.get('total_sar', 0),
            'terbayar_sby': terbayar_sby,
            'terbayar_direct': terbayar_direct,
            'terbayar_total': terbayar_sby + terbayar_direct,
            'sudah_dikirim': sudah_dikirim,
            'mengendap': mengendap,
        })

    return result


def _serialize_reservasi():
    """Reservasi mengendap dengan tanggal yang sudah diformat untuk props Inertia."""
    rows = _build_reservasi_mengendap()
    for r in rows:
        ci = r.get('check_in')
        co = r.get('check_out')
        r['check_in'] = ci.strftime('%d/%m/%Y') if ci else None
        r['check_out'] = co.strftime('%d/%m/%Y') if co else None
    return rows


@login_required
def remittance_list(request):
    from django.db.models import Q
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    qs = Remittance.objects.filter(company=KONOZ).prefetch_related('lines').order_by('-date')
    if status_filter in ('pending', 'received'):
        qs = qs.filter(status=status_filter)
    if q:
        qs = qs.filter(
            Q(remittance_number__icontains=q) |
            Q(receipt_reference__icontains=q) |
            Q(note__icontains=q)
        )
    stats = _compute_stats()
    remittances = [{
        "id": rem.id,
        "remittance_number": rem.remittance_number,
        "date": rem.date.strftime("%d/%m/%Y"),
        "total_sar": rem.total_sar,
        "status": rem.status,
        "proof_url": rem.proof.url if rem.proof else None,
    } for rem in qs]
    return inertia_render(request, "Remittance/List", props={
        "remittances": remittances,
        "stats": stats,
        "status_filter": status_filter,
        "q": q,
        "total_count": Remittance.objects.filter(company=KONOZ).count(),
    })


@login_required
def remittance_new(request):
    if request.method == 'POST':
        remittance_date = request.POST.get('date') or str(date.today())
        receipt_reference = request.POST.get('receipt_reference', '').strip()
        note = request.POST.get('note', '').strip()
        proof = request.FILES.get('proof')

        try:
            raw_lines = json.loads(request.POST.get('lines', '[]'))
        except (ValueError, TypeError):
            raw_lines = []

        lines_data = []
        for ld in raw_lines:
            try:
                amt_val = float(ld.get('amount_sar') or 0)
            except (ValueError, TypeError):
                amt_val = 0
            if amt_val > 0:
                lines_data.append({
                    'linked_number': ld.get('linked_number'),
                    'amount_sar': amt_val,
                    'invoice_id': ld.get('invoice_id') or None,
                })

        if not lines_data:
            return inertia_render(request, "Remittance/Form", props={
                'reservasi': _serialize_reservasi(),
                'error': 'Masukkan minimal satu nominal untuk dikirim.',
                'today': str(date.today()),
            })

        rem = Remittance.objects.create(
            remittance_number=Remittance.generate_number(),
            company=KONOZ,
            date=remittance_date,
            receipt_reference=receipt_reference,
            note=note,
        )
        if proof:
            rem.proof = proof
            rem.save()

        for ld in lines_data:
            RemittanceLine.objects.create(
                remittance=rem,
                invoice_id=ld['invoice_id'],
                linked_number=ld['linked_number'],
                amount_sar=ld['amount_sar'],
            )

        return redirect('remittance_detail', pk=rem.pk)

    return inertia_render(request, "Remittance/Form", props={
        'reservasi': _serialize_reservasi(),
        'today': str(date.today()),
    })


@login_required
def remittance_detail(request, pk):
    from ..models import Reservation
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    lines = list(rem.lines.select_related('invoice').order_by('linked_number'))

    linked_numbers = [l.linked_number for l in lines]

    # Reservation data (check_in, hotel)
    res_map = {
        r['reservation_number']: r
        for r in Reservation.objects.filter(reservation_number__in=linked_numbers).values('reservation_number', 'check_in', 'hotel')
    }

    # Total previously sent (other remittances)
    prev_map = {}
    for row in RemittanceLine.objects.filter(
        linked_number__in=linked_numbers
    ).exclude(remittance=rem).values('linked_number').annotate(total=Sum('amount_sar')):
        prev_map[row['linked_number']] = int(row['total'] or 0)

    enriched = []
    for line in lines:
        res = res_map.get(line.linked_number, {})
        ci = res.get('check_in')
        enriched.append({
            'linked_number': line.linked_number,
            'amount_sar': int(line.amount_sar),
            'check_in': ci.strftime("%d/%m/%Y") if ci else None,
            'hotel': res.get('hotel') or '—',
            'prev_sent': prev_map.get(line.linked_number, 0),
            'invoice': {
                'pk': line.invoice.pk,
                'invoice_number': line.invoice.invoice_number,
                'customer_name': line.invoice.customer_name,
            } if line.invoice_id else None,
        })

    return inertia_render(request, "Remittance/Detail", props={
        "rem": {
            "remittance_number": rem.remittance_number,
            "date": rem.date.strftime("%d/%m/%Y"),
            "status": rem.status,
            "proof_url": rem.proof.url if rem.proof else None,
            "receipt_reference": rem.receipt_reference,
            "note": rem.note,
            "total_sar": rem.total_sar,
        },
        "lines": enriched,
    })


@login_required
def remittance_export_csv(request):
    remittances = Remittance.objects.filter(company=KONOZ).prefetch_related('lines__invoice')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="remittance.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tanggal', 'Total SAR', 'Note', 'Res#', 'Invoice', 'Amount SAR'])
    for rem in remittances:
        lines = list(rem.lines.all())
        if lines:
            for i, line in enumerate(lines):
                writer.writerow([
                    rem.date.strftime('%d/%m/%Y') if i == 0 else '',
                    rem.total_sar if i == 0 else '',
                    rem.note if i == 0 else '',
                    line.linked_number,
                    line.invoice.invoice_number if line.invoice else '',
                    line.amount_sar,
                ])
        else:
            writer.writerow([rem.date.strftime('%d/%m/%Y'), rem.total_sar, rem.note, '', '', ''])
    return response


@login_required
@require_POST
def remittance_mark_received(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    if rem.status != Remittance.STATUS_RECEIVED:
        rem.status = Remittance.STATUS_RECEIVED
        rem.save(update_fields=['status'])
    return redirect('remittance_list')


@login_required
def remittance_edit(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    if rem.status == Remittance.STATUS_RECEIVED:
        return redirect('remittance_detail', pk=rem.pk)
    if request.method == 'POST':
        rem.date = request.POST.get('date') or rem.date
        rem.status = request.POST.get('status', rem.status)
        rem.receipt_reference = request.POST.get('receipt_reference', '').strip()
        rem.note = request.POST.get('note', '').strip()
        update_fields = ['date', 'status', 'receipt_reference', 'note']
        if request.POST.get('remove_proof'):
            rem.proof = None
            update_fields.append('proof')
        elif request.FILES.get('proof'):
            rem.proof = request.FILES['proof']
            update_fields.append('proof')
        rem.save(update_fields=update_fields)

        try:
            raw_lines = json.loads(request.POST.get('lines', '[]'))
        except (ValueError, TypeError):
            raw_lines = []
        for ld in raw_lines:
            try:
                amt_val = float(ld.get('amount_sar') or 0)
            except (ValueError, TypeError):
                amt_val = 0
            RemittanceLine.objects.filter(pk=ld.get('line_id'), remittance=rem).update(amount_sar=amt_val)

        return redirect('remittance_detail', pk=rem.pk)

    lines = list(rem.lines.select_related('invoice').order_by('linked_number'))
    return inertia_render(request, "Remittance/Edit", props={
        "rem": {
            "id": rem.id,
            "remittance_number": rem.remittance_number,
            "date": rem.date.strftime("%Y-%m-%d"),
            "receipt_reference": rem.receipt_reference or "",
            "status": rem.status,
            "note": rem.note or "",
            "proof_url": rem.proof.url if rem.proof else None,
        },
        "lines": [{
            "line_id": l.pk,
            "linked_number": l.linked_number,
            "amount_sar": int(l.amount_sar or 0),
            "invoice": {
                "pk": l.invoice.pk,
                "invoice_number": l.invoice.invoice_number,
                "customer_name": l.invoice.customer_name,
            } if l.invoice_id else None,
        } for l in lines],
    })


@login_required
def remittance_pdf(request, pk):
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url
    from ..models import Reservation
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    raw_lines = list(rem.lines.select_related('invoice').order_by('linked_number'))
    linked_numbers = [l.linked_number for l in raw_lines]

    res_map = {
        r['reservation_number']: r
        for r in Reservation.objects.filter(reservation_number__in=linked_numbers).values('reservation_number', 'check_in', 'hotel')
    }
    prev_map = {}
    for row in RemittanceLine.objects.filter(
        linked_number__in=linked_numbers
    ).exclude(remittance=rem).values('linked_number').annotate(total=Sum('amount_sar')):
        prev_map[row['linked_number']] = int(row['total'] or 0)

    lines = [{'line': l, 'check_in': res_map.get(l.linked_number, {}).get('check_in'), 'hotel': res_map.get(l.linked_number, {}).get('hotel', '—'), 'prev_sent': prev_map.get(l.linked_number, 0)} for l in raw_lines]

    return _render_list_pdf(
        request, rem.lines.none(),
        template='hw/remittance/remittance_pdf.html',
        filename=f'remittance_{rem.date}.pdf',
        extra_ctx={'rem': rem, 'lines': lines, 'logo_url': _logo_file_url('konoz')},
    )


@login_required
@require_POST
def remittance_upload_proof(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    proof = request.FILES.get('proof')
    if proof:
        rem.proof = proof
        rem.save(update_fields=['proof'])
    return redirect('remittance_detail', pk=rem.pk)


@login_required
@require_POST
def remittance_delete(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    rem.delete()
    return redirect('remittance_list')


@login_required
def remittance_recap(request):
    remittances = Remittance.objects.filter(company=KONOZ).prefetch_related('lines').order_by('-date')
    monthly = {}
    for rem in remittances:
        key = rem.date.strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {
                'label': rem.date.strftime('%B %Y'),
                'period': key,
                'remittances': [],
                'total_sent': 0,
                'total_pending': 0,
                'total_received': 0,
                'count_pending': 0,
                'count_received': 0,
            }
        monthly[key]['remittances'].append({
            'id': rem.id,
            'remittance_number': rem.remittance_number,
            'date': rem.date.strftime('%d/%m/%Y'),
            'lines_count': len(rem.lines.all()),
            'status': rem.status,
            'total_sar': rem.total_sar,
        })
        amt = int(rem.total_sar or 0)
        monthly[key]['total_sent'] += amt
        if rem.status == Remittance.STATUS_RECEIVED:
            monthly[key]['total_received'] += amt
            monthly[key]['count_received'] += 1
        else:
            monthly[key]['total_pending'] += amt
            monthly[key]['count_pending'] += 1
    return inertia_render(request, "Remittance/Recap", props={
        "monthly": list(monthly.values()),
    })


@login_required
def remittance_period_pdf(request):
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url
    month = request.GET.get('month', '')
    if not month:
        return redirect('remittance_recap')
    try:
        from datetime import datetime
        period_dt = datetime.strptime(month, '%Y-%m')
    except ValueError:
        return redirect('remittance_recap')

    remittances = Remittance.objects.filter(
        company=KONOZ,
        date__year=period_dt.year,
        date__month=period_dt.month,
    ).prefetch_related('lines').order_by('date')

    total_sent = sum(int(r.total_sar or 0) for r in remittances)
    total_pending = sum(int(r.total_sar or 0) for r in remittances if r.status == Remittance.STATUS_PENDING)
    total_received = sum(int(r.total_sar or 0) for r in remittances if r.status == Remittance.STATUS_RECEIVED)

    filename = f'remittance_recap_{month}.pdf'
    return _render_list_pdf(
        request, Remittance.objects.none(),
        template='hw/remittance/remittance_period_pdf.html',
        filename=filename,
        extra_ctx={
            'remittances': remittances,
            'period_label': period_dt.strftime('%B %Y'),
            'total_sent': total_sent,
            'total_pending': total_pending,
            'total_received': total_received,
            'logo_url': _logo_file_url('konoz'),
        },
    )
