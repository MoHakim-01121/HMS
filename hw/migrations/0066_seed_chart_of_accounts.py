"""Seed Chart of Accounts (LedgerAccount) so the FK from JournalLine.account
always resolves — in prod and in the test database."""
from django.db import migrations


def seed(apps, schema_editor):
    LedgerAccount = apps.get_model("hw", "LedgerAccount")
    from hw.finance.accounts import ACCOUNTS, normal_balance_for

    for spec in ACCOUNTS:
        LedgerAccount.objects.update_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "type": spec["type"],
                "normal_balance": normal_balance_for(spec["type"]),
                "is_postable": spec.get("is_postable", True),
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    apps.get_model("hw", "LedgerAccount").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("hw", "0065_financialperiod_company_and_more")]
    operations = [migrations.RunPython(seed, unseed)]
