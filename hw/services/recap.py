from collections import defaultdict
from datetime import date


TEMPLATE_RECAP = (
    "*CHECK-IN RECAP — {date}*\n\n"
    "{guest_list}\n"
    "Total: {total_guests} tamu | {total_hotels} hotel"
)

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


def _get_template_body(template_type: str, fallback: str) -> str:
    from hw.models import MessageTemplate
    row = MessageTemplate.objects.filter(template_type=template_type).values_list('body', flat=True).first()
    return row if row else fallback


def _render(tmpl: str, **kwargs) -> str:
    """Simple key-by-key replacement so guest data with literal braces won't break."""
    for k, v in kwargs.items():
        tmpl = tmpl.replace('{' + k + '}', str(v))
    return tmpl


def resolve_reminder_targets(client, pending_cls: list) -> list:
    """Return [(channel, phone), ...] to send a grouped reminder to. Empty = skip."""
    targets = []
    if client.reminder_target in ('PIC', 'BOTH'):
        phone = client.wa or (pending_cls[0].guest_phone if pending_cls else '')
        if phone:
            targets.append(('PIC', phone))
    if client.reminder_target in ('GROUP', 'BOTH'):
        if client.wa_group:
            targets.append(('GROUP', client.wa_group))
    return targets


def resolve_guest_target(pending_cls: list) -> list:
    """Return [('GUEST', phone)] for a client-less group (same guest_name), or [] if no phone."""
    phone = next((cl.guest_phone for cl in pending_cls if cl.guest_phone), '')
    return [('GUEST', phone)] if phone else []


def group_guests(cls: list) -> dict:
    """Group client-less CLs by guest identity for reminder purposes.

    Names are compared case/whitespace-insensitively. Same guest name with a
    single agreed non-blank phone across the group are merged (a blank phone
    acts as a wildcard). Two distinct non-blank phones under the same name are
    kept apart, treated as different people; a blank phone in that ambiguous
    situation is kept standalone rather than guessed.
    """
    def name_key(cl):
        return (cl.guest_name or '').strip().casefold()

    phones_by_name = defaultdict(set)
    for cl in cls:
        if cl.guest_phone:
            phones_by_name[name_key(cl)].add(cl.guest_phone)

    groups = {}
    for cl in cls:
        phones = phones_by_name.get(name_key(cl), set())
        if len(phones) <= 1:
            key = (name_key(cl), next(iter(phones), ''))
        else:
            key = (name_key(cl), cl.guest_phone or cl.pk)
        groups.setdefault(key, []).append(cl)
    return groups


def build_grouped_reminder_message(cls: list, reminder_type: str, recipient_name: str) -> str:
    by_hotel = defaultdict(list)
    for cl in cls:
        by_hotel[cl.hotel_name].append(cl)

    blocks = []
    for hotel_name in sorted(by_hotel.keys()):
        blocks.append(f"*{hotel_name.upper()}*")
        for i, cl in enumerate(by_hotel[hotel_name], 1):
            rooms_str = ', '.join(f"{r.quantity} {r.room_type}" for r in cl.rooms.all()) or '-'
            blocks.append(f"{i}. #RSV : {cl.confirmation_number}")
            # 3 spasi = lebar prefix "1. " supaya Kamar lurus di bawah #RSV di WhatsApp
            blocks.append(f"   Kamar : {rooms_str}")
            blocks.append("")
    booking_blocks = '\n'.join(blocks).rstrip('\n')

    kwargs = dict(client_name=recipient_name, booking_blocks=booking_blocks)
    if reminder_type == 'H1_GUEST':
        ci = cls[0].check_in
        kwargs['check_in_date'] = ci.strftime('%d %b %Y') if ci else '-'
        return _render(_get_template_body('H1_GUEST', TEMPLATE_H1_CLIENT), **kwargs)
    return _render(_get_template_body('H0_GUEST', TEMPLATE_H0_CLIENT), **kwargs)


def build_recap_message(cls: list, recap_date=None) -> str:
    by_hotel = defaultdict(list)
    for cl in cls:
        by_hotel[cl.hotel_name].append(cl)

    # Build date string
    if recap_date is not None:
        tanggal = recap_date.strftime('%d %b %Y').upper()
    else:
        dates = sorted({cl.check_in for cl in cls if cl.check_in})
        if not dates:
            tanggal = date.today().strftime('%d %b %Y').upper()
        elif len(dates) == 1:
            tanggal = dates[0].strftime('%d %b %Y').upper()
        else:
            tanggal = f"{dates[0].strftime('%d %b')} - {dates[-1].strftime('%d %b %Y')}".upper()

    # Build per-hotel/guest list block
    lines = []
    incomplete_count = 0
    for hotel_name in sorted(by_hotel.keys()):
        lines.append(f"*{hotel_name.upper()}*")
        for i, cl in enumerate(by_hotel[hotel_name], 1):
            rooms_str = ', '.join(
                f"{r.quantity} {r.room_type}" for r in cl.rooms.all()
            ) or '-'
            ci        = cl.check_in.strftime('%d %b %Y') if cl.check_in else '-'
            eta       = cl.estimasi_tiba.strftime('%H:%M') if cl.estimasi_tiba is not None else '-'
            pic_name  = cl.pic_name or '-'
            pic_phone = cl.pic_phone or '-'
            if cl.estimasi_tiba is None:
                incomplete_count += 1
            prefix = '[!] ' if cl.estimasi_tiba is None else ''
            lines.append(f"{prefix}{i}. {'RSVN':<8} : {cl.confirmation_number}")
            lines.append(f"   {'Guest':<8} : {cl.guest_name}")
            lines.append(f"   {'Check-in':<8} : {ci}")
            lines.append(f"   {'Room(s)':<8} : {rooms_str}")
            lines.append(f"   {'ETA':<8} : {eta}")
            lines.append(f"   {'PIC':<8} : {pic_name}")
            lines.append(f"   {'PIC No.':<8} : {pic_phone}")
            lines.append("")

    guest_list = '\n'.join(lines).rstrip('\n')

    tmpl = _get_template_body('RECAP_OPS', TEMPLATE_RECAP)
    message = _render(
        tmpl,
        date=tanggal,
        guest_list=guest_list,
        total_guests=len(cls),
        total_hotels=len(by_hotel),
    )

    if incomplete_count:
        message += f" | {incomplete_count} belum ETA"

    return message
