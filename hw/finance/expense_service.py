"""Beban cabang: diajukan, disetujui, dibayar (keputusan user 2026-10-11).

- Selalu rupiah. Dicatat oleh Finance (expenses.create).
- Disetujui atau ditolak oleh Finance (boleh pencatatnya sendiri), Manager,
  atau Admin (expenses.approve). Tidak ada aturan "orang kedua" di sini.
- Dibayar dari rekening IDR cabangnya (expenses.edit). Baru saat itu masuk
  pembukuan: satu jurnal Dr beban per baris / Cr rekening pembayar, dinilai
  dengan kurs tercatat rekening itu (posting.carrying_sar). Rata-rata nilai SAR
  kas rupiah tidak bergeser, dan staf tidak pernah mengetik kurs.
- Beban yang sudah dibayar dibatalkan dengan membalik jurnal dan baris buku
  kasnya; yang belum dibayar cukup ditolak.

Semua lewat posting layer (post_entry): immutable, balanced, idempotent.
"""
import re
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..branch_scope import in_scope
from ..models.expense import Expense, ExpenseCategory, ExpenseLine, ExpensePayment, ExpenseReceipt
from ..models.journal import JournalEntry
from . import accounts as coa
from .bank_ledger import record_bank_transaction, void_bank_transactions
from .errors import FinanceError
from .posting import carrying_sar, check_period_postable, get_period_for_date, native, post_entry, reverse_entry


def resolve_vendor(vendor):
    """Vendor dari nama (dibuat bila belum ada), objek Vendor, atau None."""
    from ..models.client import client_name_key
    from ..models.vendor import Vendor
    if vendor is None or isinstance(vendor, Vendor):
        return vendor
    name = str(vendor).strip()
    if not name:
        return None
    return Vendor.objects.filter(name_key=client_name_key(name)).first() or Vendor.objects.create(name=name)


def _check_branch(branch_code, user):
    """Beban diajukan, diputuskan, dibayar dan dibatalkan hanya oleh user yang
    memegang cabangnya."""
    if not in_scope(user, branch_code):
        raise FinanceError('Pengeluaran ini milik cabang di luar akses Anda.')


def _locked(expense):
    return Expense.objects.select_for_update().get(pk=expense.pk)


def _split(total, parts):
    """`total` dibagi sebanding dengan `parts`. Tiap bagian dibulatkan ke bawah,
    sisa pembulatannya ke bagian dengan pecahan terbesar -- jadi tidak ada
    bagian negatif walau baris terakhir kecil (gaji lalu biaya transfer)."""
    whole = sum(parts)
    exact = [Decimal(total) * part / whole for part in parts]
    out = [int(x) for x in exact]
    order = sorted(range(len(parts)), key=lambda i: (-(exact[i] - out[i]), i))
    for i in order[:total - sum(out)]:
        out[i] += 1
    return out


@transaction.atomic
def submit_expense(*, branch, expense_date, lines, created_by, vendor=None,
                   description='', note='', proof=None, spent_by=None, paid_with=None):
    """Catat beban (rupiah) menunggu persetujuan. Belum ada jurnal.
    lines: iterable {category, ledger_account?, description?, amount,
    receipts? (uploaded files), no_receipt_reason?}.

    `spent_by`: staf yang mengeluarkan uangnya. `paid_with`: uang muka staf
    itu bila dibayar dari sana (dibukukan otomatis saat disetujui); kosong =
    rekening kantor, dibayar Finance sesudah disetujui."""
    lines = list(lines)
    if not lines:
        raise FinanceError('Beban butuh minimal satu baris.')
    # Beban milik cabang; Pusat tidak mencatat beban (keputusan bisnis).
    if branch.is_hq:
        raise FinanceError('Pusat tidak mencatat pengeluaran — pengeluaran milik cabang.')
    _check_branch(branch.pk, created_by)
    for l in lines:
        if int(l['amount']) <= 0:
            raise FinanceError('Nominal tiap baris harus lebih dari 0.')
    if paid_with is not None:
        if paid_with.kind != paid_with.KIND_STAFF:
            raise FinanceError('Hanya uang muka staf yang bisa dipilih saat mencatat beban; rekening kantor dipilih saat membayar.')
        if paid_with.branch_id != branch.pk or paid_with.currency != Expense.CURRENCY:
            raise FinanceError(f'Uang muka {paid_with} bukan uang muka rupiah cabang ini.')
        if spent_by is not None and paid_with.holder_id != spent_by.pk:
            raise FinanceError(f'Uang muka {paid_with} dipegang staf lain.')
        spent_by = spent_by or paid_with.holder

    expense = Expense.objects.create(
        expense_number=Expense.generate_number(),
        branch=branch, expense_date=expense_date, vendor=resolve_vendor(vendor),
        description=description, currency=Expense.CURRENCY,
        status=Expense.STATUS_SUBMITTED,
        note=note, proof=proof, created_by=created_by,
        spent_by=spent_by, paid_with=paid_with,
    )
    for l in lines:
        line = ExpenseLine.objects.create(
            expense=expense, category=l['category'],
            ledger_account=l.get('ledger_account'),
            description=l.get('description', ''),
            no_receipt_reason=(l.get('no_receipt_reason') or '').strip(),
            amount=int(l['amount']),
        )
        for f in l.get('receipts') or ():
            ExpenseReceipt.objects.create(line=line, file=f, name=getattr(f, 'name', '')[:255],
                                          size=getattr(f, 'size', 0) or 0)
    return expense


