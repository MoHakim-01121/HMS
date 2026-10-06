"""Deposit client keluar: refund dari sebuah rekening, atau pindah ke client lain.

Keduanya hanya boleh memakai deposit yang ada (saldo Titipan client). Kelebihan
bayar yang masih menempel di pembayaran atau di invoice harus dipindahkan ke
deposit dulu (posting.move_payment_excess_to_deposit / move_invoice_excess_to_deposit).

Uang keluar butuh dua orang. `request_*` mencatat dokumen bernomor berstatus
pending -- tanpa jurnal; `confirm_*` oleh user lain memeriksa saldo lagi di
bawah kunci lalu memposting jurnalnya pada tanggal dokumen; `reject_*` menolak
dengan alasan. Pencatat tidak menyetujui catatannya sendiri, kecuali admin
(terbaca dari confirmed_by == created_by).
"""
from django.db import transaction
from django.utils import timezone

from ..models.client_money import ApprovalStatus, ClientRefund, ClientTransfer
from ..models.journal import JournalEntry
from . import accounts as coa
from .bank_ledger import record_bank_transaction
from .errors import FinanceError
from .posting import client_credit_balance, lock_client_deposit, native, post_entry


def _check_balance(client, amount):
    if amount <= 0:
        raise FinanceError('Nominal harus lebih besar dari nol.')
    lock_client_deposit(client.pk)
    balance = client_credit_balance(client.pk)
    if amount > balance:
        raise FinanceError(
            f'Deposit {client.name} hanya {balance:,} SAR. Pindahkan kelebihan bayarnya ke deposit dulu, '
            'atau kurangi nominalnya.'
        )


def _lock_pending(model, doc):
    """Baca ulang dokumen di bawah kunci; hanya yang pending bisa diputuskan."""
    doc = model.objects.select_for_update().get(pk=doc.pk)
    if doc.status != ApprovalStatus.PENDING:
        raise FinanceError(f'{doc} sudah {doc.get_status_display().lower()}.')
    return doc


def _check_approver(doc, user):
    from ..models.role import ADMIN_SLUG
    from ..permissions import get_role
    if doc.created_by_id == user.pk and get_role(user) != ADMIN_SLUG:
        raise FinanceError('Dokumen ini Anda catat sendiri — persetujuan harus oleh user lain.')


def can_approve(doc, user):
    """Untuk UI: apakah `user` boleh menyetujui/menolak `doc` (yang pending)."""
    try:
        _check_approver(doc, user)
    except FinanceError:
        return False
    return doc.status == ApprovalStatus.PENDING


def _mark_confirmed(doc, user):
    doc.status = ApprovalStatus.CONFIRMED
    doc.confirmed_by = user
    doc.confirmed_at = timezone.now()
    doc.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])


def _reject(model, doc, *, rejected_by, reason):
    reason = (reason or '').strip()
    if not reason:
        raise FinanceError('Tulis alasan penolakan.')
    doc = _lock_pending(model, doc)
    _check_approver(doc, rejected_by)
    doc.status = ApprovalStatus.REJECTED
    doc.confirmed_by = rejected_by
    doc.confirmed_at = timezone.now()
    doc.rejected_reason = reason
    doc.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'rejected_reason'])
    return doc


# ── Refund ─────────────────────────────────────────────────────

@transaction.atomic
def request_refund(client, *, account, amount_sar, amount_paid, refund_date, created_by, note='', proof=None):
    """Catat refund deposit (pending, tanpa jurnal). `amount_paid` = yang akan
    keluar dari rekening dalam mata uangnya (sama dengan amount_sar untuk
    rekening SAR). Saldo dicek sekarang untuk umpan balik cepat, dan lagi saat
    disetujui."""
    _check_balance(client, amount_sar)
    if account.currency == 'SAR' and amount_paid != amount_sar:
        raise FinanceError('Untuk rekening SAR, nominal yang dibayarkan sama dengan nominal deposit.')
    if amount_paid <= 0:
        raise FinanceError(f'Isi nominal yang dibayarkan dalam {account.currency}.')
    return ClientRefund.objects.create(
        refund_number=ClientRefund.generate_number(refund_date), client=client, money_account=account,
        refund_date=refund_date, amount_sar=amount_sar, amount_paid=amount_paid, note=note, proof=proof,
        created_by=created_by,
    )


