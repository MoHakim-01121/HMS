"""Audit integritas ledger jurnal — read-only, dijalankan sebelum cutover
produksi (dan berkala sesudahnya).

Jurnal (JournalEntry/JournalLine) sudah jadi system of record; tidak ada lagi
ledger legacy untuk dibandingkan. Perintah ini memeriksa jurnal terhadap
dirinya sendiri dan terhadap dokumen sumber (Invoice, PaymentRecord,
RemittanceLine):

  1. Rantai hash + nomor urut utuh (tamper-evidence).
  2. Setiap JournalEntry balance dalam SAR (Σdebit == Σcredit).
  3. Trial balance balance.
  4. Baris Piutang / Titipan selalu punya dimensi client.
  5. Total charge hidup per invoice == Invoice.total_sar (charge tak basi).
  6. Σ PaymentRecord (confirmed/allocated) per invoice == paid_sar jurnal.
  7. RemittanceLine vs jurnal kirim + jurnal alokasi penerimaan.
  8. Setiap entry reversal membalik tepat baris-baris entry yang dibaliknya.

Exit 1 kalau ada temuan. Tidak pernah menulis apa pun.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Sum

from hw.finance import accounts as coa
from hw.finance import hashing
from hw.finance import queries as fq
from hw.models import Invoice, Remittance, RemittanceLine
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--verbose', action='store_true', help='Cetak ringkasan tiap cek walau lolos.')

    def run_checks(self):
        """[(label, [findings])] for every check, in order. Also used by the
        month-end checklist (hw/finance/period_checklist.py)."""
        tb = fq.trial_balance()
        return [
            # 1. Rantai hash + seq
            ('Rantai hash / seq', hashing.verify_chain()),
            # 2. Setiap entry balance per mata uang
            ('Balance per entry', self._unbalanced_entries()),
            # 3. Trial balance
            ('Trial balance', [] if tb['balanced'] else [
                f'Trial balance timpang (debit {tb["total_debit"]:,} ≠ kredit {tb["total_credit"]:,})'
            ]),
            # 4. Dimensi client pada baris Piutang / Titipan
            ('Dimensi client (AR / Titipan)', self._lines_missing_client()),
            # 5. Charge hidup == Invoice.total_sar
            ('Charge jurnal vs total invoice', self._stale_charges()),
            # 6. PaymentRecord vs paid_sar jurnal
            ('PaymentRecord vs jurnal', self._payment_record_mismatch()),
            # 7. RemittanceLine vs jurnal
            ('RemittanceLine vs jurnal', self._remittance_line_mismatch()),
            # 8. Reversal menunjuk entry yang benar
            ('Integritas reversal', self._bad_reversals()),
            # 9. Pusat hanya menerima SAR (IDR/USD diterima & ditukar di cabang)
            ('Penerimaan non-SAR di Pusat', self._non_sar_received_at_hq()),
        ]

    def handle(self, *args, **options):
        problems = []
        for label, found in self.run_checks():
            if found:
                problems.extend(found)
                self.stdout.write(self.style.ERROR(f'[GAGAL] {label} — {len(found)} temuan'))
                for p in found:
                    self.stdout.write(self.style.ERROR(f'    • {p}'))
            elif options['verbose']:
                self.stdout.write(self.style.SUCCESS(f'[  OK  ] {label}'))

        self.stdout.write('')
        if problems:
            self.stdout.write(self.style.ERROR(f'{len(problems)} temuan total. Jurnal BELUM siap cutover.'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('Semua cek lolos. Jurnal konsisten.'))

    # ── cek individual ────────────────────────────────────────

    def _non_sar_received_at_hq(self):
        from hw.finance.accounts import HQ_BRANCH
        from hw.models.payment import PaymentRecord
        return [
            f'{p.payment_number}: {p.amount:,} {p.currency} diterima di Pusat'
            for p in PaymentRecord.objects.filter(status__in=PaymentRecord.EFFECTIVE_STATUSES)
            .exclude(receiving_account__currency='SAR').select_related('receiving_account')
            if p.receiving_branch_code == HQ_BRANCH
        ]

    def _entries(self):
        return JournalEntry.objects.all().prefetch_related('lines')

    def _unbalanced_entries(self):
        out = []
        for e in self._entries():
            # Debit/kredit selalu SAR; mata uang baris hanya mata uang transaksinya.
            d = sum(ln.debit for ln in e.lines.all())
            c = sum(ln.credit for ln in e.lines.all())
            if d != c:
                out.append(f'{e.entry_number}: debit {d:,} ≠ kredit {c:,}')
        return out

    def _lines_missing_client(self):
        rows = JournalLine.objects.filter(
            account_id__in=[coa.AR, coa.CUST_CREDIT],
            client__isnull=True,
        ).select_related('journal_entry')
        return [
            f'{r.journal_entry.entry_number} baris {r.line_no}: akun {r.account_id} tanpa client'
            for r in rows
        ]

    def _stale_charges(self):
        charged_invoice_ids = set(
            JournalLine.objects.filter(
                journal_entry__entry_type=JournalEntry.TYPE_CHARGE,
                account_id=coa.AR,
            ).values_list('invoice_id', flat=True)
        )
        charged_invoice_ids.discard(None)
        out = []
        for inv in Invoice.objects.filter(pk__in=charged_invoice_ids).exclude(status=Invoice.STATUS_VOID):
            charged = fq.invoice_charged_sar(inv.id)
            if charged != inv.total_sar:
                out.append(
                    f'{inv.invoice_number}: charge jurnal {charged:,} ≠ total invoice {inv.total_sar:,} '
                    f'(charge basi — invoice diubah tanpa re-post)'
                )
        return out

    def _payment_record_mismatch(self):
        by_invoice = defaultdict(int)
        for pr in PaymentRecord.objects.filter(
            status__in=PaymentRecord.EFFECTIVE_STATUSES,
        ).values('invoice_id', 'amount_sar'):
            by_invoice[pr['invoice_id']] += pr['amount_sar']
        out = []
        for invoice_id, pr_total in by_invoice.items():
            jl_paid = fq.invoice_paid_sar(invoice_id)
            if pr_total != jl_paid:
                inv = Invoice.objects.filter(pk=invoice_id).first()
                num = inv.invoice_number if inv else f'id={invoice_id}'
                out.append(f'{num}: Σ PaymentRecord {pr_total:,} ≠ paid_sar jurnal {jl_paid:,}')
        return out

    def _remittance_line_mismatch(self):
        """Transfer lama (tanpa IDR/kurs): Σ baris == terkirim jurnal.
        Transfer lump-sum: Σ baris <= terkirim (sisanya belum dialokasikan, sah),
        dan Σ baris alokasi penerimaan == Σ kredit reklasifikasi Kas SBY hidup."""
        reversed_ids = JournalEntry.objects.filter(
            reverses__isnull=False,
        ).values_list('reverses_id', flat=True)
        out = []
        for rem in Remittance.objects.all():
            if not fq.remittance_has_live_entries(rem.id):
                continue
            lines = RemittanceLine.objects.filter(settlement__remittance=rem)
            line_total = sum(int(l.amount_sar or 0) for l in lines)
            alloc_total = sum(int(l.amount_sar or 0) for l in lines if l.settlement_id)
            sent = int(fq.remittance_sent_sar(rem.id))
            if rem.amount_idr is None and line_total != sent:
                out.append(
                    f'{rem.remittance_number}: Σ RemittanceLine {line_total:,} ≠ terkirim jurnal {sent:,}'
                )
            if rem.amount_idr is not None and line_total > sent:
                out.append(
                    f'{rem.remittance_number}: Σ RemittanceLine {line_total:,} > terkirim jurnal {sent:,}'
                )
            journal_alloc = int(
                JournalLine.objects.filter(
                    journal_entry__entry_type=JournalEntry.TYPE_ALLOCATE,
                    journal_entry__source_remittance_settlement__isnull=False,
                    remittance_id=rem.id, account_id=rem.from_account.ledger_account_id,
                    invoice_line__isnull=False,
                ).exclude(journal_entry_id__in=reversed_ids)
                .aggregate(c=Sum('credit'))['c'] or 0
            )
            if alloc_total != journal_alloc:
                out.append(
                    f'{rem.remittance_number}: Σ alokasi penerimaan {alloc_total:,} ≠ jurnal alokasi {journal_alloc:,}'
                )
        return out

    def _bad_reversals(self):
        out = []
        for e in JournalEntry.objects.filter(reverses__isnull=False).prefetch_related('lines', 'reverses__lines'):
            mirror = sorted((l.account_id, l.credit, l.debit, l.invoice_line_id) for l in e.reverses.lines.all())
            mine = sorted((l.account_id, l.debit, l.credit, l.invoice_line_id) for l in e.lines.all())
            if mine != mirror:
                out.append(f'{e.entry_number}: tidak membalik {e.reverses.entry_number} baris demi baris')
        return out
