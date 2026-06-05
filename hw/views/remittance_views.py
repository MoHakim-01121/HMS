from collections import defaultdict
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import Payment, Remittance, RemittanceLine
from ..utils import convert_to_sar

SURABAYA_METHODS = {'cash', 'bank transfer', 'deposit'}
KONOZ = 'konoz'


def _compute_stats():
    """Hitung stats remittance global untuk company Konoz."""
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
    ).aggregate(total=Sum('amount_sar'))['total'] or 0)

    mengendap = max(0, terbayar_surabaya - sudah_dikirim)

    return {
        'terbayar_surabaya': terbayar_surabaya,
        'terbayar_pusat': terbayar_pusat,
        'sudah_dikirim': sudah_dikirim,
        'mengendap': mengendap,
    }


def _build_reservasi_mengendap():
    """
    Kembalikan list dict reservasi yang masih punya saldo mengendap di Surabaya.
    Setiap dict: linked_number, invoice_id, invoice_number, customer_name,
                 terbayar_sby, sudah_dikirim, mengendap
    """
    # Aggregate terbayar Surabaya per linked_number
    payments = Payment.objects.filter(
        invoice__company=KONOZ,
        method__in=['Cash', 'Bank Transfer', 'Deposit'],
    ).select_related('invoice').values(
        'linked_number', 'amount', 'currency', 'exchange_rate',
        'invoice_id', 'invoice__invoice_number', 'invoice__customer_name',
    )

    terbayar_by_res = defaultdict(lambda: {'sar': 0, 'invoice_id': None, 'invoice_number': '', 'customer_name': ''})
    for p in payments:
        key = p['linked_number']
        sar = int(round(convert_to_sar(float(p['amount']), p['currency'], float(p['exchange_rate']))))
        terbayar_by_res[key]['sar'] += sar
        terbayar_by_res[key]['invoice_id'] = p['invoice_id']
        terbayar_by_res[key]['invoice_number'] = p['invoice__invoice_number']
        terbayar_by_res[key]['customer_name'] = p['invoice__customer_name']

    # Aggregate sudah dikirim per linked_number
    lines = RemittanceLine.objects.filter(
        remittance__company=KONOZ
    ).values('linked_number').annotate(total=Sum('amount_sar'))
    sudah_by_res = {l['linked_number']: int(l['total'] or 0) for l in lines}

    result = []
    for linked_number, data in sorted(terbayar_by_res.items()):
        sudah = sudah_by_res.get(linked_number, 0)
        mengendap = data['sar'] - sudah
        if mengendap > 0:
            result.append({
                'linked_number': linked_number,
                'invoice_id': data['invoice_id'],
                'invoice_number': data['invoice_number'],
                'customer_name': data['customer_name'],
                'terbayar_sby': data['sar'],
                'sudah_dikirim': sudah,
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
@require_POST
def remittance_delete(request, pk):
    rem = get_object_or_404(Remittance, pk=pk, company=KONOZ)
    rem.delete()
    return redirect('remittance_list')
