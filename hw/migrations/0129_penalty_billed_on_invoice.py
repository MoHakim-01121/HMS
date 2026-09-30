"""Schema v2 F5a — denda pembatalan ditagih sebagai baris invoice.

CancellationPenalty tidak lagi menyimpan invoice maupun status bayarnya:
invoice-nya adalah baris invoice (kind = penalty) yang menunjuk denda itu, dan
lunas-tidaknya dihitung dari uang yang diterima untuk reservasinya.

Denda yang reservasinya sedang ditagih langsung dibuatkan baris dendanya.
Denda yang reservasinya belum ditagih tetap tanpa baris sampai reservasi itu
masuk ke invoice (atau dendanya disimpan ulang, yang menerbitkan invoice).

Migrasi berhenti bila ada denda bertanda lunas atau yang sudah punya jurnal
sendiri: keduanya dicatat di luar invoice, jadi uangnya harus dipindahkan oleh
orang (catat pembayarannya lewat modul Payment setelah migrasi).
"""
from django.db import migrations

from hw.db_pg import settle_constraints


def bill_existing_penalties(apps, schema_editor):
    Penalty = apps.get_model('hw', 'CancellationPenalty')
    Line = apps.get_model('hw', 'InvoiceLine')
    JournalEntry = apps.get_model('hw', 'JournalEntry')

    problems = [
        f'{p.penalty_number}: bertanda lunas' for p in Penalty.objects.filter(is_paid=True).order_by('pk')
    ]
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
    live = set(
        JournalEntry.objects.filter(reference_type='CancellationPenalty', is_reversal=False)
        .exclude(pk__in=reversed_ids).values_list('reference_id', flat=True)
    )
    problems += [
        f'{p.penalty_number}: punya jurnal denda sendiri' for p in Penalty.objects.filter(pk__in=live).order_by('pk')
    ]
    if problems:
        raise RuntimeError(
            'Denda berikut dicatat di luar invoice dan perlu dibereskan dulu: ' + '; '.join(problems[:40])
            + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
        )

    for penalty in Penalty.objects.order_by('pk'):
        hotel_line = Line.objects.filter(
            kind='hotel', confirmation_letter_id=penalty.cl_id, voided_at__isnull=True,
        ).first()
        if hotel_line is None:
            continue
        if Line.objects.filter(kind='penalty', penalty_id=penalty.pk, voided_at__isnull=True).exists():
            continue
        last = (
            Line.objects.filter(invoice_id=hotel_line.invoice_id).order_by('-line_no')
            .values_list('line_no', flat=True).first() or 0
        )
        Line.objects.create(invoice_id=hotel_line.invoice_id, kind='penalty', penalty_id=penalty.pk, line_no=last + 1)
    settle_constraints(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0128_invoice_line'),
    ]

    operations = [
        migrations.RunPython(bill_existing_penalties, migrations.RunPython.noop),
        migrations.RemoveField(model_name='cancellationpenalty', name='invoice'),
        migrations.RemoveField(model_name='cancellationpenalty', name='is_paid'),
        migrations.RemoveField(model_name='cancellationpenalty', name='payment_date'),
        migrations.RemoveField(model_name='cancellationpenalty', name='payment_method'),
        migrations.RemoveField(model_name='cancellationpenalty', name='payment_note'),
    ]
