"""Nilai ulang SAR buku besar rekening rupiah cabang (default 1000-KAS-SBY-IDR).

Masalah (ditemukan 2026-11-04): setoran lama (`Remittance.is_legacy`) dikredit
sebesar SAR yang diterima Pusat, bukan sebesar nilai tercatat rupiahnya. Laba
kurs cabang dari selisih itu tidak pernah dicatat, rata-rata nilai SAR rekening
jadi rusak (sempat minus), dan beban yang dibayar sesudahnya ikut dinilai dengan
rata-rata yang rusak itu.

Perintah ini memutar ulang buku besar rekening itu menurut tanggal (uang masuk
dulu dalam satu hari, lalu uang keluar menurut urutan posting). Uang masuk tetap
bernilai seperti dibukukan. Uang keluar milik remittance dan beban dinilai ulang
dengan rata-rata saldo SAR / saldo rupiah saat itu, persis aturan carrying_sar.
Bila rupiah yang keluar melebihi saldo buku hari itu (tanggal pembayaran di HMS
tidak selalu sama dengan tanggal uang masuk bank), dipakai rata-rata kurs semua
uang masuk sampai hari itu. Uang keluar lain (refund, pembalik, alokasi) tidak
diubah.

Untuk setiap uang keluar yang nilainya berubah, satu jurnal penyesuaian
bertanggal sama:
  - remittance: selisihnya ke Laba / Rugi Selisih Kurs cabang;
  - beban: selisihnya ke akun beban per baris, dan nilai SAR baris beban,
    pembayaran beban, buku kas, serta item klaim yang belum dibayar disamakan.

Saldo rupiah, rekonsiliasi bank, Transit, dan tagihan klien tidak berubah.

Tanpa --commit hanya menampilkan rinciannya. Satu kali per buku besar: bila
penyesuaiannya sudah ada, perintah berhenti.
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hw.finance import accounts as coa
from hw.finance.expense_service import _split
from hw.finance.posting import post_entry
from hw.models.bank_transaction import BankTransaction
from hw.models.expense import ExpenseClaimItem, ExpensePayment
from hw.models.journal import JournalEntry, JournalLine
from hw.utils import round_half_up

REVALUED_TYPES = (JournalEntry.TYPE_REMITTANCE, JournalEntry.TYPE_EXPENSE)
KEPT_TYPES = (JournalEntry.TYPE_REFUND, JournalEntry.TYPE_REVERSAL, JournalEntry.TYPE_ALLOCATE,
              JournalEntry.TYPE_ADJUSTMENT)


def _key_prefix(ledger):
    return f"revalue:{ledger}:"


def replay(ledger):
    """[(entry, native_out, posted_sar, revalued_sar, how)] for every outflow whose
    value changes, plus the ledger's (sar, native) after the replay."""
    lines = (JournalLine.objects.filter(account_id=ledger)
             .select_related('journal_entry').order_by('journal_entry__entry_date', 'journal_entry__seq', 'line_no'))
    by_entry = defaultdict(list)
    for ln in lines:
        by_entry[ln.journal_entry_id].append(ln)

    def order(eid):
        e = by_entry[eid][0].journal_entry
        net = sum((ln.amount_txn or 0) * (1 if ln.debit else -1) for ln in by_entry[eid])
        return (e.entry_date, 0 if net >= 0 else 1, e.seq)

    sar = held = in_sar = in_native = 0
    changes, unknown = [], []
    for eid in sorted(by_entry, key=order):
        entry = by_entry[eid][0].journal_entry
        for ln in by_entry[eid]:
            amount = ln.amount_txn or 0
            if ln.debit:
                sar += ln.debit
                held += amount
                if amount:
                    in_sar += ln.debit
                    in_native += amount
                continue
            value, how = ln.credit, ''
            if amount and entry.entry_type in REVALUED_TYPES:
                if held >= amount and sar > 0:
                    value, how = round_half_up(Decimal(sar) * amount / held), 'rata-rata saldo'
                else:
                    value, how = round_half_up(Decimal(in_sar) * amount / in_native), 'rata-rata uang masuk'
            elif amount and entry.entry_type not in KEPT_TYPES:
                unknown.append(entry)
            if value != ln.credit:
                changes.append((entry, amount, ln.credit, value, how))
            sar -= value
            held -= amount
    if unknown:
        raise CommandError('Uang keluar jenis yang belum ditangani: ' + ', '.join(
            f'{e.entry_number} ({e.entry_type})' for e in unknown))
    return changes, sar, held


def _remittance_lines(entry, ledger, delta):
    rem = entry.source_remittance
    dims = {'branch': rem.from_account.branch_id, 'remittance': rem.pk}
    if delta < 0:  # credited too much: the branch gained on the rate
        return [{'account': ledger, 'debit': -delta, **dims},
                {'account': coa.INC_FX_GAIN, 'credit': -delta, **dims}]
    return [{'account': coa.EXP_FX_LOSS, 'debit': delta, **dims},
            {'account': ledger, 'credit': delta, **dims}]


def _expense_plan(entry, value):
    """(lines, new shares) for an expense payment revalued to `value` SAR."""
    ep = ExpensePayment.objects.select_related('expense').get(pk=entry.source_expense_payment_id)
    exp_lines = list(ep.expense.lines.select_related('category').order_by('pk'))
    shares = _split(value, [int(line.amount) for line in exp_lines])
    by_account = defaultdict(int)
    for line, share in zip(exp_lines, shares, strict=True):
        by_account[line.account_code] += share - int(line.amount_sar)
    return ep, exp_lines, shares, by_account


