"""HQ settlement orchestration (Master Architecture v2.0 §33–39).

Jalur BARU untuk remittance yang diterima bertahap — lihat docstring
hw/models/settlement.py. Tidak menggantikan post_remittance_receive() (jalur
lama, satu tanda terima lump-sum); keduanya boleh hidup berdampingan selama
transisi, tapi satu Remittance sebaiknya konsisten pakai salah satu jalur.
"""
from django.db import transaction

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
    tidak dibukukan di sini — direkonsiliasi terpisah saat remittance
    dianggap fully settled (lihat TODO FASE I)."""
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
        company=remittance.company,
        source_type='RemittanceSettlement',
        source_id=settlement.pk,
        idempotency_key=f"settlement:{settlement.pk}:receive",
        created_by=created_by,
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
