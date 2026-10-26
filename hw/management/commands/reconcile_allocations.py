"""Samakan alokasi pembayaran dengan buku besar untuk kelebihan bayar invoice
yang dulu dipindah ke deposit lewat jurnal saja.

Sebelum perbaikan 2026-10-05, "Pindahkan ke deposit" di detail invoice hanya
memposting jurnal (DR Piutang baris / CR Titipan, sumber Invoice): buku besar
benar, tapi alokasi pembayaran yang membayar baris itu tidak dikurangi, jadi
detail pembayaran dan kwitansinya masih menunjukkan uang di reservasi.

Untuk setiap entry seperti itu yang alokasinya memang menyimpang, perintah ini
membalik entry lama lalu mengulang pemindahan lewat jalur pembayaran
(posting._shift_excess_to_deposit): alokasi dikurangi, deposited_sar naik,
dan jurnalnya atas nama pembayaran. Saldo deposit dan piutang tidak berubah.

Penyimpangan lain (mis. sisa "Move Funds" yang sudah dipensiunkan) hanya
dilaporkan untuk ditinjau manual; lihat juga `check_finance` cek 10.

Tanpa --apply hanya menampilkan rencana; tidak ada yang ditulis.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from hw.finance import accounts as coa
from hw.finance import posting
from hw.finance import queries as fq
from hw.models.journal import JournalEntry
from hw.models.payment import PaymentAllocation, PaymentRecord


def _drift(line_id):
    """Alokasi pembayaran efektif pada baris − pelunasan baris di jurnal."""
    allocated = PaymentAllocation.objects.filter(
        invoice_line_id=line_id, payment__status__in=PaymentRecord.EFFECTIVE_STATUSES,
    ).aggregate(t=Sum('amount_sar'))['t'] or 0
    a = fq._settling(invoice_line_id=line_id).aggregate(d=Sum('debit'), c=Sum('credit'))
    return allocated - ((a['c'] or 0) - (a['d'] or 0))


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Tulis perbaikannya (bawaan: hanya rencana).')
        parser.add_argument('--user', help='Username pencatat jurnal koreksi (bawaan: superuser pertama).')

    def handle(self, *args, **options):
        from django.contrib.auth.models import User
        user = (User.objects.get(username=options['user']) if options.get('user')
                else User.objects.filter(is_superuser=True).order_by('pk').first())

        candidates = (
            JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_TRANSFER, source_invoice__isnull=False)
            .filter(lines__account_id=coa.CUST_CREDIT, lines__credit__gt=0).distinct().live().order_by('seq')
        )
        plan, manual = [], []
        for entry in candidates:
            debits = {
                ln.invoice_line: ln.debit
                for ln in entry.lines.filter(account_id=coa.AR, debit__gt=0, invoice_line__isnull=False)
                .select_related('invoice_line__invoice')
            }
            if not debits:
                continue
            drifts = {line: _drift(line.pk) for line in debits}
            if all(drifts[line] >= amt for line, amt in debits.items()):
                plan.append((entry, debits))
            elif any(d for d in drifts.values()):
                manual.append(f'{entry.entry_number}: penyimpangan sebagian, tinjau manual')

        for entry, debits in plan:
            parts = ', '.join(f'{l.invoice.invoice_number} {l.label} {amt:,}' for l, amt in debits.items())
            self.stdout.write(f'{entry.entry_number} ({entry.description}): {parts}')
        for note in manual:
            self.stdout.write(self.style.WARNING(note))
        if not plan:
            self.stdout.write(self.style.SUCCESS('Tidak ada yang perlu diperbaiki.'))
            return
        if not options['apply']:
            self.stdout.write(self.style.WARNING(f'{len(plan)} entry akan diperbaiki. Jalankan dengan --apply.'))
            return

        today = timezone.localdate()
        with transaction.atomic():
            for entry, debits in plan:
                posting.reverse_entry(entry, reversal_date=today, created_by=user,
                                      note='Diulang lewat pembayaran (reconcile_allocations)')
                leftover = posting._shift_excess_to_deposit(debits, created_by=user, entry_date=today)
                if leftover:
                    raise RuntimeError(f'{entry.entry_number}: sisa tak terkait alokasi {leftover}')
        self.stdout.write(self.style.SUCCESS(f'{len(plan)} entry diperbaiki.'))
