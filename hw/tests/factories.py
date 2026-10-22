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
    Client,
    ConfirmationLetter,
    Hotel,
    Invoice,
    MealPlan,
    PaymentRecord,
    Reservation,
    Room,
    RoomType,
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


def make_account(branch='sby', currency='SAR'):
    """Rekening bank cabang `branch` dalam `currency` (dibuat bila belum ada)."""
    from hw.finance.accounts import cash_ledger_for
    from hw.finance.bank_ledger import default_account
    from hw.models import BankAccount
    existing = default_account(branch, currency)
    if existing:
        return existing
    return BankAccount.objects.create(
        branch_id=branch, name=f'Test {currency}', currency=currency, bank_name='Bank Uji',
        account_identifier=f'UJI-{branch}-{currency}',
        ledger_account_id=cash_ledger_for(branch, currency),
    )


def fund_cash(account, amount, day=date(2020, 1, 1)):
    """Isi buku kas `account` dengan `amount` (mata uang rekening) supaya test
    boleh mengeluarkan uang darinya: kas tidak bisa minus (bank_ledger.
    ensure_funds). Hanya baris buku kas -- buku besar tidak disentuh, jadi
    jurnal dan neraca yang diuji test tetap seperti semula."""
    from hw.finance.bank_ledger import record_bank_transaction
    return record_bank_transaction(
        account=account, direction='in', amount_sar=0, currency=account.currency, amount=amount,
        source_type='TestFunding', source_id=next(_numbers), transaction_date=day,
    )


def make_remittance(**kwargs):
    """Remittance dengan nilai bawaan yang sah: dari rekening IDR Surabaya ke
    rekening SAR Pusat. Nama lama diterima: `amount_idr` → amount_sent;
    `received_amount_sar` / status='received' → satu penerimaan (tanpa jurnal)."""
    from decimal import Decimal

    from hw.finance.bank_ledger import default_account
    from hw.models import Remittance
    from hw.models.settlement import RemittanceSettlement
    received = kwargs.pop('received_amount_sar', None)
    status = kwargs.pop('status', None)
    if 'amount_idr' in kwargs:
        kwargs['amount_sent'] = kwargs.pop('amount_idr')
    if kwargs.get('from_account') is None:
        kwargs['from_account'] = make_account('sby', 'IDR')
    if kwargs.get('to_account') is None:
        kwargs['to_account'] = default_account('pusat', 'SAR')
    sar_source = kwargs['from_account'].currency == 'SAR'
    if kwargs.get('exchange_rate') is None:
        kwargs['exchange_rate'] = Decimal(1) if sar_source else Decimal(4750)
    if kwargs.get('amount_sent') is None:
        kwargs['amount_sent'] = int(Decimal(kwargs['exchange_rate']) * 50000)   # 50,000 SAR expected
    kwargs.setdefault('remittance_number', f'RMT-F{next(_numbers)}')
    rem = Remittance.objects.create(**kwargs)
    if received or status == Remittance.STATUS_RECEIVED:
        RemittanceSettlement.objects.create(
            remittance=rem, received_amount_sar=received or rem.expected_sar, received_date=rem.date,
        )
    return rem


def make_remittance_line(remittance=None, invoice=None, linked_number=None, amount_sar=0, settlement=None, **legacy):
    """Alokasi penerimaan ke reservasi `linked_number` (baris hotel invoice-nya).
    Tanpa `settlement`, dipakai penerimaan pertama remittance itu (dibuat bila belum ada)."""
    from hw.models import InvoiceLine, RemittanceLine
    from hw.models.settlement import RemittanceSettlement
    legacy.pop('invoice_id', None)
    if legacy:
        raise TypeError(f'make_remittance_line: argumen tidak dikenal {sorted(legacy)}')
    if settlement is None:
        settlement = remittance.settlements.order_by('pk').first() or RemittanceSettlement.objects.create(
            remittance=remittance, received_amount_sar=max(int(amount_sar), 1), received_date=remittance.date,
        )
    lines = InvoiceLine.objects.filter(kind='hotel', confirmation_letter__confirmation_number=linked_number)
    if invoice is not None:
        lines = lines.filter(invoice=invoice)
    line = lines.order_by('voided_at', 'pk').first()
    if line is None:
        raise ValueError(f'make_remittance_line: tidak ada baris hotel untuk {linked_number}')
    return RemittanceLine.objects.create(settlement=settlement, invoice_line=line, amount_sar=amount_sar)


