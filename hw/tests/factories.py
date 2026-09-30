"""Pabrik data test untuk reservasi (CL), kamarnya, invoice, dan baris invoice.

Sejak skema v2, CL wajib punya client, hotel, dan tanggal; kamar wajib menunjuk
tipe kamar di katalog hotelnya; invoice wajib punya client; dan baris hotel di
invoice tidak menyimpan nilai (dibaca dari CL-nya). Pabrik ini mengisi bagian
yang tidak relevan bagi sebuah test, dan menerima nama sebagai teks
(`guest_name`, `hotel_name`, `room_type`, `meals`, `customer_name`) lalu
mencarikan atau membuatkan baris masternya.
"""
import itertools
from datetime import date, timedelta
from decimal import Decimal

from hw.models import (
    Client, ConfirmationLetter, Hotel, Invoice, MealPlan, Reservation, Room, RoomType, ServiceItem,
)
from hw.models.client import client_name_key
from hw.signals import invoice_sync_suspended

_numbers = itertools.count(1)
_CAPACITY = {'single': 1, 'double': 2, 'twin': 2, 'triple': 3, 'quad': 4, 'quint': 5}


def make_client(name='PT Uji Factory', **kwargs):
    existing = Client.objects.filter(name_key=client_name_key(name)).first()
    return existing or Client.objects.create(name=name, **kwargs)


def make_hotel(name='Hotel Uji Factory', city='makkah', **kwargs):
    existing = Hotel.objects.filter(name=name, city=city).first()
    return existing or Hotel.objects.create(name=name, city=city, **kwargs)


def make_cl(**kwargs):
    """ConfirmationLetter dengan nilai bawaan yang sah.

    `guest_name` → client bernama itu (kecuali `client` diberikan);
    `hotel_name` → hotel bernama itu (kecuali `hotel` diberikan).
    """
    guest_name = kwargs.pop('guest_name', None)
    hotel_name = kwargs.pop('hotel_name', None)
    invoice = kwargs.pop('invoice', None)
    if kwargs.get('client') is None and 'client_id' not in kwargs:
        if invoice is not None:
            kwargs['client'] = invoice.client
        else:
            kwargs['client'] = make_client(guest_name) if guest_name else make_client()
    if kwargs.get('hotel') is None and 'hotel_id' not in kwargs:
        kwargs['hotel'] = make_hotel(hotel_name) if hotel_name else make_hotel()
    kwargs.setdefault('confirmation_number', f'CL-FACTORY-{next(_numbers)}')
    today = date.today()
    check_in = kwargs.setdefault('check_in', today)
    kwargs.setdefault('check_out', (check_in or today) + timedelta(days=1))
    cl = ConfirmationLetter.objects.create(**kwargs)
    if invoice is not None:
        invoice.add_hotel_line(cl)
    return cl


def make_invoice(**kwargs):
    """Invoice dengan nilai bawaan yang sah. `customer_name` → client bernama
    itu (kecuali `client` diberikan). Cabang penerbit mengikuti cabang pemilik
    client bila tidak disebut."""
    name = kwargs.pop('customer_name', None)
    if kwargs.get('client') is None and 'client_id' not in kwargs:
        kwargs['client'] = make_client(name) if name else make_client()
    kwargs.setdefault('invoice_type', 'hotel')
    kwargs.setdefault('invoice_number', f'INV-FACTORY-{next(_numbers)}')
    return Invoice.objects.create(**kwargs)


def _priced_room(cl, total):
    """Satu kamar pada `cl` yang membuat nilai CL = `total` (tanpa memicu
    penyesuaian invoice: test memposting charge-nya sendiri)."""
    from hw.finance.reservation_rules import reservation_total_for_cl
    nights = cl.num_nights or 1
    # Harga per malam dua desimal; nilai CL dibulatkan ke riyal utuh, jadi
    # total yang tidak habis dibagi jumlah malam tetap tepat setelah dibulatkan.
    price = (Decimal(total) / nights).quantize(Decimal('0.01'))
    room_type, _ = RoomType.objects.get_or_create(hotel_id=cl.hotel_id, name='Quad', defaults={'capacity': 4})
    with invoice_sync_suspended():
        cl.rooms.all().delete()
        Room.objects.create(cl=cl, room_type_ref=room_type, quantity=1, price=price)
    cl = ConfirmationLetter.objects.get(pk=cl.pk)
    if not cl.is_cancelled and reservation_total_for_cl(cl) != total:
        raise ValueError(f'total {total} tidak bisa dicapai dengan {nights} malam')


def make_priced_cl(client, confirmation_number, total_sar, **kwargs):
    """Reservasi (CL) milik `client` yang nilainya `total_sar`, belum ditagih."""
    kwargs.setdefault('check_in', date(2026, 1, 10))
    kwargs.setdefault('check_out', kwargs['check_in'] + timedelta(days=1))
    cl = make_cl(client=client, confirmation_number=confirmation_number, **kwargs)
    _priced_room(cl, total_sar)
    return cl


