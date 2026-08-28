# Fase 7 Unit A: backfill JournalLine.client untuk baris lama yang NULL.
#
# Sebelum invoice_views.py memperbaiki urutan CL-link (lihat
# backfill_ledger_client.py), sebagian Invoice.client kosong saat posting,
# sehingga dimensi analitik JournalLine.client ikut NULL. Command
# backfill_ledger_client.py hanya mengisi tabel legacy Charge/Allocation/
# CashMovement -- BUKAN jurnal.
#
# Migration ini mengisi JournalLine.client dengan aturan yang PERSIS sama
# dengan _billing_client() di hw/views/invoice_billing.py (di-copy inline agar
# migration tetap berfungsi walau kode view berubah): client tunggal dari
# CL-CL invoice; >1 client berbeda = ambiguous -> biarkan NULL; tanpa CL atau
# CL tanpa client -> fallback ke Invoice.client.
#
# Dengan ini pembacaan jurnal-only (Fase 7 Unit B dst.) tidak kehilangan
# invoice lama yang client-nya sudah ter-resolve.
#
# Hanya menyentuh baris JournalLine dengan invoice terisi dan client NULL.
# reverse = mengembalikan NULL hanya untuk baris yang diisi migration ini
# (aman walau sudah ada baris NULL-client baru setelahnya).
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# (invoice_id, client_id) yang diisi + line ids, dicatat untuk reverse.
_BACKFILLED_LINE_IDS = []


# Inline rule _billing_client(): kembalikan client_id atau None.
def _resolve_client_id(invoice):
    clients = {
        cl.client_id: cl.client_id
        for cl in invoice.confirmation_letters.select_related('client')
        if cl.client_id
    }
    if len(clients) == 1:
        return next(iter(clients.values()))
    if len(clients) > 1:
        return None
    return invoice.client_id


def backfill_journal_line_client(apps, schema_editor):
    JournalLine = apps.get_model('hw', 'JournalLine')
    Invoice = apps.get_model('hw', 'Invoice')

    rows = list(
        JournalLine.objects
        .filter(client__isnull=True, invoice__isnull=False)
        .values_list('id', 'invoice_id')
    )
    if not rows:
        logger.info('[Fase7/A] no NULL-client journal lines to backfill.')
        return

    by_invoice = {}
    for line_id, invoice_id in rows:
        by_invoice.setdefault(invoice_id, []).append(line_id)

    unresolvable = []
    updated_ids = []
    for invoice in (
        Invoice.objects
        .filter(pk__in=by_invoice)
        .prefetch_related('confirmation_letters')
    ):
        line_ids = by_invoice[invoice.pk]
        client_id = _resolve_client_id(invoice)
        if client_id is None:
            unresolvable.append(invoice)
            continue
        qs = JournalLine.objects.filter(pk__in=line_ids, client__isnull=True)
        hit = list(qs.values_list('pk', flat=True))
        if hit:
            qs.update(client_id=client_id)
            updated_ids.extend(hit)

    _BACKFILLED_LINE_IDS.extend(updated_ids)

    logger.info(
        '[Fase7/A] backfilled JournalLine.client on %d line(s) across %d invoice(s); '
        '%d invoice(s) left NULL (unresolvable: no CL / CL without client / ambiguous).',
        len(updated_ids), len(by_invoice), len(unresolvable),
    )
    if unresolvable:
        numbers = list(
            Invoice.objects.filter(pk__in=[u.pk for u in unresolvable])
            .values_list('invoice_number', flat=True)
        )
        sample = ', '.join(str(n) for n in numbers[:10])
        logger.warning(
            '[Fase7/A] left NULL for manual review (%d): %s%s',
            len(numbers), sample, ' ...' if len(numbers) > 10 else '',
        )


def undo_backfill(apps, schema_editor):
    if not _BACKFILLED_LINE_IDS:
        return
    JournalLine = apps.get_model('hw', 'JournalLine')
    n = JournalLine.objects.filter(
        pk__in=_BACKFILLED_LINE_IDS, client__isnull=False, invoice__isnull=False,
    ).update(client_id=None)
    logger.info('[Fase7/A] revert: %d journal line(s) back to NULL client.', n)
    _BACKFILLED_LINE_IDS.clear()


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0073_remove_cancellationpenalty_client_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_journal_line_client, undo_backfill),
    ]