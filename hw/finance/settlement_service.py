"""Penerimaan Pusat atas setoran cabang (skema target 3.6).

Jalur penerimaan pusat untuk remittance — satu transfer boleh diterima dalam
beberapa tanda terima (RemittanceSettlement). Jalur lama
post_remittance_receive() (received_amount_sar manual, satu lump-sum) tetap
dipertahankan untuk remittance lama yang sudah memakainya; satu Remittance
HARUS konsisten pakai salah satu jalur — ditegakkan di sini (add_settlement)
dan di remittance_mark_received/remittance_edit
(hw/views/remittance_views.py).

`Remittance.status` adalah satu-satunya penanda "sudah diterima penuh" yang
dibaca UI, filter list, rekap, dan PDF. Untuk jalur settlement, status itu
TIDAK diisi manual — disinkronkan di sini: jadi 'received' begitu Σ settlement
mencapai basisnya, atau selisihnya ditutup (sisa dianggap biaya/FX).
"""
from django.db import transaction
from django.utils import timezone

from ..models.journal import JournalEntry
from ..models.remittance import Remittance
from ..models.settlement import RemittanceSettlement
from . import accounts as coa
from . import remittance_allocation
from .errors import FinanceError
from .posting import post_entry, reverse_entry


def diff_is_closed(remittance):
    """True kalau selisih remittance ini sudah dibukukan (dan belum di-reverse)."""
    return bool(_live_diff_entries(remittance))


def _live_diff_entries(remittance):
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
    return list(
        JournalEntry.objects.filter(
            reference_type='RemittanceDiff', reference_id=remittance.pk, is_reversal=False,
        ).exclude(pk__in=reversed_ids)
    )


@transaction.atomic
def add_settlement(remittance, *, received_amount_sar, received_date, created_by=None,
                   reference='', note='', allocations=None):
    """Catat satu tanda terima aktual pusat untuk remittance ini.

    Dr Kas Pusat / Cr Kas Dalam Perjalanan (Transit), sebesar nominal yang
    BENAR-BENAR diterima. Selisih terhadap settlement_basis_sar (biaya
    transfer/FX) tidak dibukukan di sini — pakai close_remittance_diff()
    kalau tidak ada lagi yang akan datang.

    `allocations` (opsional): [{linked_number, amount_sar, invoice_id?}] —
    bagian uang ini milik reservasi mana (lihat remittance_allocation).
    Validasi gagal → FinanceError, penerimaan ikut batal."""
    remittance = Remittance.objects.select_for_update().get(pk=remittance.pk)
    validated = remittance_allocation.validate(remittance, allocations)
    if received_amount_sar <= 0:
        raise FinanceError('received_amount_sar harus > 0')
    if remittance.status == Remittance.STATUS_RECEIVED:
        raise FinanceError(
            f'Remittance {remittance.remittance_number} sudah diterima penuh — '
            'tidak ada penerimaan lagi yang bisa dicatat.'
        )

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
            {'account': remittance.to_account.ledger_account_id, 'debit': received_amount_sar,
             'branch': remittance.to_account.branch_id, 'remittance': remittance.pk},
            {'account': coa.TRANSIT, 'credit': received_amount_sar, 'remittance': remittance.pk},
        ],
        source_type='RemittanceSettlement',
        source_id=settlement.pk,
        idempotency_key=f"settlement:{settlement.pk}:receive",
        created_by=created_by,
    )

    from .bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=remittance.to_account,
        direction='in', amount_sar=received_amount_sar, currency='SAR', amount=received_amount_sar,
        source_type='RemittanceSettlement', source_id=settlement.pk,
        transaction_date=received_date, reference=reference,
    )
    remittance_allocation.create_lines(settlement, validated)
    remittance_allocation.post_allocation(
        settlement, validated, entry_date=received_date, created_by=created_by,
    )
    return settlement


@transaction.atomic
def set_settlement_allocations(settlement, allocations, *, created_by=None, entry_date=None):
    """Ganti alokasi satu penerimaan (koreksi / alokasi susulan).

    Entry reklasifikasi lama di-reverse dan diposting ulang bertanggal
    `entry_date` (default hari ini) — bukan tanggal transfer, jadi periode lama
    yang sudah ditutup tidak menghalangi koreksi."""
    settlement = RemittanceSettlement.objects.select_for_update().select_related('remittance').get(
        pk=settlement.pk,
    )
    remittance = Remittance.objects.select_for_update().get(pk=settlement.remittance_id)
    validated = remittance_allocation.validate(remittance, allocations, settlement=settlement)
    entry_date = entry_date or timezone.now().date()
    for entry in remittance_allocation.live_allocation_entries(settlement):
        reverse_entry(entry, reversal_date=entry_date, created_by=created_by)
    settlement.allocations.all().delete()
    remittance_allocation.create_lines(settlement, validated)
    remittance_allocation.post_allocation(
        settlement, validated, entry_date=entry_date, created_by=created_by,
    )
    return settlement


