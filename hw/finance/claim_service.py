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
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from ..models.expense import Expense, ExpenseClaim, ExpenseClaimItem, ExpenseLine, ExpensePayment
from ..models.journal import JournalEntry
from . import accounts as coa
from .bank_ledger import record_bank_transaction, void_bank_transactions
from .errors import FinanceError
from .expense_service import _check_branch
from .posting import native, post_entry, reverse_entry


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
    return claim


def _close(claim, status, by, note=''):
    claim.items.filter(is_active=True).update(is_active=False)
    claim.status, claim.decided_by, claim.decided_at = status, by, timezone.now()
    claim.decision_note = note
    claim.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
    return claim


@transaction.atomic
def cancel_claim(claim, *, by, note=''):
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_DRAFT, ExpenseClaim.STATUS_SUBMITTED)
    return _close(claim, ExpenseClaim.STATUS_CANCELLED, by, note)


@transaction.atomic
def reject_claim(claim, *, by, note):
    """Pusat menolak klaim (dicatat Finance cabang); alasannya wajib."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_SUBMITTED)
    if not (note or '').strip():
        raise FinanceError('Tulis alasan penolakan dari Pusat.')
    return _close(claim, ExpenseClaim.STATUS_REJECTED, by, note.strip())


@transaction.atomic
def mark_paid(claim, *, account, paid_date, by, reference='', proof=None):
    """Rupiah penggantian dari Pusat masuk ke `account`. Tanggal lampau boleh
    (penggantian lama, jawaban user Q2) selama periodenya terbuka."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_SUBMITTED)
    if account is None or account.currency != Expense.CURRENCY or account.branch_id != claim.branch_id:
        raise FinanceError('Penggantian masuk ke rekening rupiah cabang yang mengajukan klaim.')
    dims = {'branch': claim.branch_id}
    entry = post_entry(
        entry_type=JournalEntry.TYPE_REIMBURSEMENT,
        description=f'Penggantian klaim {claim.claim_number} dari Pusat',
        entry_date=paid_date,
        lines=[
            {'account': account.ledger_account_id, 'debit': claim.total_sar, **dims,
             **native(account, claim.total_amount)},
            {'account': coa.HO_PUSAT, 'credit': claim.total_sar, **dims},
        ],
        source_type='ExpenseClaim', source_id=claim.pk, created_by=by,
    )
    record_bank_transaction(
        account=account, direction='in', amount_sar=claim.total_sar, currency=account.currency,
        amount=claim.total_amount, source_type='ExpenseClaim', source_id=claim.pk,
        transaction_date=paid_date, reference=reference,
    )
    claim.status, claim.paid_date, claim.paid_to, claim.reference = ExpenseClaim.STATUS_PAID, paid_date, account, reference
    claim.decided_by, claim.decided_at = by, timezone.now()
    fields = ['status', 'paid_date', 'paid_to', 'reference', 'decided_by', 'decided_at']
    if proof is not None:
        claim.proof = proof
        fields.append('proof')
    claim.save(update_fields=fields)
    return entry


@transaction.atomic
def unpay_claim(claim, *, by, reason):
    """Batalkan pencatatan lunas: jurnal dibalik pada tanggalnya sendiri (bulan
    yang sudah ditutup menolak), baris buku kas di-void, klaim kembali
    submitted."""
    claim = _locked(claim)
    _check_branch(claim.branch_id, by)
    _expect(claim, ExpenseClaim.STATUS_PAID)
    for entry in JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live():
        reverse_entry(entry, reversal_date=entry.entry_date, created_by=by, note=reason)
    void_bank_transactions('ExpenseClaim', claim.pk)
    claim.status, claim.paid_date, claim.paid_to, claim.decision_note = ExpenseClaim.STATUS_SUBMITTED, None, None, reason
    claim.reference, claim.proof, claim.decided_by, claim.decided_at = '', None, None, None
    claim.save(update_fields=['status', 'paid_date', 'paid_to', 'decision_note',
                              'reference', 'proof', 'decided_by', 'decided_at'])
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
    {'paid', 'claimed', 'unclaimed'} -- jumlahnya = total beban dibayar.

    `as_of`: posisi per tanggal itu (beban dibayar s.d. tanggal itu; lunas =
    klaim yang dibayar Pusat s.d. tanggal itu). Keanggotaan klaim tidak
    dibatasi tanggal pembuatannya, karena penggantian lama dicatat belakangan.
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
    active = Q(expense__claim_items__is_active=True)
    paid_q = active & Q(expense__claim_items__claim__status=ExpenseClaim.STATUS_PAID)
    if as_of:
        paid_q &= Q(expense__claim_items__claim__paid_date__lte=as_of)
    total = lines.aggregate(t=Sum('amount'))['t'] or 0
    paid = lines.filter(paid_q).aggregate(t=Sum('amount'))['t'] or 0
    claimed = (lines.filter(active).aggregate(t=Sum('amount'))['t'] or 0) - paid
    return {'paid': paid, 'claimed': claimed, 'unclaimed': total - paid - claimed}
