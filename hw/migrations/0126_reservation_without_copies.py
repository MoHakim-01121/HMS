"""Schema v2 F3 — reservasi (CL) dan kamarnya tanpa salinan teks.

CL: client dan hotel wajib (PROTECT), tanggal wajib, status dibatasi tiga nilai;
kolom salinan hotel_name dan guest_name dihapus (dibaca dari Hotel/Client).
Room: tipe kamar wajib lewat FK; teks room_type dan meals dihapus setelah
dipetakan ke master.

Migrasi berhenti dengan pesan yang menyebut nomor CL bila ada data yang belum
bisa dipetakan — keputusan manualnya ada di
docs/superpowers/specs/2026-09-29-keputusan-data-produksi.md.
"""
import django.db.models.deletion
from django.db import migrations, models

from hw.db_pg import settle_constraints
from hw.migrations import _cutover

STATUSES = ['TENTATIVE', 'DEFINITE', 'CANCELLED']
CAPACITY_BY_TEXT = {'single': 1, 'double': 2, 'twin': 2, 'triple': 3, 'quad': 4, 'quint': 5}


def link_cl_to_masters(apps, schema_editor):
    """Isi hotel dan client CL dari teks salinannya bila cocok persis dengan
    satu baris master (hotel: nama; client: nama atau brand, lewat
    client_name_key). Yang tidak cocok dibiarkan kosong dan dilaporkan oleh
    langkah berikutnya untuk diputuskan manual."""
    from hw.models.client import client_name_key

    CL = apps.get_model('hw', 'ConfirmationLetter')
    Hotel = apps.get_model('hw', 'Hotel')
    Client = apps.get_model('hw', 'Client')

    hotels = {}
    for h in Hotel.objects.all():
        hotels.setdefault(' '.join(h.name.lower().split()), []).append(h.pk)
    clients = {}
    for c in Client.objects.all():
        for text in {c.name, c.brand}:
            if text:
                clients.setdefault(client_name_key(text), set()).add(c.pk)

    for cl in CL.objects.filter(models.Q(hotel_id__isnull=True) | models.Q(client_id__isnull=True)):
        updates = {}
        if cl.hotel_id is None:
            found = hotels.get(' '.join((cl.hotel_name or '').lower().split()), [])
            if len(found) == 1:
                updates['hotel_id'] = found[0]
        if cl.client_id is None and (cl.guest_name or '').strip():
            found = clients.get(client_name_key(cl.guest_name), set())
            if len(found) == 1:
                updates['client_id'] = next(iter(found))
        if updates:
            CL.objects.filter(pk=cl.pk).update(**updates)


def check_and_normalise_cl(apps, schema_editor):
    CL = apps.get_model('hw', 'ConfirmationLetter')
    problems = []
    for cl in CL.objects.order_by('pk'):
        missing = [
            label for label, value in (
                ('client', cl.client_id), ('hotel', cl.hotel_id),
                ('check_in', cl.check_in), ('check_out', cl.check_out),
            ) if value is None
        ]
        status = (cl.reservation_status or '').strip().upper()
        if status not in STATUSES:
            missing.append(f'status "{cl.reservation_status}"')
        elif status != cl.reservation_status:
            CL.objects.filter(pk=cl.pk).update(reservation_status=status)
        if missing:
            problems.append(f'{cl.confirmation_number}: {", ".join(missing)}')
    if problems:
        raise RuntimeError(
            'CL berikut belum lengkap, lengkapi dulu sebelum migrasi ini: ' + '; '.join(problems[:40])
            + (f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else '')
        )
    settle_constraints(schema_editor)


def link_rooms_to_masters(apps, schema_editor):
    Room = apps.get_model('hw', 'Room')
    RoomType = apps.get_model('hw', 'RoomType')
    MealPlan = apps.get_model('hw', 'MealPlan')
    plans = {code.upper(): code for code in MealPlan.objects.values_list('code', flat=True)}

    for room in Room.objects.select_related('cl').order_by('pk'):
        updates = {}
        if room.room_type_ref_id is None:
            text = (room.room_type or '').strip() or 'Room'
            hotel_id = room.cl.hotel_id
            rt = RoomType.objects.filter(hotel_id=hotel_id, name__iexact=text).first()
            if rt is None:
                capacity = CAPACITY_BY_TEXT.get(text.split()[0].lower())
                if capacity:
                    rt = RoomType.objects.filter(hotel_id=hotel_id, capacity=capacity, view='').order_by('pk').first()
                if rt is None:
                    rt = RoomType.objects.create(
                        hotel_id=hotel_id, name=text[:100], capacity=capacity or 1, view='', is_active=True,
                    )
            updates['room_type_ref_id'] = rt.pk
        meals = (room.meals or '').strip()
        if room.meal_plan_id is None and meals:
            code = plans.get(meals.upper())
            if code:
                updates['meal_plan_id'] = code
            else:
                updates['note'] = meals[:100]   # mis. "RO/FB", "BB + late checkout"
        if updates:
            Room.objects.filter(pk=room.pk).update(**updates)
    settle_constraints(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0125_money_account_constraints'),
    ]

    operations = [
        # ── CL ────────────────────────────────────────────────────────────
        migrations.RunPython(_cutover.step(_cutover.add_missing_hotels), migrations.RunPython.noop),
        migrations.RunPython(link_cl_to_masters, migrations.RunPython.noop),
        migrations.RunPython(check_and_normalise_cl, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='confirmationletter', name='cl_check_out_after_check_in'),
        migrations.RemoveField(model_name='confirmationletter', name='hotel_name'),
        migrations.RemoveField(model_name='confirmationletter', name='guest_name'),
        migrations.AlterField(
            model_name='confirmationletter', name='client',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cls', to='hw.client'),
        ),
        migrations.AlterField(
            model_name='confirmationletter', name='hotel',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='confirmation_letters', to='hw.hotel'),
        ),
        migrations.AlterField(
            model_name='confirmationletter', name='check_in',
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name='confirmationletter', name='check_out',
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name='confirmationletter', name='reservation_status',
            field=models.CharField(
                choices=[('TENTATIVE', 'Tentative'), ('DEFINITE', 'Definite'), ('CANCELLED', 'Cancelled')],
                default='DEFINITE', max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name='confirmationletter',
            constraint=models.CheckConstraint(
                condition=models.Q(('check_out__gt', models.F('check_in'))), name='cl_check_out_after_check_in',
            ),
        ),
        migrations.AddConstraint(
            model_name='confirmationletter',
            constraint=models.CheckConstraint(
                condition=models.Q(('reservation_status__in', STATUSES)), name='cl_status_valid',
            ),
        ),

        # ── Room ──────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='room', name='note',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(link_rooms_to_masters, migrations.RunPython.noop),
        migrations.RemoveField(model_name='room', name='room_type'),
        migrations.RemoveField(model_name='room', name='meals'),
        migrations.AlterField(
            model_name='room', name='room_type_ref',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='bookings', to='hw.roomtype'),
        ),
        migrations.AlterField(
            model_name='room', name='meal_plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='hw.mealplan'),
        ),
        migrations.AddConstraint(
            model_name='room',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='room_quantity_positive'),
        ),
        migrations.AddConstraint(
            model_name='room',
            constraint=models.CheckConstraint(condition=models.Q(('price__gte', 0)), name='room_price_non_negative'),
        ),
    ]
