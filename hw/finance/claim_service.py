"""Klaim penggantian beban cabang (keputusan user 2026-10-19).

Cabang menalangi beban operasional dari kasnya, lalu mengklaimnya ke Pusat
untuk rentang yang ia pilih (bulan ini, 3 bulan, 4 bulan, ...). Pusat
mengganti dengan rupiah persis sebesar klaim. Pusat tidak memakai HMS, jadi
Finance cabang yang mencatat penolakannya atau menandai klaim lunas saat
rupiahnya masuk.

Lunas: Dr rekening IDR cabang (nominal = total rupiah, SAR = nilai SAR beban
saat dibayar, sehingga rata-rata kurs kas rupiah tidak bergeser) / Cr Rekening
Antar Kantor – Pusat. Pusat tidak menginput SAR yang ia keluarkan (Q1).

Status: draft → submitted → paid; rejected (dari submitted) dan cancelled
(dari draft/submitted) membebaskan bebannya untuk diklaim ulang. Klaim lunas
dibatalkan dengan membalik jurnal dan buku kasnya, lalu kembali ke submitted.
"""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from ..models.branch import Branch
from ..models.expense import Expense, ExpenseClaim, ExpenseClaimItem, ExpenseClaimPayment, ExpenseLine, ExpensePayment
from ..models.journal import JournalEntry
from ..utils import round_half_up
from . import accounts as coa
from .bank_ledger import record_bank_transaction, void_bank_transactions
from .errors import FinanceError
from .expense_service import _check_branch
from .posting import native, post_entry, reverse_entry

PAYMENT_SOURCE = 'ExpenseClaimPayment'
REMAINDER_OPEN, REMAINDER_BORNE = 'open', 'borne'
EXCESS_CREDIT, EXCESS_KEEP = 'credit', 'keep'


def _locked(claim):
    return ExpenseClaim.objects.select_for_update().get(pk=claim.pk)


def _expect(claim, *statuses):
    if claim.status not in statuses:
        raise FinanceError(f'Klaim {claim.claim_number} sedang {claim.get_status_display()}.')


def claimable_expenses(branch, date_from, date_to):
    """Beban cabang yang sudah dibayar, bertanggal dalam rentang, dan belum ada
    di klaim aktif."""
    return (
        Expense.objects.filter(
            branch=branch, status=Expense.STATUS_PAID,
            expense_date__gte=date_from, expense_date__lte=date_to,
        )
        .exclude(claim_items__is_active=True)
        .prefetch_related('lines')
        .order_by('expense_date', 'pk')
    )


def claimable_start(branch):
    """Tanggal beban tertua yang masih bisa diklaim (None bila tidak ada)."""
    oldest = claimable_expenses(branch, date.min, date.max).first()
    return oldest.expense_date if oldest else None


def _retotal(claim):
    agg = claim.items.filter(is_active=True).aggregate(a=Sum('amount'), s=Sum('amount_sar'))
    claim.total_amount, claim.total_sar = agg['a'] or 0, agg['s'] or 0
    claim.save(update_fields=['total_amount', 'total_sar'])


def _add_items(claim, expenses):
    """Masukkan `expenses` ke `claim`. Beban yang sudah ada di klaim aktif lain
    ditolak oleh constraint DB (dua klaim dibuat bersamaan), dilaporkan
    sebagai FinanceError."""
    for expense in expenses:
        # Re-read under lock: a void may have landed after the caller listed it.
        expense = Expense.objects.select_for_update().get(pk=expense.pk)
        if expense.status != Expense.STATUS_PAID:
            raise FinanceError(f'{expense.expense_number} tidak lagi berstatus dibayar.')
        lines = list(expense.lines.all())
        try:
            with transaction.atomic():
                ExpenseClaimItem.objects.create(
                    claim=claim, expense=expense,
                    amount=sum(l.amount for l in lines), amount_sar=sum(l.amount_sar for l in lines),
                )
        except IntegrityError:
            raise FinanceError(f'{expense.expense_number} sudah ada di klaim lain.') from None
    _retotal(claim)


@transaction.atomic
def create_claim(*, branch, date_from, date_to, created_by, exclude_ids=(), note=''):
    if branch.is_hq:
        raise FinanceError('Pusat tidak mengklaim pengeluaran — klaim milik cabang.')
    _check_branch(branch.pk, created_by)
    if date_from > date_to:
        raise FinanceError('Tanggal awal harus sebelum tanggal akhir.')
    expenses = [e for e in claimable_expenses(branch, date_from, date_to) if e.pk not in set(exclude_ids)]
    if not expenses:
        raise FinanceError('Tidak ada pengeluaran yang bisa diklaim di rentang ini.')
    claim = ExpenseClaim.objects.create(
        claim_number=ExpenseClaim.generate_number(), branch=branch,
        date_from=date_from, date_to=date_to, note=note, created_by=created_by,
    )
    _add_items(claim, expenses)
    return claim