@transaction.atomic
def confirm_refund(refund, *, confirmed_by):
    """Setujui refund: DR Titipan / CR Kas rekening itu, plus buku bank."""
    refund = _lock_pending(ClientRefund, refund)
    _check_approver(refund, confirmed_by)
    client, account = refund.client, refund.money_account
    _check_balance(client, refund.amount_sar)
    entry = post_entry(
        entry_type=JournalEntry.TYPE_REFUND,
        description=f"Refund {refund.refund_number} ke {client}",
        entry_date=refund.refund_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": refund.amount_sar, "client": client.pk, "branch": account.branch_id},
            {"account": account.ledger_account_id, "credit": refund.amount_sar, "client": client.pk,
             "branch": account.branch_id, **native(account, refund.amount_paid)},
        ],
        source_type="ClientRefund",
        source_id=refund.pk,
        created_by=confirmed_by,
        proof=refund.proof or None,
    )
    record_bank_transaction(
        account=account, direction='out', amount_sar=refund.amount_sar, currency=account.currency,
        amount=refund.amount_paid, source_type='Refund', source_id=entry.pk,
        transaction_date=refund.refund_date, reference=(refund.note or refund.refund_number)[:200],
    )
    _mark_confirmed(refund, confirmed_by)
    return refund


@transaction.atomic
def reject_refund(refund, *, rejected_by, reason):
    return _reject(ClientRefund, refund, rejected_by=rejected_by, reason=reason)


# ── Transfer deposit ke client lain ───────────────────────────

@transaction.atomic
def request_transfer(from_client, to_client, *, amount_sar, transfer_date, created_by, note=''):
    """Catat pemindahan deposit `from_client` ke `to_client` (pending, tanpa jurnal)."""
    if from_client.pk == to_client.pk:
        raise FinanceError('Pilih client tujuan yang berbeda.')
    _check_balance(from_client, amount_sar)
    return ClientTransfer.objects.create(
        transfer_number=ClientTransfer.generate_number(transfer_date), from_client=from_client,
        to_client=to_client, transfer_date=transfer_date, amount_sar=amount_sar, note=note,
        created_by=created_by,
    )


@transaction.atomic
def confirm_transfer(transfer, *, confirmed_by):
    """Setujui transfer: DR Titipan (asal) / CR Titipan (tujuan)."""
    transfer = _lock_pending(ClientTransfer, transfer)
    _check_approver(transfer, confirmed_by)
    _check_balance(transfer.from_client, transfer.amount_sar)
    post_entry(
        entry_type=JournalEntry.TYPE_TRANSFER,
        description=f"Transfer deposit {transfer.transfer_number}: {transfer.from_client} → {transfer.to_client}",
        entry_date=transfer.transfer_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": transfer.amount_sar, "client": transfer.from_client_id},
            {"account": coa.CUST_CREDIT, "credit": transfer.amount_sar, "client": transfer.to_client_id},
        ],
        source_type="ClientTransfer",
        source_id=transfer.pk,
        created_by=confirmed_by,
    )
    _mark_confirmed(transfer, confirmed_by)
    return transfer


@transaction.atomic
def reject_transfer(transfer, *, rejected_by, reason):
    return _reject(ClientTransfer, transfer, rejected_by=rejected_by, reason=reason)


def pending_out(client=None):
    """Refund dan transfer deposit yang menunggu persetujuan (terbaru dulu)."""
    refunds = ClientRefund.objects.filter(status=ApprovalStatus.PENDING).select_related(
        'client', 'money_account', 'created_by')
    transfers = ClientTransfer.objects.filter(status=ApprovalStatus.PENDING).select_related(
        'from_client', 'to_client', 'created_by')
    if client is not None:
        refunds = refunds.filter(client=client)
        transfers = transfers.filter(from_client=client)
    return list(refunds), list(transfers)
