"""HQ Settlement views — obligations, settlements, allocation.

New UI surface for the FASE E domain (hw/models/settlement.py). Gated under
the existing 'remittance' permission module — settlement is money movement
between branch and HQ, same sensitivity class as remittance itself (staff
read-only, manager+ can create/allocate).

Kept deliberately separate from remittance_views.py: HQObligation/
RemittanceSettlement/RemittanceAllocation are additive on top of Remittance,
not a replacement (see hw/models/settlement.py docstring).
"""
import json

from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models.branch import Branch
from ..models.remittance import Remittance
from ..models.settlement import HQObligation, RemittanceSettlement
from ..finance import settlement_service
from ..finance.errors import FinanceError
from ..permissions import require_perm
from .helpers import _parse_date, _to_float


def _obligation_props(o):
    return {
        'id': o.pk,
        'branch': o.branch_id,
        'branch_name': o.branch.name,
        'reservation_id': o.reservation_id,
        'reservation_number': o.reservation.reservation_number if o.reservation_id else None,
        'amount_sar': o.amount_sar,
        'settled_sar': o.settled_sar,
        'outstanding_sar': o.outstanding_sar,
        'status': o.status,
        'status_display': o.get_status_display(),
        'due_date': o.due_date.isoformat() if o.due_date else None,
        'note': o.note,
        'created_at': o.created_at.isoformat(),
    }


def _settlement_props(s):
    return {
        'id': s.pk,
        'remittance_id': s.remittance_id,
        'remittance_number': s.remittance.remittance_number,
        'received_amount_sar': s.received_amount_sar,
        'received_date': s.received_date.isoformat() if s.received_date else None,
        'reference': s.reference,
        'allocated_sar': s.allocated_sar,
        'unallocated_sar': s.unallocated_sar,
        'allocations': [{
            'id': a.pk,
            'obligation_id': a.hq_obligation_id,
            'obligation_branch': a.hq_obligation.branch_id,
            'amount_sar': a.amount_sar,
        } for a in s.allocations.select_related('hq_obligation')],
    }


@require_perm('remittance', 'view')
def settlement_list(request):
    obligations = HQObligation.objects.select_related('branch', 'reservation').order_by(
        'status', 'due_date', 'created_at',
    )
    settlements = RemittanceSettlement.objects.select_related('remittance').prefetch_related(
        'allocations__hq_obligation',
    ).order_by('-received_date', '-id')

    return inertia_render(request, 'Settlement/List', props={
        'obligations': [_obligation_props(o) for o in obligations],
        'settlements': [_settlement_props(s) for s in settlements],
        'branch_choices': [{'value': b.code, 'label': b.name} for b in Branch.objects.filter(is_active=True)],
        'remittance_choices': [
            {'value': r.pk, 'label': f'{r.remittance_number} ({r.date})'}
            for r in Remittance.objects.order_by('-date')[:100]
        ],
    })


@require_perm('remittance', 'edit')
def obligation_new(request):
    if request.method != 'POST':
        return redirect('settlement_list')

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    branch = Branch.objects.filter(pk=data.get('branch'), is_active=True).first()
    amount = _to_float(data.get('amount_sar'))
    if not branch or not amount:
        messages.error(request, 'Cabang dan nominal harus diisi.')
        return redirect('settlement_list')

    try:
        settlement_service.create_obligation(
            branch=branch, amount_sar=int(amount),
            due_date=_parse_date(data.get('due_date')), note=data.get('note', ''),
        )
        messages.success(request, 'Kewajiban setor baru tercatat.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('settlement_list')


@require_perm('remittance', 'edit')
def settlement_new(request):
    if request.method != 'POST':
        return redirect('settlement_list')

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    remittance = Remittance.objects.filter(pk=data.get('remittance')).first()
    amount = _to_float(data.get('received_amount_sar'))
    if not remittance or not amount:
        messages.error(request, 'Remittance dan nominal diterima harus diisi.')
        return redirect('settlement_list')

    try:
        settlement_service.add_settlement(
            remittance,
            received_amount_sar=int(amount),
            received_date=_parse_date(data.get('received_date')) or date.today(),
            created_by=request.user, reference=data.get('reference', ''),
            note=data.get('note', ''),
        )
        messages.success(request, f'Settlement untuk {remittance.remittance_number} tercatat.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('settlement_list')


@require_perm('remittance', 'edit')
def settlement_allocate(request, pk):
    settlement = get_object_or_404(RemittanceSettlement, pk=pk)
    if request.method != 'POST':
        return redirect('settlement_list')

    raw = request.POST.get('allocations', '')
    try:
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (json.JSONDecodeError, ValueError):
        rows = []

    allocations = []
    for row in rows:
        amt = _to_float(row.get('amount_sar', 0))
        if not amt or amt <= 0:
            continue
        obligation = HQObligation.objects.filter(pk=row.get('obligation_id')).first()
        if obligation is None:
            continue
        allocations.append((obligation, int(amt)))

    if not allocations:
        messages.error(request, 'Tidak ada alokasi yang valid.')
        return redirect('settlement_list')

    try:
        settlement_service.allocate_settlement(settlement, allocations, created_by=request.user)
        messages.success(request, 'Alokasi settlement tercatat.')
    except FinanceError as e:
        messages.error(request, str(e))

    return redirect('settlement_list')