@transaction.atomic
def remove_item(claim, expense, *, by):
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_DRAFT)
    claim.items.filter(expense=expense, is_active=True).update(is_active=False)
    _retotal(claim)
    return claim


@transaction.atomic
def submit_claim(claim, *, by):
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_DRAFT)
    if not claim.items.filter(is_active=True).exists():
        raise FinanceError('Klaim ini tidak berisi pengeluaran.')
    claim.status, claim.submitted_at = ExpenseClaim.STATUS_SUBMITTED, timezone.now()
    claim.save(update_fields=['status', 'submitted_at'])
    _apply_credit(claim, by)
    return claim


def head_office_credit(branch_id, *, as_of=None):
    """Titipan Pusat: kelebihan transfer yang belum memotong klaim mana pun."""
    live = ExpenseClaimPayment.objects.filter(claim__branch_id=branch_id, voided_at__isnull=True)
    if as_of:
        live = live.filter(payment_date__lte=as_of)
    added = live.filter(excess_kept=False).aggregate(t=Sum('excess_amount'))['t'] or 0
    used = live.filter(kind=ExpenseClaimPayment.KIND_CREDIT).aggregate(t=Sum('amount'))['t'] or 0
    return added - used


def _apply_credit(claim, by):
    """Potong klaim yang baru diajukan dengan titipan Pusat. Tidak ada uang
    bergerak: jurnalnya sudah dibuat saat kelebihan itu masuk."""
    Branch.objects.select_for_update().filter(pk=claim.branch_id).exists()  # one credit, one claim at a time
    use = min(head_office_credit(claim.branch_id), claim.remaining)
    if use <= 0:
        return
    today = timezone.localdate()
    value = round_half_up(Decimal(claim.total_sar) * use / claim.total_amount)
    ExpenseClaimPayment.objects.create(
        claim=claim, kind=ExpenseClaimPayment.KIND_CREDIT, payment_date=today, amount=use, amount_sar=value, created_by=by,
    )
    claim.received_amount += use
    claim.received_sar += value
    fields = ['received_amount', 'received_sar']
    if not claim.remaining:
        claim.status, claim.paid_date = ExpenseClaim.STATUS_PAID, today
        claim.decided_by, claim.decided_at = by, timezone.now()
        fields += ['status', 'paid_date', 'decided_by', 'decided_at']
    claim.save(update_fields=fields)


def _transfers(claim):
    return claim.payments.filter(kind=ExpenseClaimPayment.KIND_TRANSFER, voided_at__isnull=True)


def _expect_unanswered(claim, *statuses):
    """Belum ada jawaban Pusat: klaim yang lunas murni dari titipan masih boleh
    ditolak atau dibatalkan, karena belum ada transfer untuk klaim itu."""
    if claim.status == ExpenseClaim.STATUS_PAID and not claim.borne_amount and not _transfers(claim).exists():
        return
    _expect(claim, *statuses)


def _close(claim, status, by, note=''):
    claim.items.filter(is_active=True).update(is_active=False)
    claim.payments.filter(voided_at__isnull=True).update(voided_at=timezone.now())  # the credit goes back
    claim.status, claim.decided_by, claim.decided_at = status, by, timezone.now()
    claim.decision_note = note
    claim.received_amount, claim.received_sar, claim.paid_date = 0, 0, None
    claim.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note',
                              'received_amount', 'received_sar', 'paid_date'])
    return claim


@transaction.atomic
def cancel_claim(claim, *, by, note=''):
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect_unanswered(claim, ExpenseClaim.STATUS_DRAFT, ExpenseClaim.STATUS_SUBMITTED)
    return _close(claim, ExpenseClaim.STATUS_CANCELLED, by, note)


