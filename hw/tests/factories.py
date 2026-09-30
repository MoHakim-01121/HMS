"""Pabrik data test untuk reservasi (CL) dan kamarnya.

Sejak skema v2, CL wajib punya client, hotel, dan tanggal; kamar wajib menunjuk
tipe kamar di katalog hotelnya. Pabrik ini mengisi bagian yang tidak relevan
bagi sebuah test, dan menerima nama sebagai teks (`guest_name`, `hotel_name`,
`room_type`, `meals`) lalu mencarikan atau membuatkan baris masternya.
"""
import itertools
from datetime import date, timedelta

from hw.models import Client, ConfirmationLetter, Hotel, MealPlan, Room, RoomType
from hw.models.client import client_name_key

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
    if kwargs.get('client') is None and 'client_id' not in kwargs:
        kwargs['client'] = make_client(guest_name) if guest_name else make_client()
    if kwargs.get('hotel') is None and 'hotel_id' not in kwargs:
        kwargs['hotel'] = make_hotel(hotel_name) if hotel_name else make_hotel()
    kwargs.setdefault('confirmation_number', f'CL-FACTORY-{next(_numbers)}')
    today = date.today()
    check_in = kwargs.setdefault('check_in', today)
    kwargs.setdefault('check_out', (check_in or today) + timedelta(days=1))
    return ConfirmationLetter.objects.create(**kwargs)


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
