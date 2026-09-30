"""Schema v2 F2a — Branch.is_hq, Client.name_key (UNIQUE), Client.owner_branch.

name_key diisi dari nama perusahaan yang dinormalisasi. Bila database ini
sudah punya client bernama sama (produksi: "SAFAAR" dan "Safaar"), baris kedua
dst. diberi akhiran " #<id>" supaya UNIQUE bisa terpasang tanpa kehilangan
data; penggabungan client dobel adalah keputusan manual (lihat
docs/superpowers/specs/2026-09-29-keputusan-data-produksi.md, bagian B).
"""
import re
import unicodedata

import django.db.models.deletion
from django.db import migrations, models

import hw.models.client

_LEGAL_FORMS = {'pt', 'cv', 'tbk', 'persero', 'ud'}


def _name_key(name):
    text = unicodedata.normalize('NFKC', name or '').lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = [t for t in text.split() if t not in _LEGAL_FORMS]
    return ' '.join(tokens) or ' '.join(text.split())


def mark_hq(apps, schema_editor):
    apps.get_model('hw', 'Branch').objects.filter(code='pusat').update(is_hq=True)


def fill_name_keys(apps, schema_editor):
    Client = apps.get_model('hw', 'Client')
    seen = set()
    for client in Client.objects.order_by('pk'):
        key = _name_key(client.name) or f'client {client.pk}'
        if key in seen:
            key = f'{key} #{client.pk}'
        seen.add(key)
        Client.objects.filter(pk=client.pk).update(name_key=key)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0121_currency_document_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='branch',
            name='is_hq',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_hq, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='branch',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_hq', True)), fields=('is_hq',), name='branch_single_hq',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='name_key',
            field=models.CharField(default='', editable=False, max_length=200),
            preserve_default=False,
        ),
        migrations.RunPython(fill_name_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='client',
            name='name_key',
            field=models.CharField(editable=False, max_length=200, unique=True),
        ),
        migrations.AddField(
            model_name='client',
            name='owner_branch',
            field=models.ForeignKey(
                default=hw.models.client.default_owner_branch,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='clients', to='hw.branch',
            ),
        ),
    ]