def make_hotel_line(invoice, reservation_number=None, total_sar=None, hotel=None,
                    check_in=None, check_out=None, confirmation_letter=None, **legacy):
    """Baris hotel pada `invoice`, beserta reservasi (CL) yang ditagihnya.

    Menerima nama-nama lama baris Reservation: `reservation_number` jadi nomor
    CL (CL bernomor itu dipakai bila sudah ada), `total_sar` jadi harga satu
    kamar semalam, `hotel` jadi hotel CL. Mengembalikan barisnya."""
    legacy.pop('client', None); legacy.pop('client_id', None)
    if legacy:
        raise TypeError(f'make_hotel_line: argumen tidak dikenal {sorted(legacy)}')
    cl = confirmation_letter
    if cl is None and reservation_number is not None:
        cl = ConfirmationLetter.objects.filter(confirmation_number=reservation_number).first()
        live = cl.invoice_line if cl is not None else None
        if live is not None and live.invoice_id != invoice.pk:
            cl = None   # nomor itu sudah ditagih di invoice lain: buat reservasi baru
            reservation_number = f'{reservation_number}-{next(_numbers)}'
    if cl is None:
        start = check_in or date(2026, 1, 10)
        cl = make_cl(
            client=invoice.client, hotel_name=hotel or None,
            confirmation_number=reservation_number or f'R-FACTORY-{next(_numbers)}',
            check_in=start, check_out=check_out or start + timedelta(days=1),
        )
    if total_sar:
        _priced_room(cl, total_sar)
    line = invoice.add_hotel_line(cl)
    return Reservation.objects.get(pk=line.pk)


def set_line_total(line, total_sar):
    """Ubah nilai baris hotel lewat sumbernya (kamar CL), tanpa memposting
    ulang charge: pengganti `reservation.total_sar = x; reservation.save()`."""
    _priced_room(line.confirmation_letter, total_sar)
    return Reservation.objects.get(pk=line.pk)


def make_service_line(invoice, name='Service', qty=1, price=0, **legacy):
    legacy.pop('service_number', None)
    if legacy:
        raise TypeError(f'make_service_line: argumen tidak dikenal {sorted(legacy)}')
    line = invoice.add_service_line(name, qty, price)
    return ServiceItem.objects.get(pk=line.pk)


def cl_form_payload(cl, rooms=None, **overrides):
    """POST body yang sah untuk /cl/<pk>/edit/ (atau /cl/new/) berdasarkan `cl`.

    `rooms`: daftar dict {quantity, price, room_type_id?, meals?}; tanpa
    room_type_id dipakai tipe kamar dari kamar pertama CL (atau dibuatkan).
    Bawaan: kamar-kamar CL apa adanya. `overrides` menimpa field form.
    """
    import json
    existing = list(cl.rooms.all())
    if rooms is None:
        rooms = [{'quantity': r.quantity, 'price': float(r.price), 'room_type_id': r.room_type_ref_id,
                  'meals': r.meals} for r in existing]
    fallback = existing[0].room_type_ref if existing else None
    rows = []
    for r in rooms:
        r = dict(r)
        if not r.get('room_type_id'):
            if fallback is None:
                fallback, _ = RoomType.objects.get_or_create(
                    hotel_id=cl.hotel_id, name=r.get('room_type') or 'Quad', defaults={'capacity': 4},
                )
            r['room_type_id'] = fallback.pk
        r.setdefault('room_type', 'Room')
        rows.append(r)
    payload = {
        'client_id': str(cl.client_id), 'guest_name': cl.guest_name,
        'hotel_id': str(cl.hotel_id), 'hotel_name': cl.hotel_name,
        'guest_phone': cl.guest_phone,
        'check_in': cl.check_in.isoformat(), 'check_out': cl.check_out.isoformat(),
        'confirmation_number': cl.confirmation_number,
        'reservation_status': cl.reservation_status, 'note': cl.note,
        'rooms': json.dumps(rows),
    }
    payload.update(overrides)
    return payload


def make_room(**kwargs):
    """Room pada `cl`. `room_type` teks → tipe kamar hotel CL itu (dibuat bila
    belum ada); `meals` teks → meal plan berkode itu, selain itu jadi catatan."""
    cl = kwargs['cl']
    text = kwargs.pop('room_type', None)
    if kwargs.get('room_type_ref') is None and 'room_type_ref_id' not in kwargs:
        name = text or 'Quad'
        capacity = _CAPACITY.get(name.split()[0].lower(), 2)
        kwargs['room_type_ref'], _ = RoomType.objects.get_or_create(
            hotel_id=cl.hotel_id, name=name, defaults={'capacity': capacity},
        )
    meals = kwargs.pop('meals', None)
    if meals and kwargs.get('meal_plan') is None and 'meal_plan_id' not in kwargs:
        if MealPlan.objects.filter(code=meals).exists():
            kwargs['meal_plan_id'] = meals
        else:
            kwargs.setdefault('note', meals)
    return Room.objects.create(**kwargs)
