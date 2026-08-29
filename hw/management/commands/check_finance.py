"""Audit integritas ledger jurnal — read-only, dijalankan sebelum cutover
produksi (dan berkala sesudahnya).

Jurnal (JournalEntry/JournalLine) sudah jadi system of record; tidak ada lagi
ledger legacy untuk dibandingkan. Perintah ini memeriksa jurnal terhadap
dirinya sendiri dan terhadap dokumen sumber (Invoice, PaymentRecord,
RemittanceLine):

  1. Rantai hash + nomor urut per company utuh (tamper-evidence).
  2. Setiap JournalEntry balance per mata uang (Σdebit == Σcredit).
  3. Trial balance per company balance.
  4. Baris Piutang / Titipan selalu punya dimensi client.
  5. Total charge hidup per invoice == Invoice.total_sar (charge tak basi).
  6. Σ PaymentRecord (confirmed/allocated) per invoice == paid_sar jurnal.
  7. Σ RemittanceLine per remittance == total terkirim di jurnal.
  8. Setiap entry reversal menunjuk entry yang benar dan ber-flag is_reversal.

Exit 1 kalau ada temuan. Tidak pernah menulis apa pun.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from hw.finance import accounts as coa
from hw.finance import hashing
from hw.finance import queries as fq
from hw.models import Invoice, Remittance, RemittanceLine
from hw.models.choices import Company
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--company', help='Batasi ke satu company (default: semua).')
        parser.add_argument('--verbose', action='store_true', help='Cetak ringkasan tiap cek walau lolos.')

    def handle(self, *args, **options):
        companies = [options['company']] if options['company'] else list(Company.values)
        problems = []
        ok = self.stdout.write

        def check(label, found):
            if found:
                problems.extend(found)
                self.stdout.write(self.style.ERROR(f'[GAGAL] {label} — {len(found)} temuan'))
                for p in found:
                    self.stdout.write(self.style.ERROR(f'    • {p}'))
            elif options['verbose']:
                self.stdout.write(self.style.SUCCESS(f'[  OK  ] {label}'))

        # 1. Rantai hash + seq per company
        for company in companies:
            check(f'Rantai hash / seq ({company})', hashing.verify_chain(company))

        # 2. Setiap entry balance per mata uang
        check('Balance per entry', self._unbalanced_entries(companies))

        # 3. Trial balance per company
        for company in companies:
            tb = fq.trial_balance(company=company)
            if not tb['balanced']:
                problems.append(
                    f'{company}: trial balance timpang (debit {tb["total_debit"]:,} '
                    f'≠ kredit {tb["total_credit"]:,})'
                )
                self.stdout.write(self.style.ERROR(f'[GAGAL] Trial balance ({company})'))
            elif options['verbose']:
                self.stdout.write(self.style.SUCCESS(f'[  OK  ] Trial balance ({company})'))

        # 4. Dimensi client pada baris Piutang / Titipan
        check('Dimensi client (AR / Titipan)', self._lines_missing_client(companies))

        # 5. Charge hidup == Invoice.total_sar
        check('Charge jurnal vs total invoice', self._stale_charges(companies))

        # 6. PaymentRecord vs paid_sar jurnal
        check('PaymentRecord vs jurnal', self._payment_record_mismatch(companies))

        # 7. RemittanceLine vs jurnal
        check('RemittanceLine vs jurnal', self._remittance_line_mismatch(companies))

        # 8. Reversal menunjuk entry yang benar
        check('Integritas reversal', self._bad_reversals(companies))

        self.stdout.write('')
        if problems:
            self.stdout.write(self.style.ERROR(f'{len(problems)} temuan total. Jurnal BELUM siap cutover.'))
            raise SystemExit(1)
        ok(self.style.SUCCESS('Semua cek lolos. Jurnal konsisten.'))

    # ── cek individual ────────────────────────────────────────

    def _entries(self, companies):
        return JournalEntry.objects.filter(company__in=companies).prefetch_related('lines')

    def _unbalanced_entries(self, companies):
        out = []
        for e in self._entries(companies):
            by_cur = defaultdict(lambda: [0, 0])
            for ln in e.lines.all():
                by_cur[ln.currency][0] += ln.debit
                by_cur[ln.currency][1] += ln.credit
            for cur, (d, c) in by_cur.items():
                if d != c:
                    out.append(f'{e.entry_number} ({cur}): debit {d:,} ≠ kredit {c:,}')
        return out

    def _lines_missing_client(self, companies):
        rows = JournalLine.objects.filter(
            journal_entry__company__in=companies,
            account_id__in=[coa.AR, coa.CUST_CREDIT],
            client__isnull=True,
        ).select_related('journal_entry')
        return [
            f'{r.journal_entry.entry_number} baris {r.line_no}: akun {r.account_id} tanpa client'
            for r in rows
        ]

    def _stale_charges(self, companies):
        charged_invoice_ids = set(
            JournalLine.objects.filter(
                journal_entry__company__in=companies,
                journal_entry__entry_type=JournalEntry.TYPE_CHARGE,
                account_id=coa.AR,
            ).values_list('invoice_id', flat=True)
        )
        charged_invoice_ids.discard(None)
        out = []
        for inv in Invoice.objects.filter(pk__in=charged_invoice_ids):
            charged = fq.invoice_charged_sar(inv.id)
            if charged != inv.total_sar:
                out.append(
                    f'{inv.invoice_number}: charge jurnal {charged:,} ≠ total invoice {inv.total_sar:,} '
                    f'(charge basi — invoice diubah tanpa re-post)'
                )
        return out

    def _payment_record_mismatch(self, companies):
        by_invoice = defaultdict(int)
        for pr in PaymentRecord.objects.filter(
            company__in=companies, status__in=PaymentRecord.EFFECTIVE_STATUSES,
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

    def _remittance_line_mismatch(self, companies):
        out = []
        for rem in Remittance.objects.filter(company__in=companies):
            if not fq.remittance_has_live_entries(rem.id):
                continue
            line_total = sum(
                int(l.amount_sar or 0)
                for l in RemittanceLine.objects.filter(remittance=rem)
            )
            sent = int(fq.remittance_sent_sar(rem.id))
            if line_total != sent:
                out.append(
                    f'{rem.remittance_number}: Σ RemittanceLine {line_total:,} ≠ terkirim jurnal {sent:,}'
                )
        return out

    def _bad_reversals(self, companies):
        out = []
        for e in JournalEntry.objects.filter(
            company__in=companies, reverses__isnull=False,
        ).select_related('reverses'):
            if not e.is_reversal:
                out.append(f'{e.entry_number}: menunjuk reverses tapi is_reversal=False')
            if e.reverses and e.reverses.company != e.company:
                out.append(f'{e.entry_number}: me-reverse entry company lain')
        return out
