"""Aturan yang hanya bisa dibuktikan di PostgreSQL: konkurensi dan trigger.

Dilewati di SQLite. Jalankan dengan TEST_DATABASE_URL (config/settings.py).
"""
import threading
from datetime import date

from django.contrib.auth.models import User
from django.db import connection, connections, transaction
from django.db.utils import DatabaseError
from django.test import TransactionTestCase

from hw.db_pg import pg_only
from hw.finance import accounts as coa
from hw.finance.hashing import verify_chain
from hw.finance.posting import post_entry
from hw.models import ConfirmationLetter, DocumentSequence
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_cl

WORKERS = 8


def _run_parallel(fn):
    """Jalankan fn() di WORKERS thread yang dimulai bersamaan (barrier)."""
    barrier = threading.Barrier(WORKERS)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(fn())
        except Exception as exc:  # dikumpulkan, dilaporkan oleh test
            errors.append(repr(exc))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


@pg_only
class ParallelNumberingTest(TransactionTestCase):
    # TransactionTestCase mengosongkan tabel; pulihkan data seed migrasi
    # (cabang, bagan akun) yang dibutuhkan test ini.
    serialized_rollback = True

    def test_parallel_allocation_never_duplicates(self):
        make_cl(
            confirmation_number='CL-100', hotel_name='H', guest_name='G',
            check_in=date(2040, 1, 1), check_out=date(2040, 1, 2),
        )

        def allocate_and_insert():
            with transaction.atomic():
                number = ConfirmationLetter.generate_number()
                make_cl(
                    confirmation_number=number, hotel_name='H', guest_name='G',
                    check_in=date(2040, 1, 1), check_out=date(2040, 1, 2),
                )
                return number

        numbers, errors = _run_parallel(allocate_and_insert)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(numbers), [f'CL-{n:03d}' for n in range(101, 101 + WORKERS)])
        self.assertEqual(DocumentSequence.objects.get(key='CL').last_value, 100 + WORKERS)


@pg_only
class ParallelPostingTest(TransactionTestCase):
    # TransactionTestCase mengosongkan tabel; pulihkan data seed migrasi
    # (cabang, bagan akun) yang dibutuhkan test ini.
    serialized_rollback = True

    def setUp(self):
        self.user = User.objects.create_user('fin', password='x')
        FinancialPeriod.objects.create(name='2040-01', date_from=date(2040, 1, 1), date_to=date(2040, 1, 31))

    def test_parallel_posting_keeps_seq_and_hash_chain_intact(self):
        user = self.user

        def post():
            return post_entry(
                entry_type=JournalEntry.TYPE_ADJUSTMENT, description='p',
                entry_date=date(2040, 1, 10), created_by=user,
                lines=[
                    {'account': coa.CASH_SBY, 'debit': 100, 'credit': 0},
                    {'account': coa.OPENING_EQUITY, 'debit': 0, 'credit': 100},
                ],
            ).seq

        seqs, errors = _run_parallel(post)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(seqs), list(range(1, WORKERS + 1)))
        self.assertEqual(verify_chain(), [])
        numbers = list(JournalEntry.objects.values_list('entry_number', flat=True))
        self.assertEqual(len(numbers), len(set(numbers)))


@pg_only
class AppendOnlyTriggerTest(TransactionTestCase):
    # TransactionTestCase mengosongkan tabel; pulihkan data seed migrasi
    # (cabang, bagan akun) yang dibutuhkan test ini.
    serialized_rollback = True

    def setUp(self):
        user = User.objects.create_user('fin', password='x')
        FinancialPeriod.objects.create(name='2040-01', date_from=date(2040, 1, 1), date_to=date(2040, 1, 31))
        post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT, description='x',
            entry_date=date(2040, 1, 10), created_by=user,
            lines=[
                {'account': coa.CASH_SBY, 'debit': 100, 'credit': 0},
                {'account': coa.OPENING_EQUITY, 'debit': 0, 'credit': 100},
            ],
        )

    def test_bulk_update_rejected(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                JournalLine.objects.update(note='diubah')

    def test_bulk_delete_rejected(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                JournalEntry.objects.all()._raw_delete(connection.alias)
