"""Hapus PaymentAllocation milik payment yang sudah mati (rejected/reversed/voided).

Dulu Reverse (dan re-sync pembayaran dari form invoice) mengubah status ke
REVERSED tanpa menghapus alokasinya. Baris sisa itu membuat payment mati masih
terbaca "teralokasi" dan membuat reservasinya tidak bisa dihapus dari invoice
(invoice_views._reservation_has_money). Kode sekarang sudah membersihkannya
saat reject/void/reverse; perintah ini membereskan data lama.

Default hanya menampilkan temuan (dry-run). Pakai --apply untuk menghapus.
Isi setiap alokasi yang dihapus dicatat di PaymentLog payment-nya.

  python manage.py clear_dead_payment_allocations
  python manage.py clear_dead_payment_allocations --apply --user admin
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hw.finance.posting import clear_payment_allocations
from hw.models.payment import PaymentLog, PaymentRecord


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Benar-benar hapus (default: dry-run).')
        parser.add_argument('--user', help='Username yang tercatat di PaymentLog (wajib dengan --apply).')

    def handle(self, *args, **options):
        dead = (
            PaymentRecord.objects
            .exclude(status__in=PaymentRecord.EFFECTIVE_STATUSES + (PaymentRecord.STATUS_PENDING,))
            .filter(allocations__isnull=False)
            .distinct()
            .order_by('payment_number')
        )
        found = [(p, list(p.allocations.all())) for p in dead]
        if not found:
            self.stdout.write(self.style.SUCCESS('Tidak ada alokasi basi.'))
            return

        for p, allocs in found:
            total = sum(a.amount_sar for a in allocs)
            self.stdout.write(f'{p.payment_number} [{p.status}] - {len(allocs)} alokasi, {total:,} SAR')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                f'Dry-run: {len(found)} payment. Jalankan ulang dengan --apply --user <username> untuk menghapus.'
            ))
            return

        if not options['user']:
            raise CommandError('--user wajib diisi bersama --apply (dicatat di PaymentLog).')
        try:
            user = User.objects.get(username=options['user'])
        except User.DoesNotExist:
            raise CommandError(f'User {options["user"]!r} tidak ditemukan.') from None

        with transaction.atomic():
            for p, _ in found:
                dropped = clear_payment_allocations(p)
                PaymentLog.objects.create(
                    payment=p,
                    action=PaymentLog.ACTION_UPDATED,
                    before_state={'status': p.status, 'allocations': dropped},
                    after_state={'status': p.status, 'allocations': []},
                    performed_by=user,
                    note='Cleanup: alokasi basi dari payment mati dihapus',
                )
        self.stdout.write(self.style.SUCCESS(f'Selesai: alokasi dari {len(found)} payment dihapus.'))