@transaction.atomic
def reject_claim(claim, *, by, note):
    """Pusat menolak klaim (dicatat Finance cabang); alasannya wajib."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect_unanswered(claim, ExpenseClaim.STATUS_SUBMITTED)
    if not (note or '').strip():
        raise FinanceError('Tulis alasan penolakan dari Pusat.')
    return _close(claim, ExpenseClaim.STATUS_REJECTED, by, note.strip())


@transaction.atomic
def mark_paid(claim, *, account, paid_date, by, reference='', proof=None, amount=None, remainder=None, excess_use=None):
    """Rupiah penggantian dari Pusat masuk ke `account`. Tanggal lampau boleh
    (penggantian lama, jawaban user Q2) selama periodenya terbuka.

    `amount`: rupiah yang diterima, bawaan seluruh sisa klaim. Kalau kurang dari
    sisa, `remainder` wajib: REMAINDER_OPEN (masih ditagih) atau REMAINDER_BORNE
    (ditanggung cabang, klaim selesai). Kalau lebih, `excess_use` wajib:
    EXCESS_CREDIT (titipan yang memotong klaim berikutnya) atau EXCESS_KEEP (dana
    tambahan untuk cabang, tidak memotong apa pun). Nilai SAR-nya sebanding dengan bagian
    klaim yang dibayar; transfer yang melunasi mengambil sisa nilainya."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_SUBMITTED, ExpenseClaim.STATUS_PARTIAL)
    if account is None or account.currency != Expense.CURRENCY or account.branch_id != claim.branch_id:
        raise FinanceError('Penggantian masuk ke rekening rupiah cabang yang mengajukan klaim.')
    remaining = claim.remaining
    amount = remaining if amount is None else int(amount)
    if amount <= 0:
        raise FinanceError('Jumlah diterima harus lebih dari 0.')
    short, excess = max(remaining - amount, 0), max(amount - remaining, 0)
    if short and remainder not in (REMAINDER_OPEN, REMAINDER_BORNE):
        raise FinanceError('Pilih nasib sisanya: masih akan diganti Pusat, atau ditanggung cabang.')
    if excess and excess_use not in (EXCESS_CREDIT, EXCESS_KEEP):
        raise FinanceError('Pilih nasib kelebihannya: memotong klaim berikutnya, atau dana tambahan untuk cabang.')
    excess_sar = round_half_up(Decimal(claim.total_sar) * excess / claim.total_amount)
    value = (claim.total_sar - claim.received_sar + excess_sar if not short
             else round_half_up(Decimal(claim.total_sar) * amount / claim.total_amount))
    if value <= 0:
        raise FinanceError('Jumlah diterima terlalu kecil untuk dibukukan.')

    payment = ExpenseClaimPayment.objects.create(
        claim=claim, payment_date=paid_date, account=account, amount=amount, amount_sar=value,
        excess_amount=excess, excess_sar=excess_sar, excess_kept=bool(excess) and excess_use == EXCESS_KEEP, reference=reference, proof=proof, created_by=by,
    )
    dims = {'branch': claim.branch_id}
    entry = post_entry(
        entry_type=JournalEntry.TYPE_REIMBURSEMENT,
        description=f'Penggantian klaim {claim.claim_number} dari Pusat',
        entry_date=paid_date,
        lines=[
            {'account': account.ledger_account_id, 'debit': value, **dims, **native(account, amount)},
            {'account': coa.HO_PUSAT, 'credit': value, **dims},
        ],
        source_type='ExpenseClaim', source_id=claim.pk, created_by=by,
    )
    record_bank_transaction(
        account=account, direction='in', amount_sar=value, currency=account.currency,
        amount=amount, source_type=PAYMENT_SOURCE, source_id=payment.pk,
        transaction_date=paid_date, reference=reference,
    )
    claim.received_amount += amount - excess
    claim.received_sar += value - excess_sar
    claim.status = ExpenseClaim.STATUS_PAID
    if short and remainder == REMAINDER_OPEN:
        claim.status = ExpenseClaim.STATUS_PARTIAL
    elif short:
        claim.borne_amount, claim.borne_date = short, paid_date
    claim.paid_date, claim.paid_to, claim.reference = paid_date, account, reference
    claim.decided_by, claim.decided_at = by, timezone.now()
    fields = ['status', 'received_amount', 'received_sar', 'borne_amount', 'borne_date',
              'paid_date', 'paid_to', 'reference', 'decided_by', 'decided_at']
    if proof is not None:
        claim.proof = proof
        fields.append('proof')
    claim.save(update_fields=fields)
    return entry


