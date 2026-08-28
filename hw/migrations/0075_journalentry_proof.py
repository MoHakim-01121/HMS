# Fase 7 Unit B: lampiran dokumen sumber di JournalEntry (mis. bukti transfer
# refund). Sebelumnya bukti refund menempel di CashMovement (shadow table yang
# dipensiunkan); sekarang dibawa oleh entry jurnal refund itu sendiri.
#
# proof adalah metadata (FileField) -- tidak ikut entry_hash, tidak dilindungi
# trigger append-only selain INSERT itu sendiri.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0074_backfill_journalline_client'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalentry',
            name='proof',
            field=models.FileField(blank=True, null=True, upload_to='ledger/proof/'),
        ),
    ]