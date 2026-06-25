from collections import defaultdict
from datetime import date


TEMPLATE_H0 = (
    "Assalamualaikum Bapak/Ibu {guest_name},\n\n"
    "Hari ini adalah hari check-in Anda di *{hotel_name}*.\n\n"
    "Detail reservasi:\n"
    "- No. CL   : {confirmation_number}\n"
    "- Kamar     : {rooms}\n\n"
    "Mohon segera informasikan estimasi tiba dan nama PIC\n"
    "agar kami siapkan penerimaan Anda.\n\n"
    "Terima kasih."
)

TEMPLATE_H1 = (
    "Assalamualaikum Bapak/Ibu {guest_name},\n\n"
    "Kami mengingatkan bahwa check-in Anda di *{hotel_name}* dijadwalkan besok, "
    "*{check_in_date}*.\n\n"
    "Detail reservasi:\n"
    "- No. CL   : {confirmation_number}\n"
    "- Kamar     : {rooms}\n\n"
    "Mohon balas pesan ini dengan:\n"
    "- Estimasi tiba di hotel\n"
    "- Nama & nomor PIC yang bisa kami hubungi\n\n"
    "Terima kasih."
)

TEMPLATE_RECAP = (
    "*CHECK-IN RECAP — {date}*\n\n"
    "{guest_list}\n"
    "Total: {total_guests} tamu | {total_hotels} hotel"
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


def build_reminder_message(cl, reminder_type: str) -> str:
    rooms_str = ', '.join(f"{r.quantity} {r.room_type}" for r in cl.rooms.all()) or '-'
    if reminder_type == 'H1_GUEST':
        tmpl = _get_template_body('H1_GUEST', TEMPLATE_H1)
        return _render(
            tmpl,
            guest_name=cl.guest_name,
            hotel_name=cl.hotel_name,
            check_in_date=cl.check_in.strftime('%d %b %Y') if cl.check_in else '-',
            confirmation_number=cl.confirmation_number,
            rooms=rooms_str,
        )
    tmpl = _get_template_body('H0_GUEST', TEMPLATE_H0)
    return _render(
        tmpl,
        guest_name=cl.guest_name,
        hotel_name=cl.hotel_name,
        confirmation_number=cl.confirmation_number,
        rooms=rooms_str,
    )


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