def make_payment(**kwargs):
    """PaymentRecord langsung (tanpa jurnal), untuk test yang menyiapkan
    keadaan tertentu. Rekening penerima wajib sejak skema v2: bila tidak
    disebut, dipakai rekening bawaan cabang `received_in` (sby) dalam
    `currency` (SAR). `currency`, `received_in`, dan `period` bukan kolom lagi."""
    from hw.finance.bank_ledger import default_account
    currency = kwargs.pop('currency', 'SAR')
    branch = kwargs.pop('received_in', 'sby')
    kwargs.pop('period', None)
    if kwargs.get('receiving_account') is None:
        kwargs['receiving_account'] = default_account(branch, currency) or make_account(branch, currency)
    return PaymentRecord.objects.create(**kwargs)


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


def ensure_current_period():
    """Periode yang memuat hari ini. Koreksi seperti realokasi diposting pada
    tanggal hari ini, jadi test yang hanya membuat periode lampau butuh ini."""
    from hw.models.period import FinancialPeriod
    today = date.today()
    if FinancialPeriod.objects.filter(date_from__lte=today, date_to__gte=today).exists():
        return
    start = today.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    FinancialPeriod.objects.create(name=f'{start:%Y-%m} (test current)', date_from=start, date_to=end)


def _checker():
    """Penyetuju terpisah untuk dokumen uang keluar (pencatat != penyetuju)."""
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(username='factory-checker')
    return user


def refund_now(client, **kwargs):
    """Refund deposit yang dicatat lalu langsung disetujui user lain."""
    from hw.finance.deposit import confirm_refund, request_refund
    return confirm_refund(request_refund(client, **kwargs), confirmed_by=_checker())


def transfer_now(from_client, to_client, **kwargs):
    """Transfer deposit yang dicatat lalu langsung disetujui user lain."""
    from hw.finance.deposit import confirm_transfer, request_transfer
    return confirm_transfer(request_transfer(from_client, to_client, **kwargs), confirmed_by=_checker())


def ops_and_money_role():
    """Slug of a test role holding both the operational side (CL, invoices,
    services) and money. Since 2026-10-09 these belong to two people (Manager
    and Finance); tests that drive an invoice and its payments with one user,
    to check the ledger rather than who may do what, use this role."""
    from hw.models.role import RoleDefinition
    every = ['view', 'create', 'edit', 'delete', 'export', 'approve']
    modules = ('cl', 'invoice', 'hotels', 'clients', 'calendar', 'penalty',
               'payments', 'bank', 'expenses', 'remittance', 'statements', 'journal', 'periods')
    RoleDefinition.objects.get_or_create(
        slug='ops-money', defaults={'label': 'Ops & Money (test)', 'permissions': {m: every for m in modules}},
    )
    return 'ops-money'


def fund_account(account, amount, sar, day, user=None):
    """Isi rekening `account` dengan `amount` (mata uang rekening) senilai
    `sar` SAR, di buku besar DAN buku kas — yang dibutuhkan beban, yang dinilai
    dengan kurs tercatat rekening (posting.carrying_sar)."""
    fund_ledger(account, amount, sar, day, user)
    return fund_cash(account, amount, day)


def fund_ledger(account, amount, sar, day, user=None):
    """Isi buku besar rekening `account` dengan `amount` (mata uang rekening)
    senilai `sar` SAR, tanpa baris buku kas. Untuk test yang mengirim
    remittance: dengan `amount`/`sar` = kurs kirimnya, nilai tercatat yang
    dikirim sama dengan SAR kirimnya, jadi tidak terbentuk laba/rugi kurs."""
    from django.contrib.auth.models import User

    from hw.finance import accounts as coa
    from hw.finance import posting
    user = user or User.objects.get_or_create(username='factory-funder')[0]
    return posting.post_adjustment(
        lines=[{'account': account.ledger_account_id, 'debit': sar, 'branch': account.branch_id,
                **posting.native(account, amount)},
               {'account': coa.OPENING_EQUITY, 'credit': sar, 'branch': account.branch_id}],
        description=f'dana awal {account}', entry_date=day, created_by=user,
    )


def fund_ledger_for(remittance, amount_sar=None):
    """fund_ledger untuk tepat satu remittance: rupiahnya senilai SAR kirimnya
    (`amount_sar`, bawaan expected_sar), pada tanggal remittance."""
    return fund_ledger(remittance.from_account, remittance.amount_sent,
                       amount_sar or remittance.expected_sar, remittance.date)


def paid_expense(branch, account, amount, day, user, *, category='UTIL', vendor=None, description=''):
    """Beban rupiah yang sudah diajukan, disetujui dan dibayar dari `account`.
    Mengembalikan (expense, payment)."""
    from hw.finance import expense_service
    from hw.models import ExpenseCategory
    exp = expense_service.submit_expense(
        branch=branch, expense_date=day, created_by=user, vendor=vendor, description=description,
        lines=[{'category': ExpenseCategory.objects.get(code=category), 'amount': amount}],
    )
    expense_service.approve_expense(exp, approved_by=user)
    payment = expense_service.pay_expense(exp, account=account, payment_date=day, paid_by=user)
    exp.refresh_from_db()
    return exp, payment
