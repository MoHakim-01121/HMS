from django.db import migrations

# Reminder H-1/H-0 kini selalu dikirim sebagai pesan gabungan per client/tamu,
# jadi template lama berbasis satu booking ({guest_name}/{hotel_name}/{rooms})
# tidak bisa dirender lagi. Body lama tanpa {booking_blocks} direset ke default
# format gabungan; operator bisa menyesuaikan ulang lewat Pengaturan WA.

TEMPLATE_H0_CLIENT = (
    "Assalamualaikum Bapak/Ibu {client_name},\n\n"
    "Berikut detail check-in hari ini:\n\n"
    "{booking_blocks}\n"
    "Mohon segera informasikan estimasi tiba & PIC untuk tiap hotel.\n\n"
    "Terima kasih."
)

TEMPLATE_H1_CLIENT = (
    "Assalamualaikum Bapak/Ibu {client_name},\n\n"
    "Kami mengingatkan bahwa check-in berikut dijadwalkan besok, *{check_in_date}*:\n\n"
    "{booking_blocks}\n"
    "Mohon segera informasikan estimasi tiba & PIC untuk tiap hotel.\n\n"
    "Terima kasih."
)


def reset_stale_reminder_templates(apps, schema_editor):
    MessageTemplate = apps.get_model('hw', 'MessageTemplate')
    defaults = {'H0_GUEST': TEMPLATE_H0_CLIENT, 'H1_GUEST': TEMPLATE_H1_CLIENT}
    for row in MessageTemplate.objects.filter(template_type__in=defaults):
        if '{booking_blocks}' not in row.body:
            row.body = defaults[row.template_type]
            row.save(update_fields=['body'])
    try:
        from django.core.cache import cache
        cache.delete('message_templates')
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0032_client_wa_group_reminder_target'),
    ]

    operations = [
        migrations.RunPython(reset_stale_reminder_templates, migrations.RunPython.noop),
    ]
