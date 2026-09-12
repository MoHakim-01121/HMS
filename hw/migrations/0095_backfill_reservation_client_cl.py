"""Backfill Reservation.confirmation_letter / Reservation.client for historical
rows, using the exact same implicit rule the live sync already trusts
(hw/views/cl_views.py::_sync_invoice_reservation_from_cl): same invoice,
reservation_number == cl.confirmation_number. Not a new/riskier heuristic —
just materializing a matching rule the app already relies on into a real FK.

Reservations with no matching CL on their invoice (manual invoice-form rows,
never linked to a CL) are left with confirmation_letter=NULL — correct, not
every reservation originates from a CL.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    ConfirmationLetter = apps.get_model('hw', 'ConfirmationLetter')
    Reservation = apps.get_model('hw', 'Reservation')

    cls_by_invoice = {}
    for cl in ConfirmationLetter.objects.filter(invoice_id__isnull=False).only(
        'id', 'invoice_id', 'confirmation_number', 'client_id',
    ):
        cls_by_invoice.setdefault(cl.invoice_id, {})[cl.confirmation_number] = cl

    updates = []
    for r in Reservation.objects.filter(confirmation_letter__isnull=True).only(
        'id', 'invoice_id', 'reservation_number', 'client_id',
    ):
        cl = cls_by_invoice.get(r.invoice_id, {}).get(r.reservation_number)
        if cl is None:
            continue
        r.confirmation_letter_id = cl.id
        if not r.client_id and cl.client_id:
            r.client_id = cl.client_id
        updates.append(r)

    if updates:
        Reservation.objects.bulk_update(updates, ['confirmation_letter', 'client'], batch_size=500)

    # Reservations still without a client: fall back to their invoice's client
    # (covers manual invoice-form rows never linked to a CL).
    Invoice = apps.get_model('hw', 'Invoice')
    invoice_clients = dict(Invoice.objects.filter(client_id__isnull=False).values_list('id', 'client_id'))
    fallback_updates = []
    for r in Reservation.objects.filter(client__isnull=True).only('id', 'invoice_id'):
        client_id = invoice_clients.get(r.invoice_id)
        if client_id:
            r.client_id = client_id
            fallback_updates.append(r)
    if fallback_updates:
        Reservation.objects.bulk_update(fallback_updates, ['client'], batch_size=500)


def unbackfill(apps, schema_editor):
    apps.get_model('hw', 'Reservation').objects.update(confirmation_letter=None, client=None)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0094_reservation_client_reservation_confirmation_letter'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
