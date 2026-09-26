"""HQ receipt actions for a remittance (staged receipt — FASE E domain,
hw/models/settlement.py).

Tidak ada halaman daftar sendiri: penerimaan pusat dikelola dari Remittance
(row action di list + detail), karena settlement selalu milik satu remittance.
Form Catat Penerimaan (Remittance/Receipt, dibuka di modal) sekaligus tempat
mengalokasikan uang yang diterima ke reservasi.
Gated under the existing 'remittance' permission module — money movement
between branch and HQ, same sensitivity class as remittance itself (staff
read-only, manager+ can create).
"""
import json

from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models.remittance import Remittance
from ..models.settlement import RemittanceSettlement
from ..finance import remittance_allocation, settlement_service
from ..finance.errors import FinanceError
from ..permissions import require_perm
from .helpers import _parse_date, _to_float


def _safe_next(data, fallback):
    """Redirect ke `next` kalau path lokal yang valid (Record Receipt dari
    list kembali ke list, dari detail kembali ke detail). `data` = body yang
    sudah di-parse: Inertia mengirim JSON, jadi request.POST kosong."""
    next_url = data.get('next') or ''
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)
    return redirect(fallback)


def _request_data(request):
    try:
        return json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        return request.POST


def _allocation_payload(raw):
    """Payload alokasi: list (Inertia JSON) atau string JSON (form biasa)."""
    if raw in (None, ''):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise FinanceError('Format alokasi tidak valid') from None
    if not isinstance(raw, list):
        raise FinanceError('Format alokasi tidak valid')
    return raw


def _receipt_props(remittance, *, settlement=None, next_url='', form=None, error=None):
    """Props halaman Remittance/Receipt: catat penerimaan baru, atau ubah
    alokasi satu penerimaan (`settlement` terisi)."""
    basis = remittance.settlement_basis_sar
    settled = remittance.settled_sar
    rows = remittance_allocation.candidates(remittance, settlement)
    if form is None:
        if settlement is not None:
            form = {
                'received_amount_sar': settlement.received_amount_sar,
                'received_date': settlement.received_date.isoformat(),
                'reference': settlement.reference,
                'allocations': [
                    {'linked_number': l.linked_number, 'invoice_id': l.invoice_id, 'amount_sar': int(l.amount_sar)}
                    for l in settlement.allocations.all()
                ],
            }
        else:
            form = {
                'received_amount_sar': max((basis or 0) - settled, 0) or '',
                'received_date': date.today().isoformat(),
                'reference': '',
                'allocations': None,
            }
    return {
        'rem': {
            'id': remittance.pk,
            'remittance_number': remittance.remittance_number,
            'date': remittance.date.strftime('%d/%m/%Y'),
            'amount_idr': remittance.amount_idr,
            'exchange_rate': float(remittance.exchange_rate) if remittance.exchange_rate else None,
            'expected_sar': remittance.expected_sar,
            'basis_sar': basis,
            'settled_sar': settled,
            'remaining_to_allocate': remittance_allocation.remaining_to_allocate(remittance, settlement),
            'can_allocate': remittance.expected_sar is not None,
        },
        'settlement': {
            'id': settlement.pk,
            'received_amount_sar': settlement.received_amount_sar,
            'received_date': settlement.received_date.strftime('%d/%m/%Y'),
        } if settlement else None,
        'candidates': [{
            'linked_number': r['linked_number'],
            'invoice_id': r['invoice_id'],
            'invoice_number': r['invoice_number'],
            'customer_name': r['customer_name'] or '',
            'hotel': r['hotel'] or '',
            'check_in': r['check_in'].strftime('%d/%m/%Y') if r['check_in'] else None,
            'total_sar': int(r['total_sar'] or 0),
            'paid_sar': int(r['terbayar_total'] or 0),
            'available': r['available'],
            'current': r['current'],
            'paid_in_full': r['paid_in_full'],
        } for r in rows],
        'form': form,
        'error': error,
        'next': next_url,
    }


def _receipt_failed(request, data, remittance, error, *, settlement=None, fallback):
    """Inertia (modal): tampilkan ulang form beserta isian + pesan error,
    supaya alokasi yang sudah diketik tidak hilang. Non-Inertia: redirect."""
    if not request.headers.get('X-Inertia'):
        messages.error(request, error)
        return _safe_next(data, fallback)
    try:
        allocations = _allocation_payload(data.get('allocations'))
    except FinanceError:
        allocations = []
    form = {
        'received_amount_sar': data.get('received_amount_sar', ''),
        'received_date': data.get('received_date', ''),
        'reference': data.get('reference', ''),
        'allocations': allocations,
    }
    return inertia_render(request, 'Remittance/Receipt', props=_receipt_props(
        remittance, settlement=settlement, next_url=data.get('next', ''), form=form, error=error,
    ))