@transaction.atomic
def close_remainder(claim, *, by, closed_date, note=''):
    """Pusat tidak akan mengganti sisanya: klaim selesai, sisanya tanggungan
    cabang. Tidak ada uang bergerak, jadi tidak ada jurnal: bebannya sudah
    tercatat saat dibayar."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_PARTIAL)
    claim.borne_amount, claim.borne_date = claim.remaining, closed_date
    claim.status, claim.decision_note = ExpenseClaim.STATUS_PAID, note
    claim.decided_by, claim.decided_at = by, timezone.now()
    claim.save(update_fields=['status', 'borne_amount', 'borne_date', 'decision_note', 'decided_by', 'decided_at'])
    return claim


@transaction.atomic
def unpay_claim(claim, *, by, reason):
    """Batalkan semua transfer penggantian: jurnal dibalik pada tanggalnya
    sendiri (bulan yang sudah ditutup menolak), baris buku kas di-void, klaim
    kembali submitted. Potongan titipan tetap menempel pada klaimnya."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_PAID, ExpenseClaim.STATUS_PARTIAL)
    transfers = _transfers(claim)
    if not transfers.exists():
        raise FinanceError('Klaim ini lunas dari titipan Pusat, tidak ada transfer untuk dibatalkan. Batalkan klaimnya.')
    excess = transfers.filter(excess_kept=False).aggregate(t=Sum('excess_amount'))['t'] or 0
    if excess > head_office_credit(claim.branch_id):
        raise FinanceError('Kelebihan transfer klaim ini sudah memotong klaim lain. Batalkan klaim itu dulu.')
    for entry in JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live():
        reverse_entry(entry, reversal_date=entry.entry_date, created_by=by, note=reason)
    void_bank_transactions(PAYMENT_SOURCE, list(transfers.values_list('pk', flat=True)))
    transfers.update(voided_at=timezone.now())
    credit = claim.payments.filter(voided_at__isnull=True).aggregate(a=Sum('amount'), s=Sum('amount_sar'))
    claim.status, claim.paid_date, claim.paid_to, claim.decision_note = ExpenseClaim.STATUS_SUBMITTED, None, None, reason
    claim.reference, claim.proof, claim.decided_by, claim.decided_at = '', None, None, None
    claim.received_amount, claim.received_sar = credit['a'] or 0, credit['s'] or 0
    claim.borne_amount, claim.borne_date = 0, None
    claim.save(update_fields=['status', 'paid_date', 'paid_to', 'decision_note', 'reference', 'proof', 'decided_by',
                              'decided_at', 'received_amount', 'received_sar', 'borne_amount', 'borne_date'])
    return claim


def drop_voided_expense(expense):
    """Dipanggil void_expense: beban di klaim draft keluar dari klaimnya; beban
    di klaim yang sudah diajukan atau lunas tidak boleh di-void."""
    item = expense.claim_items.filter(is_active=True).first()
    if item is None:
        return
    item.claim = _locked(item.claim)   # a submit may be running at the same time
    if item.claim.status != ExpenseClaim.STATUS_DRAFT:
        raise FinanceError(
            f'{expense.expense_number} ada di klaim {item.claim.claim_number} '
            f'({item.claim.get_status_display()}) — batalkan klaimnya dulu.'
        )
    item.is_active = False
    item.save(update_fields=['is_active'])
    _retotal(item.claim)


def reimbursement_summary(branch, *, as_of=None, date_from=None, date_to=None):
    """Rupiah beban dibayar cabang menurut status penggantiannya:
    {'paid', 'claimed', 'unclaimed', 'borne'} -- jumlahnya = total beban dibayar.
    Klaim yang diganti sebagian dibagi sebanding: yang diterima masuk `paid`,
    yang ditanggung cabang masuk `borne`, sisanya masih `claimed`.

    `as_of`: posisi per tanggal itu (beban dibayar s.d. tanggal itu; diganti =
    transfer Pusat s.d. tanggal itu). Keanggotaan klaim tidak dibatasi tanggal
    pembuatannya, karena penggantian lama dicatat belakangan.
    `date_from`/`date_to` membatasi beban menurut tanggal bayarnya."""
    pays = ExpensePayment.objects.filter(
        status=ExpensePayment.STATUS_PAID, expense__status=Expense.STATUS_PAID, expense__branch=branch,
    )
    if as_of:
        pays = pays.filter(payment_date__lte=as_of)
    if date_from:
        pays = pays.filter(payment_date__gte=date_from)
    if date_to:
        pays = pays.filter(payment_date__lte=date_to)
    lines = ExpenseLine.objects.filter(expense__in=pays.values('expense'))
    active = lines.filter(expense__claim_items__is_active=True)
    total = lines.aggregate(t=Sum('amount'))['t'] or 0
    claimed_total = active.aggregate(t=Sum('amount'))['t'] or 0
    paid = borne = 0
    answered = active.filter(expense__claim_items__claim__status__in=(ExpenseClaim.STATUS_PARTIAL, ExpenseClaim.STATUS_PAID))
    per_claim = answered.values('expense__claim_items__claim').annotate(t=Sum('amount'))
    claims = ExpenseClaim.objects.in_bulk([r['expense__claim_items__claim'] for r in per_claim])
    for row in per_claim:
        claim = claims[row['expense__claim_items__claim']]
        received = claim.received_amount
        if as_of:
            received = claim.payments.filter(voided_at__isnull=True, payment_date__lte=as_of).aggregate(
                t=Sum(F('amount') - F('excess_amount')))['t'] or 0
        paid += round_half_up(Decimal(row['t']) * received / claim.total_amount)
        if claim.borne_amount and (not as_of or claim.borne_date <= as_of):
            borne += round_half_up(Decimal(row['t']) * claim.borne_amount / claim.total_amount)
    return {'paid': paid, 'claimed': claimed_total - paid - borne, 'unclaimed': total - claimed_total, 'borne': borne}
