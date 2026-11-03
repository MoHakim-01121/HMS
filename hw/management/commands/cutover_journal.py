"""Bangun jurnal riwayat sekali setelah migrasi cutover skema v2 (F11).

Produksi belum punya jurnal: invoice, pembayaran lama (dipindah oleh migrasi
0120), dan setoran lama (0133) sudah berbentuk dokumen baru tapi belum
dibukukan. Perintah ini memutar ulang semuanya menurut tanggal lewat layanan
posting yang sama dengan pemakaian harian:

1. charge tiap invoice (tanggal terbit),
2. pembayaran terkonfirmasi (tanggal bayar, beserta alokasinya),
3. kirim setoran dari rekening cabang (tanggal setoran),
4. penerimaan di Pusat dan alokasinya ke reservasi (tanggal terima),
5. kelebihan bayar pada CL batal dipindah ke deposit client (keputusan user).

Aman diulang: dokumen yang sudah punya entry hidup dilewati. Tanpa --commit
semuanya dijalankan lalu dibatalkan (laporan saja).

6. (opsional) saldo tiap rekening disamakan dengan saldo nyata pada hari
   cutover: --saldo ID=NOMINAL[@KURS] dalam mata uang rekening. Selisihnya satu
   baris buku kas + satu jurnal penyesuaian lawan Ekuitas Saldo Awal.

    python manage.py cutover_journal            # uji coba, tidak menyimpan
    python manage.py cutover_journal --commit   # simpan
    python manage.py cutover_journal --commit --tanggal 2026-10-15 --saldo 1=150000000@4850 --saldo 3=2500
"""
from calendar import monthrange
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hw.finance import accounts as coa
from hw.finance.bank_ledger import record_bank_transaction
from hw.finance.penalty_billing import reservation_balances
from hw.finance.posting import (
    move_invoice_excess_to_deposit,
    post_exchange,
    post_invoice_charge,
    post_payment,
    resync_remittance,
)
from hw.finance.remittance_allocation import live_allocation_entries, post_allocation
from hw.finance.seasons import ensure_monthly_periods
from hw.finance.settlement_service import post_receipt
from hw.models import (
    BankTransaction,
    CurrencyExchange,
    FinancialPeriod,
    Invoice,
    JournalEntry,
    PaymentRecord,
    Remittance,
    RemittanceSettlement,
)

SYSTEM_USERNAME = 'system.cutover'
# Urutan dalam satu hari: uang masuk dan ditukar dulu, baru dikirim.
CHARGE, PAYMENT, EXCHANGE, SEND, RECEIVE = range(5)


def _live(source_type, source_id, entry_type):
    return JournalEntry.objects.for_source(source_type, source_id).filter(entry_type=entry_type).live().exists()