@transaction.atomic
def approve_expense(expense, *, approved_by):
    expense = _locked(expense)
    if expense.status != Expense.STATUS_SUBMITTED:
        raise FinanceError(f'{expense.expense_number} tidak sedang menunggu persetujuan.')
    _check_branch(expense.branch_id, approved_by)
    expense.status = Expense.STATUS_APPROVED
    expense.decided_by, expense.decided_at = approved_by, timezone.now()
    expense.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
    # Paid out of a staff advance: the money already left on the expense date.
    if expense.paid_with_id:
        pay_expense(expense, account=expense.paid_with, payment_date=expense.expense_date, paid_by=approved_by)
        expense.refresh_from_db()
    return expense


@transaction.atomic
def reject_expense(expense, *, rejected_by, reason=''):
    expense = _locked(expense)
    if expense.status not in Expense.OPEN_STATUSES:
        raise FinanceError(f'{expense.expense_number} sudah dibayar atau ditutup; tidak bisa ditolak.')
    _check_branch(expense.branch_id, rejected_by)
    expense.status = Expense.STATUS_REJECTED
    expense.decided_by, expense.decided_at = rejected_by, timezone.now()
    expense.decision_note = reason
    expense.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note', 'updated_at'])
    return expense


@transaction.atomic
def pay_expense(expense, *, account, payment_date, paid_by, reference=''):
    """Bayar beban yang sudah disetujui, penuh, dari rekening IDR cabangnya."""
    expense = _locked(expense)
    if expense.status != Expense.STATUS_APPROVED:
        raise FinanceError(f'{expense.expense_number} belum disetujui atau sudah dibayar.')
    _check_branch(expense.branch_id, paid_by)
    if account is None:
        raise FinanceError('Pilih rekening yang membayar.')
    if account.currency != Expense.CURRENCY:
        raise FinanceError('Beban dibayar dari rekening rupiah.')
    if account.branch_id != expense.branch_id:
        raise FinanceError(f'Rekening {account} milik cabang lain — beban dibayar dari rekening cabangnya sendiri.')
    check_period_postable(get_period_for_date(payment_date))

    lines = list(expense.lines.select_related('category'))
    total = sum(int(l.amount) for l in lines)
    # Nilai SAR = bagian yang sebanding dari nilai tercatat rekening; menolak
    # rupiah yang tidak tercatat ada di rekening itu.
    value = carrying_sar(account, total, payment_date)
    for line, share in zip(lines, _split(value, [int(l.amount) for l in lines]), strict=True):
        line.amount_sar = share
        line.save(update_fields=['amount_sar'])

    ep = ExpensePayment.objects.create(
        expense=expense, payment_date=payment_date, amount=total, amount_sar=value,
        source_account=account, reference=reference, status=ExpensePayment.STATUS_PAID,
        created_by=paid_by,
    )
    br = expense.branch_id
    journal_lines = [
        {'account': l.account_code, 'debit': l.amount_sar, 'branch': br,
         'note': l.description or l.category.name, 'currency': Expense.CURRENCY, 'amount_txn': int(l.amount)}
        for l in lines if l.amount_sar
    ]
    journal_lines.append({'account': account.ledger_account_id, 'credit': value, 'branch': account.branch_id,
                          **native(account, total)})
    post_entry(
        entry_type=JournalEntry.TYPE_EXPENSE,
        description=f"Beban {expense.expense_number} — {expense.vendor or expense.description}",
        entry_date=payment_date,
        lines=journal_lines,
        source_type='ExpensePayment',
        source_id=ep.pk,
        idempotency_key=f"expensepayment:{ep.pk}:pay",
        created_by=paid_by,
    )
    record_bank_transaction(
        account=account, direction='out', amount_sar=value, currency=account.currency, amount=total,
        source_type='ExpensePayment', source_id=ep.pk, transaction_date=payment_date,
        reference=reference or expense.expense_number,
        # A staff advance may go negative: the staff member fronted the rest.
        check_funds=account.kind != account.KIND_STAFF,
    )
    expense.status = Expense.STATUS_PAID
    expense.save(update_fields=['status', 'updated_at'])
    return ep


