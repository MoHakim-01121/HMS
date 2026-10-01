"""Deposit client keluar: refund dari sebuah rekening, atau pindah ke client lain.

Keduanya hanya boleh memakai deposit yang ada (saldo Titipan client). Kelebihan
bayar yang masih menempel di pembayaran atau di invoice harus dipindahkan ke
deposit dulu (posting.move_payment_excess_to_deposit / move_invoice_excess_to_deposit).
"""
from django.db import models, transaction

from ..models.client_money import ClientRefund, ClientTransfer
from ..models.journal import JournalEntry, JournalLine
from . import accounts as coa
from .bank_ledger import record_bank_transaction
from .errors import FinanceError
from .posting import client_credit_balance, post_entry


def _lock_deposit(client_id):
    """Kunci baris Titipan client supaya dua pengeluaran paralel tidak
    memakai saldo yang sama."""
    JournalLine.objects.select_for_update().filter(
        client_id=client_id, account_id=coa.CUST_CREDIT,
    ).aggregate(d=models.Sum('debit'))


def _check_balance(client, amount):
    if amount <= 0:
        raise FinanceError('Nominal harus lebih besar dari nol.')
    _lock_deposit(client.pk)
    balance = client_credit_balance(client.pk)
    if amount > balance:
        raise FinanceError(
            f'Deposit {client.name} hanya {balance:,} SAR. Pindahkan kelebihan bayarnya ke deposit dulu, '
            'atau kurangi nominalnya.'
        )


@transaction.atomic
def refund_deposit(client, *, account, amount_sar, amount_paid, refund_date, created_by, note='', proof=None):
    """Kembalikan deposit client dari `account`: DR Titipan / CR Kas rekening itu.
    `amount_paid` = yang keluar dari rekening dalam mata uangnya (sama dengan
    amount_sar untuk rekening SAR)."""
    _check_balance(client, amount_sar)
    if account.currency == 'SAR' and amount_paid != amount_sar:
        raise FinanceError('Untuk rekening SAR, nominal yang dibayarkan sama dengan nominal deposit.')
    if amount_paid <= 0:
        raise FinanceError(f'Isi nominal yang dibayarkan dalam {account.currency}.')
    number = ClientRefund.generate_number(refund_date)
    refund = ClientRefund(
        refund_number=number, client=client, money_account=account, refund_date=refund_date,
        amount_sar=amount_sar, amount_paid=amount_paid, note=note, proof=proof, created_by=created_by,
    )
    entry = post_entry(
        entry_type=JournalEntry.TYPE_REFUND,
        description=f"Refund {number} ke {client}",
        entry_date=refund_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": amount_sar, "client": client.pk, "branch": account.branch_id},
            {"account": account.ledger_account_id, "credit": amount_sar, "client": client.pk, "branch": account.branch_id},
        ],
        created_by=created_by,
        proof=proof,
    )
    # The refund points at its journal entry (the entry is written first).
    refund.journal_entry = entry
    refund.save()
    record_bank_transaction(
        account=account, direction='out', amount_sar=amount_sar, currency=account.currency, amount=amount_paid,
        source_type='Refund', source_id=entry.pk, transaction_date=refund_date, reference=(note or number)[:200],
    )
    return refund


@transaction.atomic
def transfer_deposit(from_client, to_client, *, amount_sar, transfer_date, created_by, note=''):
    """Pindahkan deposit `from_client` ke `to_client`: DR Titipan (asal) / CR Titipan (tujuan)."""
    if from_client.pk == to_client.pk:
        raise FinanceError('Pilih client tujuan yang berbeda.')
    _check_balance(from_client, amount_sar)
    number = ClientTransfer.generate_number(transfer_date)
    entry = post_entry(
        entry_type=JournalEntry.TYPE_TRANSFER,
        description=f"Transfer deposit {number}: {from_client} → {to_client}",
        entry_date=transfer_date,
        lines=[
            {"account": coa.CUST_CREDIT, "debit": amount_sar, "client": from_client.pk},
            {"account": coa.CUST_CREDIT, "credit": amount_sar, "client": to_client.pk},
        ],
        created_by=created_by,
    )
    return ClientTransfer.objects.create(
        transfer_number=number, from_client=from_client, to_client=to_client, transfer_date=transfer_date,
        amount_sar=amount_sar, note=note, journal_entry=entry, created_by=created_by,
    )
