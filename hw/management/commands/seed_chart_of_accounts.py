"""Seed / perbarui Chart of Accounts (tabel LedgerAccount). Idempotent.

Usage:
    python manage.py seed_chart_of_accounts
"""
from django.core.management.base import BaseCommand

from hw.finance.accounts import seed_chart_of_accounts


class Command(BaseCommand):
    help = "Seed the Chart of Accounts (LedgerAccount) — idempotent"

    def handle(self, *args, **options):
        n = seed_chart_of_accounts()
        self.stdout.write(self.style.SUCCESS(f"Chart of Accounts seeded: {n} account(s)."))
