"""Keputusan data produksi untuk cutover skema v2 (F11).

Dipanggil dari migrasi di titik di mana bentuk datanya cocok. Keputusan user
(2 Okt 2026, docs/superpowers/specs/2026-09-29-keputusan-data-produksi.md):

* aplikasi khusus Konoz: data ber-company Ijabah dihapus (sebelum 0100);
* pembayaran lama (hw_payment) dipindah menjadi PaymentRecord terkonfirmasi
  dengan nominal, kurs, dan tanggal aslinya (sebelum 0120 menghapus tabelnya);
* client/hotel CL yang tidak cocok otomatis diisi sesuai keputusan;
* denda bernilai 0 dihapus, jatuh tempo sebelum tanggal terbit dibetulkan;
* setoran lama menjadi transfer dari rekening IDR Surabaya, rupiahnya dihitung
  dengan kurs rata-rata pembayaran IDR (laba kurs periode lama = 0).

Semua fungsi aman dijalankan pada database tanpa data itu (dev, test): bila
tidak ada yang cocok, tidak ada yang berubah. Jurnalnya dibangun sesudah
migrasi oleh `manage.py cutover_journal`.

Modul ini diawali garis bawah supaya Django tidak menganggapnya migrasi.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from hw.models.client import client_name_key

LEGACY_NOTE = 'Data lama (pra-sistem)'
SYSTEM_USERNAME = 'system.cutover'
UNKNOWN_CLIENT = 'Belum diketahui'

# Client CL yang diputuskan manual (nomor CL → nama client).
CL_CLIENTS = {
    '684': UNKNOWN_CLIENT,
    '749': UNKNOWN_CLIENT,
    '748': 'Insan Utama',
    '5054': 'Gema',
    '5055': 'Gema',
    '4456': 'AIS Organizer',
    '2295': 'Ijabah Group',
}
NEW_CLIENTS = ['Insan Utama', 'Gema', 'AIS Organizer', UNKNOWN_CLIENT]
# Hotel yang belum ada di master (nama persis seperti di CL → kota).
NEW_HOTELS = {'Al Saha Hotel Madina': 'madinah', 'Dar Al Eiman Al Haram': 'makkah'}


def step(fn):
    """RunPython untuk satu langkah keputusan; pemeriksaan constraint PG
    dituntaskan sesudahnya supaya operasi skema berikutnya tidak tertahan."""
    def run(apps, schema_editor):
        from hw.db_pg import settle_constraints
        fn(apps, schema_editor)
        settle_constraints(schema_editor)
    run.__name__ = fn.__name__
    return run


def _fail(title, problems):
    raise RuntimeError(f'{title}: ' + '; '.join(problems[:40]) + (
        f' … (+{len(problems) - 40} lagi)' if len(problems) > 40 else ''
    ))


# ── sebelum 0100: hapus data Ijabah ───────────────────────────────────────

def purge_ijabah(apps, schema_editor):
    Invoice = apps.get_model('hw', 'Invoice')
    CL = apps.get_model('hw', 'ConfirmationLetter')
    Hotel = apps.get_model('hw', 'Hotel')
    Payment = apps.get_model('hw', 'Payment')

    invoices = Invoice.objects.filter(company='ijabah')
    mixed = CL.objects.filter(invoice__in=invoices).exclude(company='ijabah')
    if mixed.exists():
        _fail('CL Konoz menempel di invoice Ijabah', [c.confirmation_number for c in mixed])
    Payment.objects.filter(invoice__in=invoices).delete()
    CL.objects.filter(company='ijabah').delete()
    invoices.delete()
    Hotel.objects.filter(company='ijabah').delete()


# ── sebelum 0120: client CL dan pembayaran lama ───────────────────────────

def _merge_duplicate_clients(Client):
    """Client dengan name_key sama digabung (B: SAFAAR/Safaar). Yang dipertahankan:
    nama tidak huruf besar semua, lalu id terkecil."""
    groups = defaultdict(list)
    for c in Client.objects.order_by('pk'):
        groups[client_name_key(c.name)].append(c)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        keep = sorted(rows, key=lambda c: (c.name.isupper(), c.pk))[0]
        for drop in rows:
            if drop.pk == keep.pk:
                continue
            for rel in Client._meta.related_objects:
                if rel.many_to_many:
                    continue
                rel.related_model._base_manager.filter(**{rel.field.name: drop.pk}).update(**{rel.field.name: keep.pk})
            if not keep.brand and drop.brand and drop.brand != keep.name:
                Client.objects.filter(pk=keep.pk).update(brand=drop.brand)
            drop.delete()


def _clients_by_key(Client):
    out = defaultdict(set)
    for c in Client.objects.all():
        for text in {c.name, c.brand}:
            if text:
                out[client_name_key(text)].add(c.pk)
    return out


def link_cl_clients(apps, schema_editor):
    Client = apps.get_model('hw', 'Client')
    CL = apps.get_model('hw', 'ConfirmationLetter')

    _merge_duplicate_clients(Client)
    if CL.objects.filter(confirmation_number__in=list(CL_CLIENTS)).exists():
        for name in NEW_CLIENTS:
            if not Client.objects.filter(name__iexact=name).exists():
                Client.objects.create(name=name, note=LEGACY_NOTE if name == UNKNOWN_CLIENT else '')
    for number, name in CL_CLIENTS.items():
        client = Client.objects.filter(name__iexact=name).order_by('pk').first()
        if client:
            CL.objects.filter(confirmation_number=number, client__isnull=True).update(client_id=client.pk)
    keys = _clients_by_key(Client)
    for cl in CL.objects.filter(client__isnull=True).exclude(guest_name=''):
        found = keys.get(client_name_key(cl.guest_name), set())
        if len(found) == 1:
            CL.objects.filter(pk=cl.pk).update(client_id=next(iter(found)))


def _system_user(apps):
    User = apps.get_model('auth', 'User')
    user, _ = User.objects.get_or_create(
        username=SYSTEM_USERNAME, defaults={'first_name': 'System', 'last_name': 'Cutover', 'is_active': False},
    )
    return user


def _ensure_periods(apps, dates):
    Period = apps.get_model('hw', 'FinancialPeriod')
    for d in sorted({(x.year, x.month) for x in dates}):
        start, end = date(d[0], d[1], 1), date(d[0], d[1], monthrange(*d)[1])
        if not Period.objects.filter(date_from__lte=end, date_to__gte=start).exists():
            Period.objects.create(name=start.strftime('%B %Y'), date_from=start, date_to=end)


def _period_for(apps, day):
    return apps.get_model('hw', 'FinancialPeriod').objects.get(date_from__lte=day, date_to__gte=day)


def _bank_account(apps, branch, currency):
    Bank = apps.get_model('hw', 'BankAccount')
    acc = Bank.objects.filter(branch_id=branch, currency=currency, is_active=True).order_by('pk').first()
    if acc is None:
        acc = Bank.objects.create(
            branch_id=branch, currency=currency, name=f'Rekening Surabaya {currency}',
            bank_name='Rekening Surabaya', account_identifier='', note=LEGACY_NOTE,
            ledger_account_id=f'1000-KAS-{branch.upper()}',
        )
    return acc


def _sar(amount, currency, rate):
    amount, rate = Decimal(str(amount)), Decimal(str(rate or 0))
    if currency == 'SAR':
        value = amount
    elif currency == 'IDR':
        value = amount / rate if rate else Decimal(0)
    else:
        value = amount * rate
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def move_legacy_payments(apps, schema_editor):
    Payment = apps.get_model('hw', 'Payment')
    Record = apps.get_model('hw', 'PaymentRecord')
    Allocation = apps.get_model('hw', 'PaymentAllocation')
    Reservation = apps.get_model('hw', 'Reservation')
    CL = apps.get_model('hw', 'ConfirmationLetter')
    Cash = apps.get_model('hw', 'CashAccount')

    legacy = list(Payment.objects.select_related('invoice', 'cl').order_by('payment_date', 'pk'))
    if not legacy:
        return
    user = _system_user(apps)
    _ensure_periods(apps, [p.payment_date for p in legacy])

    problems = []
    for p in legacy:
        if Record.objects.filter(reference=f'legacy:{p.pk}').exists():
            continue
        invoice = p.invoice
        cl = p.cl or CL.objects.filter(invoice_id=invoice.pk, confirmation_number=(p.linked_number or '').strip()).first()
        client_id = (
            (cl.client_id if cl else None) or invoice.client_id
            or CL.objects.filter(invoice_id=invoice.pk, client__isnull=False).values_list('client_id', flat=True).first()
        )
        amount_sar = _sar(p.amount, p.currency, p.exchange_rate)
        if client_id is None:
            problems.append(f'pembayaran lama {p.pk} ({invoice.invoice_number}): client tidak diketahui')
            continue
        if amount_sar <= 0 or p.amount <= 0:
            problems.append(f'pembayaran lama {p.pk} ({invoice.invoice_number}): nominal {p.amount} {p.currency}')
            continue
        to_hq = p.currency == 'SAR' and (p.method or '').strip().lower() == 'direct'
        branch = 'pusat' if to_hq else 'sby'
        account = {}
        if p.currency == 'SAR':
            account['cash_account'] = Cash.objects.filter(branch_id=branch, currency='SAR').order_by('pk').first()
        else:
            account['bank_account'] = _bank_account(apps, 'sby', p.currency)
        record = Record.objects.create(
            payment_number=f'PAY-L{p.pk:04d}', payment_date=p.payment_date, amount=p.amount,
            currency=p.currency, exchange_rate=p.exchange_rate or 1, amount_sar=amount_sar,
            method=p.method or 'Transfer', reference=f'legacy:{p.pk}',
            note='\n'.join(x for x in (LEGACY_NOTE, p.note or '') if x), proof=p.proof,
            status='confirmed', confirmed_at=None, created_by_id=user.pk, confirmed_by_id=user.pk,
            client_id=client_id, invoice_id=invoice.pk, period=_period_for(apps, p.payment_date),
            received_in=branch, **account,
        )
        reservation = (
            Reservation.objects.filter(invoice_id=invoice.pk, confirmation_letter_id=cl.pk).first()
            or Reservation.objects.filter(invoice_id=invoice.pk, reservation_number=cl.confirmation_number).first()
        ) if cl else None
        if reservation is not None:
            Allocation.objects.create(payment_id=record.pk, reservation_id=reservation.pk, amount_sar=amount_sar)
    if problems:
        _fail('Pembayaran lama berikut perlu dibereskan', problems)


# ── sebelum 0126: hotel baru ──────────────────────────────────────────────

def add_missing_hotels(apps, schema_editor):
    Hotel = apps.get_model('hw', 'Hotel')
    CL = apps.get_model('hw', 'ConfirmationLetter')
    for name, city in NEW_HOTELS.items():
        if CL.objects.filter(hotel_name=name).exists() and not Hotel.objects.filter(name__iexact=name).exists():
            Hotel.objects.create(name=name, city=city, note=LEGACY_NOTE)


# ── sebelum 0127: denda bernilai 0 ────────────────────────────────────────

def drop_zero_penalties(apps, schema_editor):
    from django.db.models import Q
    Penalty = apps.get_model('hw', 'CancellationPenalty')
    Penalty.objects.filter(penalty_amount=0).filter(Q(amount_sar__isnull=True) | Q(amount_sar=0)).delete()


# ── sebelum 0128: jatuh tempo sebelum tanggal terbit ──────────────────────

def fix_due_dates(apps, schema_editor):
    from django.db.models import F
    Invoice = apps.get_model('hw', 'Invoice')
    Invoice.objects.filter(due_date__lt=F('issued_date')).update(due_date=F('issued_date'))


# ── sebelum 0133: setoran jalur lama ──────────────────────────────────────

def map_legacy_remittances(apps, schema_editor):
    Remittance = apps.get_model('hw', 'Remittance')
    Line = apps.get_model('hw', 'RemittanceLine')
    Record = apps.get_model('hw', 'PaymentRecord')
    Account = apps.get_model('hw', 'MoneyAccount')

    legacy = Remittance.objects.filter(from_account__isnull=True, amount_idr__isnull=True)
    if not legacy.exists():
        return
    legacy.exclude(pk__in=Line.objects.values('remittance_id')).delete()
    idr = Account.objects.filter(branch_id='sby', currency='IDR', is_active=True).order_by('kind', 'pk').first()
    payments = list(
        Record.objects.filter(receiving_account__currency='IDR', status='confirmed')
        .values_list('payment_date', 'amount', 'amount_sar')
    )
    problems = []
    for rem in legacy.order_by('date', 'pk'):
        sar = sum(int(x) for x in Line.objects.filter(remittance_id=rem.pk).values_list('amount_sar', flat=True))
        before = [(a, s) for d, a, s in payments if d <= rem.date] or [(a, s) for _, a, s in payments]
        total_idr, total_sar = sum(a for a, _ in before), sum(s for _, s in before)
        if idr is None or not total_sar:
            problems.append(f'{rem.remittance_number}: tidak ada rekening/pembayaran IDR untuk menghitung kurs')
            continue
        rate = (Decimal(total_idr) / Decimal(total_sar)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        Remittance.objects.filter(pk=rem.pk).update(
            from_account_id=idr.pk, exchange_rate=rate,
            amount_idr=int((Decimal(sar) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
            received_amount_sar=sar if rem.status == 'received' else rem.received_amount_sar,
            note='\n'.join(x for x in (LEGACY_NOTE, rem.note or '') if x),
        )
    if problems:
        _fail('Setoran lama berikut perlu dibereskan', problems)
