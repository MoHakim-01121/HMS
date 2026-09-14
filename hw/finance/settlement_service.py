"""HQ settlement orchestration (Master Architecture v2.0 §33–39).

Jalur BARU untuk remittance yang diterima bertahap — lihat docstring
hw/models/settlement.py. Tidak menggantikan post_remittance_receive() (jalur
lama, satu tanda terima lump-sum); keduanya boleh hidup berdampingan selama
transisi, tapi satu Remittance sebaiknya konsisten pakai salah satu jalur.
"""
from django.db import models, transaction
from django.utils import timezone

from ..models.journal import JournalEntry
from ..models.settlement import HQObligation, RemittanceAllocation, RemittanceSettlement
from . import accounts as coa
from .errors import FinanceError
from .posting import post_entry


@transaction.atomic
def create_obligation(*, branch, amount_sar, reservation=None, due_date=None, note=''):
    """Catat kewajiban cabang→pusat. Tidak memposting jurnal sendiri — kas
    yang terkumpul di cabang sudah tercermin lewat charge/payment journal;
    ini murni tracking kewajiban setor."""
    if amount_sar <= 0:
        raise FinanceError('amount_sar harus > 0')
    return HQObligation.objects.create(
        branch=branch, reservation=reservation, amount_sar=amount_sar,
        due_date=due_date, note=note,
    )


@transaction.atomic
def add_settlement(remittance, *, received_amount_sar, received_date, created_by=None,
                   reference='', note=''):
    """Catat satu tanda terima aktual pusat untuk remittance ini.

    Dr Kas Pusat / Cr Kas Dalam Perjalanan (Transit), sebesar nominal yang
    BENAR-BENAR diterima. Selisih terhadap expected_sar (biaya transfer/FX)
    tidak dibukukan di sini — pakai close_remittance_diff() terpisah saat
    remittance dianggap fully settled."""
    if received_amount_sar <= 0:
        raise FinanceError('received_amount_sar harus > 0')

    settlement = RemittanceSettlement.objects.create(
        remittance=remittance, received_amount_sar=received_amount_sar,
        received_date=received_date, reference=reference, note=note,
        created_by=created_by,
    )
    post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=f"Settlement {remittance.remittance_number} — {received_amount_sar:,} SAR",
        entry_date=received_date,
        lines=[
            {'account': coa.CASH_PUSAT, 'debit': received_amount_sar, 'branch': 'pusat',
             'remittance': remittance.pk},
            {'account': coa.TRANSIT, 'credit': received_amount_sar, 'remittance': remittance.pk},
        ],
        source_type='RemittanceSettlement',
        source_id=settlement.pk,
        idempotency_key=f"settlement:{settlement.pk}:receive",
        created_by=created_by,
    )

    from ..models.bank import CashAccount
    from .bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=CashAccount.objects.filter(branch_id='pusat', is_active=True).first(),
        direction='in', amount_sar=received_amount_sar,
        source_type='RemittanceSettlement', source_id=settlement.pk,
        transaction_date=received_date, reference=reference,
    )
    return settlement


@transaction.atomic
def allocate_settlement(settlement, allocations, *, created_by=None):
    """Bagi satu settlement ke satu/banyak HQObligation.

    allocations: iterable (HQObligation, amount_sar). Analitik saja — TIDAK
    memposting jurnal baru (uang sudah masuk lewat add_settlement); ini cuma
    menandai kewajiban mana yang tertutup."""
    allocations = list(allocations)
    total = sum(int(a) for _, a in allocations)
    if total > settlement.unallocated_sar:
        raise FinanceError(
            f"Alokasi {total:,} melebihi sisa settlement {settlement.unallocated_sar:,}"
        )
    rows = []
    obligations = []
    for obligation, amt in allocations:
        if int(amt) <= 0:
            continue
        rows.append(RemittanceAllocation(settlement=settlement, hq_obligation=obligation, amount_sar=int(amt)))
        obligations.append(obligation)
    RemittanceAllocation.objects.bulk_create(rows)
    for obligation in obligations:
        obligation.status = obligation.derive_status()
        obligation.save(update_fields=['status'])
    return rows


@transaction.atomic
def close_remittance_diff(remittance, *, created_by=None, entry_date=None):
    """Bukukan selisih expected_sar vs Σ RemittanceSettlement.received_amount_sar
    sekali, saat remittance dianggap selesai diterima (biaya transfer/FX —
    v2.0 §46). Panggil paling banyak sekali per remittance; panggilan kedua
    tanpa reversal manual ditolak (bukan idempotent-by-content seperti
    post_entry lain — perbedaan bisa disengaja butuh review manusia)."""
    from ..models.journal import JournalEntry as _JE

    expected = remittance.expected_sar
    if expected is None:
        raise FinanceError(
            'Remittance ini tidak punya amount_idr/exchange_rate — expected_sar tak terhitung'
        )
    reversed_ids = _JE.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
    if _JE.objects.filter(
        reference_type='RemittanceDiff', reference_id=remittance.pk, is_reversal=False,
    ).exclude(pk__in=reversed_ids).exists():
        raise FinanceError(
            'Selisih remittance ini sudah pernah dibukukan — reverse entry lama dulu untuk mengoreksi'
        )

    received_total = remittance.settlements.aggregate(
        t=models.Sum('received_amount_sar'),
    )['t'] or 0
    diff = expected - received_total
    if diff == 0:
        return None

    entry_date = entry_date or timezone.now().date()
    if diff > 0:
        lines = [
            {'account': coa.EXP_BANKFEE, 'debit': diff, 'branch': 'pusat', 'remittance': remittance.pk},
            {'account': coa.TRANSIT, 'credit': diff, 'remittance': remittance.pk},
        ]
        desc = f"Biaya transfer/selisih kurs {remittance.remittance_number}"
    else:
        lines = [
            {'account': coa.TRANSIT, 'debit': -diff, 'remittance': remittance.pk},
            {'account': coa.INC_FX_GAIN, 'credit': -diff, 'branch': 'pusat', 'remittance': remittance.pk},
        ]
        desc = f"Laba selisih kurs {remittance.remittance_number}"

    return post_entry(
        entry_type=JournalEntry.TYPE_REMITTANCE,
        description=desc,
        entry_date=entry_date,
        lines=lines,
        source_type='RemittanceDiff',
        source_id=remittance.pk,
        idempotency_key=f"remittance:{remittance.pk}:settlement-diff",
        created_by=created_by,
    )