@transaction.atomic
def void_expense(expense, *, voided_by, reason='', date=None):
    """Batalkan beban yang sudah dibayar: jurnal dan baris buku kasnya dibalik.
    Baris dan pembayarannya tetap ada untuk audit."""
    expense = _locked(expense)
    if expense.status != Expense.STATUS_PAID:
        raise FinanceError(f'{expense.expense_number} belum dibayar — tolak saja bila tidak jadi.')
    _check_branch(expense.branch_id, voided_by)
    from .claim_service import drop_voided_expense
    drop_voided_expense(expense)
    date = date or timezone.localdate()
    for ep in expense.payments.filter(status=ExpensePayment.STATUS_PAID):
        for entry in JournalEntry.objects.for_source('ExpensePayment', ep.pk).live():
            reverse_entry(entry, reversal_date=date, created_by=voided_by)
        ep.status = ExpensePayment.STATUS_VOID
        ep.save(update_fields=['status'])
        void_bank_transactions('ExpensePayment', ep.pk)
    expense.status = Expense.STATUS_VOIDED
    expense.decision_note = reason
    expense.save(update_fields=['status', 'decision_note', 'updated_at'])
    return expense


# ── Kategori beban ───────────────────────────────────────────────────

def _category_code(name):
    """Kode kategori dari namanya: huruf besar dan angka, maks. 11 karakter
    (akun bukunya <nomor>-EXP-<kode> harus muat 20 karakter)."""
    base = re.sub(r'[^A-Z0-9]+', '-', name.upper()).strip('-')[:11].strip('-') or 'CAT'
    code, n = base, 2
    while ExpenseCategory.objects.filter(pk=code).exists():
        suffix = f'-{n}'
        code = base[:11 - len(suffix)] + suffix
        n += 1
    return code


def _next_ledger_number():
    from ..models.journal import LedgerAccount
    taken = {
        int(m.group(1)) for m in
        (re.match(r'^(\d{4})-EXP-', c) for c in LedgerAccount.objects.values_list('code', flat=True))
        if m
    }
    n = coa.EXP_CUSTOM_FROM
    while n in taken:
        n += 10
    return n


@transaction.atomic
def create_category(name):
    """Kategori beban baru dengan akun bebannya sendiri, supaya tampil sebagai
    baris tersendiri di Trial Balance dan laporan."""
    from ..models.journal import LedgerAccount
    name = (name or '').strip()
    if not name:
        raise FinanceError('Nama kategori wajib diisi.')
    if ExpenseCategory.objects.filter(name__iexact=name).exists():
        raise FinanceError(f'Kategori "{name}" sudah ada.')
    code = _category_code(name)
    ledger = LedgerAccount.objects.create(
        code=f'{_next_ledger_number()}-EXP-{code}', name=f'Beban {name}',
        type=coa.AccountType.EXPENSE, normal_balance=coa.normal_balance_for(coa.AccountType.EXPENSE),
        is_postable=True, is_active=True,
    )
    return ExpenseCategory.objects.create(code=code, name=name, ledger_account=ledger)


@transaction.atomic
def update_category(category, *, name=None, is_active=None):
    """Ganti nama (akun bukunya ikut) atau aktif/nonaktifkan. Kategori tidak
    dihapus: riwayat beban dan laporannya tetap menunjuk ke sana."""
    if name is not None:
        name = name.strip()
        if not name:
            raise FinanceError('Nama kategori wajib diisi.')
        if ExpenseCategory.objects.filter(name__iexact=name).exclude(pk=category.pk).exists():
            raise FinanceError(f'Kategori "{name}" sudah ada.')
        category.name = name
        category.ledger_account.name = f'Beban {name}'
        category.ledger_account.save(update_fields=['name'])
    if is_active is not None:
        category.is_active = is_active
    category.save()
    return category