def _expense_lines(entry, ledger, by_account):
    br = entry.lines.filter(account_id=ledger).values_list('branch_id', flat=True).first()
    out, net = [], 0
    for account, d in sorted(by_account.items()):
        if d > 0:
            out.append({'account': account, 'debit': d, 'branch': br})
        elif d < 0:
            out.append({'account': account, 'credit': -d, 'branch': br})
        net += d
    if net > 0:
        out.append({'account': ledger, 'credit': net, 'branch': br})
    elif net < 0:
        out.append({'account': ledger, 'debit': -net, 'branch': br})
    return out


def _sync_expense_documents(ep, exp_lines, shares, value):
    for line, share in zip(exp_lines, shares, strict=True):
        line.amount_sar = share
        line.save(update_fields=['amount_sar'])
    ep.amount_sar = value
    ep.save(update_fields=['amount_sar'])
    BankTransaction.objects.filter(source_type='ExpensePayment', source_id=ep.pk).update(amount_sar=value)
    for item in ExpenseClaimItem.objects.filter(expense=ep.expense, is_active=True).select_related('claim'):
        if item.claim.payments.filter(voided_at__isnull=True).exists():
            raise CommandError(f'{ep.expense.expense_number} ada di klaim {item.claim.claim_number} yang sudah dibayar.')
        item.amount_sar = value
        item.save(update_fields=['amount_sar'])
        from hw.finance.claim_service import _retotal
        _retotal(item.claim)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--ledger', default='1000-KAS-SBY-IDR')
        parser.add_argument('--commit', action='store_true', help='Posting jurnalnya (tanpa ini hanya tampil).')

    def handle(self, *args, ledger, commit, **opts):
        prefix = _key_prefix(ledger)
        if JournalEntry.objects.filter(idempotency_key__startswith=prefix).exists():
            raise CommandError(f'Penyesuaian {ledger} sudah pernah diposting.')

        before = JournalLine.objects.filter(account_id=ledger)
        before_sar = sum(ln.debit - ln.credit for ln in before)
        changes, after_sar, held = replay(ledger)

        monthly = defaultdict(lambda: [0, 0])  # month -> [fx gain, extra expense]
        self.stdout.write(f'{"Tanggal":10}  {"Dokumen":32} {"Rupiah":>14} {"SAR lama":>9} {"SAR baru":>9} {"Selisih":>8}  Dasar')
        for entry, amount, posted, value, how in changes:
            delta = value - posted
            month = entry.entry_date.strftime('%Y-%m')
            if entry.entry_type == JournalEntry.TYPE_REMITTANCE:
                monthly[month][0] -= delta
                name = entry.source_remittance.remittance_number
            else:
                monthly[month][1] += delta
                name = entry.description.removeprefix('Beban ')[:32]
            self.stdout.write(f'{entry.entry_date:%Y-%m-%d}  {name:32} {amount:>14,} {posted:>9,} {value:>9,} {delta:>+8,}  {how}')

        self.stdout.write('\nPer bulan: laba kurs cabang (+laba / -rugi), tambahan nilai SAR beban')
        for month in sorted(monthly):
            gain, extra = monthly[month]
            self.stdout.write(f'  {month}: laba kurs {gain:+,} SAR, beban {extra:+,} SAR')
        total_gain = sum(v[0] for v in monthly.values())
        total_extra = sum(v[1] for v in monthly.values())
        rate = f'{held / after_sar:,.1f}' if after_sar > 0 else '-'
        self.stdout.write(f'  Total: laba kurs {total_gain:+,} SAR, beban {total_extra:+,} SAR')
        self.stdout.write(f'\n{ledger}: {before_sar:,} SAR → {after_sar:,} SAR untuk {held:,} rupiah (kurs {rate})')

        if not commit:
            self.stdout.write('\nBelum diposting. Jalankan dengan --commit.')
            return

        with transaction.atomic():
            for entry, amount, posted, value, how in changes:
                delta = value - posted
                if entry.entry_type == JournalEntry.TYPE_REMITTANCE:
                    name = entry.source_remittance.remittance_number
                    lines = _remittance_lines(entry, ledger, delta)
                else:
                    ep, exp_lines, shares, by_account = _expense_plan(entry, value)
                    name = ep.expense.expense_number
                    lines = _expense_lines(entry, ledger, by_account)
                    _sync_expense_documents(ep, exp_lines, shares, value)
                if entry.entry_type == JournalEntry.TYPE_REMITTANCE:
                    # The cash book carries the journal's SAR value next to the rupiah.
                    BankTransaction.objects.filter(
                        source_type='Remittance', source_id=entry.source_remittance_id, account__ledger_account_id=ledger,
                        direction=BankTransaction.DIRECTION_OUT,
                    ).update(amount_sar=value)
                post_entry(
                    entry_type=JournalEntry.TYPE_ADJUSTMENT,
                    description=f'Nilai SAR {name} dengan kurs rata-rata rekening ({posted:,} → {value:,} SAR)',
                    entry_date=entry.entry_date,
                    lines=lines,
                    idempotency_key=f'{prefix}{entry.pk}',
                )
            final = sum(ln.debit - ln.credit for ln in JournalLine.objects.filter(account_id=ledger))
            if final != after_sar:
                raise CommandError(f'Hasil {final:,} SAR tidak sama dengan hitungan {after_sar:,} SAR; dibatalkan.')
        self.stdout.write(self.style.SUCCESS(f'\n{len(changes)} jurnal penyesuaian diposting.'))