class Command(BaseCommand):
    help = 'Bangun jurnal riwayat sekali setelah migrasi cutover skema v2.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Simpan hasilnya (tanpa ini: uji coba).')
        parser.add_argument('--tanggal', type=date.fromisoformat, default=None,
                            help='Tanggal cutover untuk penyesuaian saldo (bawaan: hari ini).')
        parser.add_argument('--saldo', action='append', default=[], metavar='ID=NOMINAL[@KURS]',
                            help='Saldo nyata rekening (id MoneyAccount) dalam mata uangnya; kurs wajib untuk non-SAR.')

    def handle(self, *args, **options):
        commit = options['commit']
        self.stdout.write(f"Mode: {'SIMPAN' if commit else 'UJI COBA, tidak ada yang disimpan'}")
        with transaction.atomic():
            self.user, _ = get_user_model().objects.get_or_create(
                username=SYSTEM_USERNAME, defaults={'first_name': 'System', 'last_name': 'Cutover', 'is_active': False},
            )
            coa.seed_chart_of_accounts()
            stats = self._replay()
            for spec in options['saldo']:
                self._adjust_balance(spec, options['tanggal'] or timezone.localdate())
            self._report(stats)
            if not commit:
                transaction.set_rollback(True)

    # ── putar ulang ──────────────────────────────────────────────────────
    def _events(self):
        events = []
        for inv in Invoice.objects.exclude(status=Invoice.STATUS_VOID):
            events.append((inv.issued_date or inv.created_at.date(), CHARGE, inv.pk, inv))
        for p in PaymentRecord.objects.filter(status=PaymentRecord.STATUS_CONFIRMED).select_related('receiving_account'):
            events.append((p.payment_date, PAYMENT, p.pk, p))
        for ex in CurrencyExchange.objects.filter(status=CurrencyExchange.STATUS_ACTIVE).select_related(
            'from_account', 'to_account',
        ):
            events.append((ex.exchange_date, EXCHANGE, ex.pk, ex))
        for rem in Remittance.objects.select_related('from_account', 'to_account'):
            events.append((rem.date, SEND, rem.pk, rem))
        for s in RemittanceSettlement.objects.select_related('remittance__from_account', 'remittance__to_account'):
            events.append((s.received_date, RECEIVE, s.pk, s))
        return sorted(events, key=lambda e: e[:3])

    def _ensure_periods(self, days):
        for y, m in sorted({(d.year, d.month) for d in days}):
            start, end = date(y, m, 1), date(y, m, monthrange(y, m)[1])
            if not FinancialPeriod.objects.filter(date_from__lte=end, date_to__gte=start).exists():
                FinancialPeriod.objects.create(name=f'{y}-{m:02d}', date_from=start, date_to=end)

    def _replay(self):
        events = self._events()
        self._ensure_periods([e[0] for e in events])
        # Sampai akhir tahun berjalan, supaya posting tidak berhenti di awal bulan depan.
        today = timezone.localdate()
        ensure_monthly_periods(today, date(today.year, 12, 31))
        stats = {'charge': 0, 'payment': 0, 'exchange': 0, 'send': 0, 'receive': 0, 'allocate': 0, 'deposit': 0}
        for day, kind, _, obj in events:
            if kind == CHARGE:
                if not _live('Invoice', obj.pk, JournalEntry.TYPE_CHARGE) and post_invoice_charge(
                    obj, created_by=self.user, entry_date=day,
                ):
                    stats['charge'] += 1
            elif kind == PAYMENT:
                if not _live('PaymentRecord', obj.pk, JournalEntry.TYPE_PAYMENT):
                    post_payment(obj, created_by=self.user)
                    stats['payment'] += 1
            elif kind == EXCHANGE:
                # A same-currency transfer has no journal: post_exchange returns None.
                if not _live('CurrencyExchange', obj.pk, JournalEntry.TYPE_EXCHANGE) and post_exchange(
                    obj, created_by=self.user,
                ):
                    stats['exchange'] += 1
            elif kind == SEND:
                if not _live('Remittance', obj.pk, JournalEntry.TYPE_REMITTANCE):
                    resync_remittance(obj, created_by=self.user)
                    stats['send'] += 1
                if not BankTransaction.objects.filter(source_type='Remittance', source_id=obj.pk).exists():
                    record_bank_transaction(
                        account=obj.from_account, direction='out', amount_sar=obj.expected_sar,
                        currency=obj.from_account.currency, amount=obj.amount_sent,
                        source_type='Remittance', source_id=obj.pk, transaction_date=obj.date,
                        reference=obj.receipt_reference, check_funds=False,  # history, as it happened
                    )
            else:
                if not _live('RemittanceSettlement', obj.pk, JournalEntry.TYPE_REMITTANCE):
                    post_receipt(obj, created_by=self.user)
                    stats['receive'] += 1
                lines = list(obj.allocations.select_related('invoice_line'))
                if lines and not live_allocation_entries(obj):
                    validated = [
                        {'row': {'reservation_id': l.invoice_line_id, 'invoice_id': l.invoice_line.invoice_id},
                         'amount_sar': l.amount_sar}
                        for l in lines
                    ]
                    post_allocation(obj, validated, entry_date=day, created_by=self.user)
                    stats['allocate'] += 1
        stats['deposit'] = self._cancelled_excess_to_deposit()
        return stats

    def _cancelled_excess_to_deposit(self):
        """Uang CL batal yang sudah dibayar → deposit client (keputusan 2 Okt 2026)."""
        moved = 0
        for inv in Invoice.objects.filter(invoice_type='hotel').exclude(status=Invoice.STATUS_VOID):
            rows = reservation_balances(inv).values()
            if any(r['remaining'] < 0 and r['line'].confirmation_letter.is_cancelled for r in rows):
                moved += move_invoice_excess_to_deposit(inv, created_by=self.user, entry_date=timezone.localdate())
        return moved

    def _adjust_balance(self, spec, day):
        """Samakan saldo rekening dengan saldo nyata pada hari cutover."""
        from decimal import Decimal

        from django.core.management.base import CommandError
        from django.db.models import Sum

        from hw.finance.posting import post_adjustment
        from hw.models.bank import MoneyAccount

        try:
            pk, value = spec.split('=', 1)
            amount, _, rate = value.partition('@')
            account = MoneyAccount.objects.get(pk=int(pk))
            real = int(amount.replace(',', ''))
            rate = Decimal(rate) if rate else (Decimal(1) if account.currency == 'SAR' else None)
        except (ValueError, MoneyAccount.DoesNotExist) as exc:
            raise CommandError(f'--saldo {spec}: {exc}') from None
        if rate is None or rate <= 0:
            raise CommandError(f'--saldo {spec}: kurs wajib untuk rekening {account.currency}')
        moves = BankTransaction.objects.filter(account=account).exclude(status=BankTransaction.STATUS_VOIDED)
        book = (moves.filter(direction='in').aggregate(t=Sum('amount'))['t'] or 0) - (
            moves.filter(direction='out').aggregate(t=Sum('amount'))['t'] or 0)
        diff = real - book
        self.stdout.write(f"  {account}: buku {book:,} {account.currency}, nyata {real:,}, selisih {diff:,}")
        if not diff:
            return
        if account.currency == 'SAR':
            diff_sar = diff
        elif account.currency == 'IDR':
            diff_sar = int((Decimal(diff) / rate).quantize(Decimal(1)))
        else:
            diff_sar = int((Decimal(diff) * rate).quantize(Decimal(1)))
        direction = 'in' if diff > 0 else 'out'
        record_bank_transaction(
            account=account, direction=direction, amount_sar=abs(diff_sar), currency=account.currency,
            amount=abs(diff), source_type='CutoverAdjustment', source_id=account.pk,
            transaction_date=day, reference='Penyesuaian saldo cutover', check_funds=False,
        )
        if diff_sar:
            side = 'debit' if diff_sar > 0 else 'credit'
            other = 'credit' if diff_sar > 0 else 'debit'
            from hw.finance.posting import native
            post_adjustment(
                lines=[
                    {'account': account.ledger_account_id, side: abs(diff_sar), 'branch': account.branch_id,
                     **native(account, abs(diff), rate)},
                    {'account': coa.OPENING_EQUITY, other: abs(diff_sar), 'branch': account.branch_id},
                ],
                description=f'Penyesuaian saldo cutover {account}',
                entry_date=day, created_by=self.user, idempotency_key=f'cutover:saldo:{account.pk}',
            )

    # ── laporan ──────────────────────────────────────────────────────────
    def _report(self, stats):
        from hw.finance import queries
        from hw.management.commands.check_finance import Command as Check

        self.stdout.write(
            f"Entry dibuat: charge {stats['charge']}, pembayaran {stats['payment']}, penukaran {stats['exchange']}, "
            f"kirim setoran {stats['send']}, "
            f"terima {stats['receive']}, alokasi penerimaan {stats['allocate']}; "
            f"kelebihan bayar CL batal ke deposit {stats['deposit']:,} SAR"
        )
        paid_docs = sum(int(p.amount_sar) for p in PaymentRecord.objects.filter(status=PaymentRecord.STATUS_CONFIRMED))
        paid_journal = sum(queries.invoice_paid_map(list(Invoice.objects.values_list('pk', flat=True))).values())
        self.stdout.write(f"Total pembayaran: dokumen {paid_docs:,} SAR, terbukukan ke invoice {paid_journal:,} SAR")
        for acc in queries.money_accounts_overview():
            self.stdout.write(f"  saldo buku {acc['name']} ({acc['branch']}): {acc['book_balance']:,} SAR")
        findings = [(label, rows) for label, rows in Check().run_checks() if rows]
        if findings:
            for label, rows in findings:
                self.stdout.write(self.style.WARNING(f'{label}: {len(rows)} temuan, mis. {rows[0]}'))
        else:
            self.stdout.write(self.style.SUCCESS('check_finance: semua cek lolos'))
