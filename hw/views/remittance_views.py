import csv

from collections import defaultdict
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
            'sudah_dikirim': sudah_dikirim,
            'mengendap': mengendap,
        })

    return result


@login_required
def remittance_list(request):
    remittances = Remittance.objects.filter(company=KONOZ).prefetch_related('lines')
    stats = _compute_stats()
    return render(request, 'hw/remittance/remittance_history.html', {
        'remittances': remittances,
        'stats': stats,
    })


@login_required
def remittance_new(request):
    if request.method == 'POST':
        remittance_date = request.POST.get('date') or str(date.today())
        note = request.POST.get('note', '').strip()
        proof = request.FILES.get('proof')

        linked_numbers = request.POST.getlist('linked_number')
        amounts = request.POST.getlist('amount_sar')
        invoice_ids = request.POST.getlist('invoice_id')

        lines_data = []
        for ln, amt, inv_id in zip(linked_numbers, amounts, invoice_ids):
            try:
                amt_val = float(amt.replace(',', '').strip()) if amt and amt.strip() else 0
            except ValueError:
                amt_val = 0
            if amt_val > 0:
                lines_data.append({'linked_number': ln, 'amount_sar': amt_val, 'invoice_id': inv_id or None})

        if not lines_data:
            reservasi = _build_reservasi_mengendap()
            return render(request, 'hw/remittance/remittance_form.html', {
                'reservasi': reservasi,
                'error': 'Masukkan minimal satu nominal untuk dikirim.',
                'today': str(date.today()),
            })

        rem = Remittance.objects.create(
            remittance_number=Remittance.generate_number(),
            company=KONOZ,
            date=remittance_date,
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

    reservasi = _build_reservasi_mengendap()
    return render(request, 'hw/remittance/remittance_form.html', {
        'reservasi': reservasi,
        'today': str(date.today()),
    })


@login_required
def remittance_detail(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    lines = rem.lines.select_related('invoice').order_by('linked_number')
    return render(request, 'hw/remittance/remittance_detail.html', {
        'rem': rem,
        'lines': lines,
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
def remittance_edit(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    if request.method == 'POST':
        rem.date = request.POST.get('date') or rem.date
        rem.note = request.POST.get('note', '').strip()
        rem.save(update_fields=['date', 'note'])
        return redirect('remittance_detail', pk=rem.pk)
    return render(request, 'hw/remittance/remittance_edit.html', {'rem': rem})


@login_required
def remittance_pdf(request, pk):
    from .helpers import _render_list_pdf
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    lines = list(rem.lines.select_related('invoice').order_by('linked_number'))
    return _render_list_pdf(
        request, rem.lines.none(),
        template='hw/remittance/remittance_pdf.html',
        filename=f'remittance_{rem.date}.pdf',
        extra_ctx={'rem': rem, 'lines': lines},
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