@transaction.atomic
def delete_settlement(settlement, *, created_by=None, entry_date=None):
    """Hapus satu penerimaan yang salah catat.

    Jurnal terima dan alokasinya di-reverse bertanggal `entry_date` (default
    hari ini) -- jejak audit tetap di jurnal. Baris penerimaan, alokasinya, dan
    log BankTransaction-nya dihapus, lalu status remittance diturunkan lagi
    kalau tidak lagi diterima penuh. Ditolak kalau selisih transfer sudah
    ditutup (nominal selisih dihitung dari penerimaan ini) atau transaksinya
    sudah dicocokkan dengan mutasi bank."""
    from ..models.bank_transaction import BankTransaction
    from .posting import _live_entries

    settlement = RemittanceSettlement.objects.select_for_update().get(pk=settlement.pk)
    remittance = Remittance.objects.select_for_update().get(pk=settlement.remittance_id)
    if diff_is_closed(remittance):
        raise FinanceError(
            f'Selisih {remittance.remittance_number} sudah ditutup — penerimaan tidak bisa dihapus. '
            'Buka kembali selisihnya dulu (Reopen Difference di detail remittance).'
        )
    bank_tx = BankTransaction.objects.filter(
        source_type='RemittanceSettlement', source_id=settlement.pk,
    ).first()
    if bank_tx and (bank_tx.status == BankTransaction.STATUS_RECONCILED or bank_tx.statement_lines.exists()):
        raise FinanceError(
            f'Penerimaan {remittance.remittance_number} sudah direkonsiliasi dengan mutasi bank — '
            'batalkan pencocokannya dulu.'
        )

    entry_date = entry_date or timezone.now().date()
    entries = (
        _live_entries('RemittanceSettlement', settlement.pk, JournalEntry.TYPE_REMITTANCE)
        + remittance_allocation.live_allocation_entries(settlement)
    )
    for entry in entries:
        reverse_entry(
            entry, reversal_date=entry_date, created_by=created_by,
            note=f'Penerimaan {remittance.remittance_number} dihapus',
        )
    settlement.allocations.all().delete()
    if bank_tx:
        bank_tx.delete()
    settlement.delete()


@transaction.atomic
def reopen_remittance_diff(remittance, *, created_by=None, entry_date=None):
    """Batalkan penutupan selisih: reverse entry selisihnya (bertanggal
    `entry_date`, default hari ini) lalu kembalikan status ke pending kalau
    penerimaan belum mencapai basisnya. Jalan resmi untuk mengoreksi
    penerimaan setelah selisih ditutup -- setelahnya penerimaan bisa dicatat,
    dihapus, atau selisih ditutup ulang."""
    remittance = Remittance.objects.select_for_update().get(pk=remittance.pk)
    entries = _live_diff_entries(remittance)
    if not entries:
        raise FinanceError(f'Selisih {remittance.remittance_number} belum ditutup.')
    for entry in entries:
        reverse_entry(
            entry, reversal_date=entry_date or timezone.now().date(), created_by=created_by,
            note=f'Selisih {remittance.remittance_number} dibuka kembali',
        )


def _diff_idempotency_key(remittance):
    base = f"remittance:{remittance.pk}:settlement-diff"
    closed_before = JournalEntry.objects.filter(
        reference_type='RemittanceDiff', reference_id=remittance.pk, is_reversal=False,
    ).count()
    return base if closed_before == 0 else f"{base}:{closed_before + 1}"


@transaction.atomic
def close_remittance_diff(remittance, *, created_by=None, entry_date=None):
    """Bukukan selisih settlement_basis_sar vs Σ settlement sekali, saat tidak
    ada lagi penerimaan yang akan datang (biaya transfer/FX — v2.0 §46), lalu
    tandai remittance diterima. Panggilan kedua tanpa reversal manual ditolak
    (bukan idempotent-by-content seperti post_entry lain — perbedaan bisa
    disengaja butuh review manusia).

    Setelah entry selisih di-reverse, penutupan ulang memakai idempotency key
    bernomor (settlement-diff:2, :3, ...) -- key lama tetap melekat di entry
    yang sudah di-reverse dan kolomnya unique."""
    # Kunci baris remittance: dua klik "Tutup selisih" bersamaan tidak boleh
    # sama-sama lolos cek diff_is_closed di bawah.
    Remittance.objects.select_for_update().filter(pk=remittance.pk).exists()
    if not remittance.settlements.exists():
        raise FinanceError(
            'Belum ada penerimaan tercatat untuk remittance ini — catat penerimaannya dulu. '
            'Menutup selisih sekarang akan membukukan seluruh nominal sebagai biaya.'
        )
    basis = remittance.settlement_basis_sar
    if basis is None:
        raise FinanceError('Nominal kirim remittance ini tidak diketahui — selisih tak bisa dihitung')
    if diff_is_closed(remittance):
        raise FinanceError(
            'Selisih remittance ini sudah pernah dibukukan — buka kembali selisihnya dulu untuk mengoreksi'
        )

    diff = basis - remittance.settled_sar
    entry = None
    if diff != 0:
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
        entry = post_entry(
            entry_type=JournalEntry.TYPE_REMITTANCE,
            description=desc,
            entry_date=entry_date or timezone.now().date(),
            lines=lines,
            source_type='RemittanceDiff',
            source_id=remittance.pk,
            idempotency_key=_diff_idempotency_key(remittance),
            created_by=created_by,
        )
    return entry