@require_perm('remittance', 'edit')
def remittance_record_receipt(request, pk):
    from .remittance_views import _can_record_receipt

    remittance = get_object_or_404(Remittance, pk=pk)
    fallback = f'/remittance/{pk}/'
    if request.method != 'POST':
        if not _can_record_receipt(remittance):
            messages.error(request, f'Penerimaan {remittance.remittance_number} tidak bisa dicatat lagi.')
            return redirect('remittance_detail', pk=pk)
        return inertia_render(request, 'Remittance/Receipt', props=_receipt_props(
            remittance, next_url=request.GET.get('next', ''),
        ))

    data = _request_data(request)
    amount = int(round(_to_float(data.get('received_amount_sar')) or 0))
    if not amount:
        return _receipt_failed(request, data, remittance, 'Nominal diterima harus diisi.', fallback=fallback)
    raw_date = data.get('received_date')
    received_date = _parse_date(raw_date) if raw_date else date.today()
    if received_date is None:
        return _receipt_failed(request, data, remittance, 'Tanggal diterima tidak valid.', fallback=fallback)

    try:
        settlement_service.add_settlement(
            remittance,
            received_amount_sar=amount,
            received_date=received_date,
            created_by=request.user, reference=data.get('reference', ''),
            note=data.get('note', ''),
            allocations=_allocation_payload(data.get('allocations')),
        )
    except FinanceError as e:
        return _receipt_failed(request, data, remittance, str(e), fallback=fallback)

    messages.success(request, f'Penerimaan {remittance.remittance_number} tercatat.')
    return _safe_next(data, fallback)


@require_perm('remittance', 'edit')
def remittance_receipt_allocation(request, pk, sid):
    """Ubah alokasi satu penerimaan: koreksi, atau alokasi susulan untuk uang
    yang sudah diterima tapi belum dibagikan ke reservasi."""
    remittance = get_object_or_404(Remittance, pk=pk)
    settlement = get_object_or_404(RemittanceSettlement, pk=sid, remittance=remittance)
    fallback = f'/remittance/{pk}/'
    if request.method != 'POST':
        return inertia_render(request, 'Remittance/Receipt', props=_receipt_props(
            remittance, settlement=settlement, next_url=request.GET.get('next', ''),
        ))

    data = _request_data(request)
    try:
        settlement_service.set_settlement_allocations(
            settlement, _allocation_payload(data.get('allocations')), created_by=request.user,
        )
    except FinanceError as e:
        return _receipt_failed(request, data, remittance, str(e), settlement=settlement, fallback=fallback)

    messages.success(request, f'Alokasi penerimaan {remittance.remittance_number} disimpan.')
    return _safe_next(data, fallback)


@require_perm('remittance', 'delete')
@require_POST
def remittance_receipt_delete(request, pk, sid):
    """Hapus penerimaan yang salah catat (lihat settlement_service.delete_settlement)."""
    remittance = get_object_or_404(Remittance, pk=pk)
    settlement = get_object_or_404(RemittanceSettlement, pk=sid, remittance=remittance)
    try:
        settlement_service.delete_settlement(settlement, created_by=request.user)
        messages.success(request, f'Penerimaan {remittance.remittance_number} dihapus.')
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('remittance_detail', pk=pk)


@require_perm('remittance', 'edit')
def remittance_close_diff(request, pk):
    """Book the basis-vs-received difference (bank fee/FX) once no further
    receipt is expected, and mark the remittance received."""
    remittance = get_object_or_404(Remittance, pk=pk)
    if request.method != 'POST':
        return redirect('remittance_detail', pk=pk)

    try:
        settlement_service.close_remittance_diff(remittance, created_by=request.user)
        messages.success(request, f'Selisih {remittance.remittance_number} dibukukan.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('remittance_detail', pk=pk)


@require_perm('remittance', 'edit')
@require_POST
def remittance_reopen_diff(request, pk):
    """Undo a closed difference (reverse its entry) so receipts can be
    corrected again; the remittance drops back to pending if it is short."""
    remittance = get_object_or_404(Remittance, pk=pk)
    try:
        settlement_service.reopen_remittance_diff(remittance, created_by=request.user)
        messages.success(request, f'Selisih {remittance.remittance_number} dibuka kembali.')
    except FinanceError as e:
        messages.error(request, str(e))
    return redirect('remittance_detail', pk=pk)
