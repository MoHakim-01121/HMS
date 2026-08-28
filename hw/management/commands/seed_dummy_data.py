"""Seed data dummy musiman (jemaah umrah) mulai check-in 28 Agustus 2026.

Membuat data lengkap untuk pengetesan Calendar / CL / Invoice / klien:
- Client (+ brand/city/pic minimal)
- ConfirmationLetter + Room
- Invoice hotel (per agency per gelombang) + Reservation tiap CL + Charge ledger
- Invoice visa ekstra + ServiceItem
- Pembayaran: Payment (legacy), CashMovement, Allocation + status invoice

Idempotent: semua nomor dokumen deterministik; baris yang sudah ada di-skip.
`--reset`: hapus data dummy hasil seed ini (ditandai prefix ``[SEED]`` /
nomor ``DUM-``), lalu bikin ulang.

Usage:
    python manage.py seed_dummy_data
    python manage.py seed_dummy_data --reset
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from hw.models import (
    Client,
    ConfirmationLetter,
    Room,
    Invoice,
    Reservation,
    ServiceItem,
    Payment,
    Charge,
    Allocation,
    CashMovement,
    ChargeReason,
    AllocationReason,
    Company,
    InvoiceType,
)
from hw.models.ledger import CashAccount
from hw.utils import round_half_up

DUM_PREFIX = 'DUM-'
SEED_TAG = '[SEED] '

# ── Klien agensi satu musim enggan (semua direferensikan di data lama) ──────
AGENCIES = [
    {'name': 'PT GEMA IJABAH SEJAHTERA', 'brand': 'Ijabah Group',     'city': 'Surabaya', 'pic': 'Pak Joko',  'wa': '628123456701'},
    {'name': 'Global Tour',               'brand': '',                 'city': 'Surabaya', 'pic': 'Bu Sari',   'wa': '628123456702'},
    {'name': 'Darmawisata',               'brand': '',                 'city': 'Surabaya', 'pic': 'Pak Bowo',  'wa': '628123456703'},
    {'name': 'Asosiasi Berpahala',        'brand': 'Pokoknya Umrah',   'city': 'Jakarta',  'pic': 'Ust. Rahman', 'wa': '628123456704'},
    {'name': 'Cahaya Multazam',           'brand': 'Cahaya Multazam',  'city': 'Bandung',  'pic': 'Pak Haidar', 'wa': '628123456705'},
]

# ── Hotel + harga kamar (SAR/night, konsisten dgn data CL lama) ─────────────
HOTELS = {
    'Sawaed Al Kheir':   {'Double': Decimal('390'), 'Triple': Decimal('435'), 'Quad': Decimal('475'), 'Quint': Decimal('540')},
    'Rawaby Zamzam':     {'Double': Decimal('400'), 'Triple': Decimal('450'), 'Quad': Decimal('480')},
    'Olayan Ajyad':      {'Double': Decimal('420'), 'Triple': Decimal('470'), 'Quad': Decimal('520'), 'Quint': Decimal('590')},
    'Snood Ajyad':       {'Double': Decimal('430'), 'Triple': Decimal('470'), 'Quad': Decimal('500')},
    'Nada Al Diyafa':    {'Double': Decimal('440'), 'Triple': Decimal('485'), 'Quad': Decimal('520')},
    'Jawharat Al Rasyid': {'Double': Decimal('380'), 'Triple': Decimal('440'), 'Quad': Decimal('490')},
    'Maysan Al Mashaer': {'Double': Decimal('470'), 'Triple': Decimal('520'), 'Quad': Decimal('560'), 'Quint': Decimal('640')},
    'Grand Plaza Badr':  {'Double': Decimal('520'), 'Triple': Decimal('580'), 'Quad': Decimal('620')},
    'Azka Al Safa':      {'Double': Decimal('380'), 'Triple': Decimal('430'), 'Quad': Decimal('460')},
}

# ── Nama jamaah individual untuk CL perorangan ──────────────────────────────
JAMAAH_NAMES = [
    'Ahmad Fauzi', 'Siti Nurhaliza', 'Budi Santoso', 'Dewi Lestari', 'Muhammad Ridwan',
    'Fatimah Zahra', 'Abdul Aziz', 'Nur Hidayati', 'Rahmat Hidayat', 'Siti Aminah',
    'Hasan Basri', 'Kartika Sari', 'Yusuf Maulana', 'Aisyah Putri', 'Andi Saputra',
    'Rina Wahyuni', 'Fajar Ramadhan', 'Laila Mahmudah', 'Zainal Arifin', 'Maya Anggraini',
    'Indra Gunawan', 'Wulan Dari', 'Rudi Hartono', 'Salamah Hasyim',
]

# Gelombang mingguan: check-in Jumat mulai 28-08-2026, total 14 gelombang
START_DATE = date(2026, 8, 28)
NUM_WAVES = 14

VISA_PRICE = Decimal('1250')  # SAR per visa

MEALS = 'FB'


def _split_integer(total, weights):
    """Bagi `total` menjadi int yang jumlahnya `total`, proporsional ke weights."""
    if total <= 0:
        return [0] * len(weights)
    wsum = sum(weights)
    if not wsum:
        out = [0] * len(weights)
        out[0] = total
        return out
    parts = []
    acc = 0
    for w in weights[:-1]:
        p = total * w // wsum
        parts.append(p)
        acc += p
    parts.append(total - acc)
    return parts


class Command(BaseCommand):
    help = 'Seed data dummy musiman (CL/Invoice/Payment) mulai 28 Agustus 2026.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Hapus dulu data dummy dari seed ini lalu bikin ulang.',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            if options['reset']:
                self._reset()
            self.seed()

    # ── Reset ──────────────────────────────────────────────────────────────
    def _reset(self):
        self.stdout.write('Reset data dummy [SEED]...')

        # Alokasi/payment/charge yang kita buat punya jejak SEED_TAG.
        alloc_ids = list(Allocation.objects.filter(note__startswith=SEED_TAG).values_list('id', flat=True))
        cash_ids = list(CashMovement.objects.filter(note__startswith=SEED_TAG).values_list('id', flat=True))
        pay_ids = list(Payment.objects.filter(note__startswith=SEED_TAG).values_list('id', flat=True))
        charge_ids = list(Charge.objects.filter(description__startswith=SEED_TAG).values_list('id', flat=True))

        invoice_ids = set()
        invoice_ids.update(Charge.objects.filter(id__in=charge_ids).values_list('invoice_id', flat=True))
        invoice_ids.update(CashMovement.objects.filter(id__in=cash_ids).values_list('invoice_id', flat=True))
        invoice_ids.update(Payment.objects.filter(id__in=pay_ids).values_list('invoice_id', flat=True))
        invoice_ids.update(Allocation.objects.filter(id__in=alloc_ids).values_list('invoice_id', flat=True))
        invoice_ids = {i for i in invoice_ids if i}

        # Penalty juga bisa nyangkut ke invoice kita (mis. CL dibatalkan) —
        # serahkan lewat CL delete di bawah; invoice cuma SET_NULL.
        cm = CashMovement.objects.filter(id__in=cash_ids)
        self.stdout.write(f"  delete: {cm.count()} cash_movement")
        cm.delete()
        for qs, label in [
            (Allocation.objects.filter(id__in=alloc_ids), 'allocation'),
            (Payment.objects.filter(id__in=pay_ids), 'payment'),
            (Charge.objects.filter(id__in=charge_ids), 'charge'),
        ]:
            self.stdout.write(f"  delete: {qs.count()} {label}")
            qs.delete()

        # Invoice beserta Reservation/ServiceItem/PaymentRecord lewat CASCADE.
        inv_qs = Invoice.objects.filter(pk__in=invoice_ids)
        self.stdout.write(f"  delete: {inv_qs.count()} invoice")
        inv_qs.delete()

        # CL dummy: prefix DUM- + tahun (aman dari DUM- manual lama).
        cl_qs = ConfirmationLetter.objects.filter(confirmation_number__startswith=f'{DUM_PREFIX}2026')
        self.stdout.write(f"  delete: {cl_qs.count()} confirmation_letter")
        cl_qs.delete()

        self.stdout.write(self.style.SUCCESS('Reset selesai.\n'))

    # ── Client ─────────────────────────────────────────────────────────────
    def _get_clients(self):
        clients = {}
        for spec in AGENCIES:
            obj, created = Client.objects.get_or_create(
                name=spec['name'],
                defaults={
                    'brand': spec['brand'],
                    'city': spec['city'],
                    'pic': spec['pic'],
                    'wa': spec['wa'],
                },
            )
            clients[spec['name']] = obj
            if created:
                self.stdout.write(f"  client+ {spec['name']}")
        return clients

    # ── Inti seed ──────────────────────────────────────────────────────────
    def seed(self):
        self.stdout.write('Seed data dummy mulai 28-08-2026 s/d akhir November:')
        clients = self._get_clients()
        counter = {'cl': 0, 'room': 0, 'inv': 0, 'res': 0, 'svc': 0,
                   'charge': 0, 'alloc': 0, 'cash': 0, 'pay': 0, 'svc_item': 0}
        month_seq = {}  # (invoice_type, YYYYMM) -> int

        for wi in range(NUM_WAVES):
            check_in = START_DATE + timedelta(weeks=wi)
            rng = random.Random(f'{check_in.isoformat()}')
            # 3 agensi aktif per gelombang, rotasi deterministik.
            active = [(wi + k) % len(AGENCIES) for k in range(3)]

            for j, ai in enumerate(active):
                spec = AGENCIES[ai]
                client = clients[spec['name']]
                display = spec['brand'] or spec['name']
                clrng = random.Random(f'{check_in.isoformat()}-{j}')

                hotel_name = clrng.choice(list(HOTELS))
                prices = HOTELS[hotel_name]
                nights = clrng.choice([7, 8])
                check_out = check_in + timedelta(days=nights)
                status = clrng.choices(['DEFINITE', 'TENTATIVE'], weights=[17, 3])[0]

                # CL grup (manifest agency).
                group_conf = f'{DUM_PREFIX}{check_in:%Y%m%d}-{j + 1:02d}'
                cl, created = self._create_cl(
                    conf=group_conf, guest=display, client=client,
                    hotel=hotel_name, check_in=check_in, check_out=check_out,
                    status=status, rooms=self._group_rooms(clrng, prices),
                    rng=clrng, is_group=True,
                )
                counter['cl'] += created and 1 or 0
                counter['room'] += created and cl.rooms.count() or 0
                cl_objs = [cl]

                # CL perorangan (jamaah) sesekali, hotel beda.
                if (wi + j) % 2 == 0:
                    ind_conf = f'{DUM_PREFIX}{check_in:%Y%m%d}-{(j + 1) * 10:02d}'
                    ind_rng = random.Random(f'{check_in.isoformat()}-ind-{j}')
                    ind_hotel = ind_rng.choice([h for h in HOTELS if h != hotel_name])
                    ind_cl, ind_created = self._create_cl(
                        conf=ind_conf, guest=ind_rng.choice(JAMAAH_NAMES), client=client,
                        hotel=ind_hotel, check_in=check_in, check_out=check_out,
                        status='DEFINITE', rooms=self._individual_rooms(ind_rng, HOTELS[ind_hotel]),
                        rng=ind_rng, is_group=False,
                    )
                    counter['cl'] += ind_created and 1 or 0
                    counter['room'] += ind_created and ind_cl.rooms.count() or 0
                    cl_objs.append(ind_cl)

                # 1 invoice hotel utk semua CL agency ini (mirip invoice_from_cls).
                inv = self._invoice_for_cls(cl_objs, month_seq, counter)
                if inv:
                    self._seed_payments(inv, SEED_TAG, month_seq, counter)

            # Cancelled CL sesekali — tanpa invoice, tampil merah di kalender.
            if wi % 5 == 2:
                spec = AGENCIES[(wi + 1) % len(AGENCIES)]
                client = clients[spec['name']]
                crng = random.Random(f'{check_in.isoformat()}-cancel')
                hotel_name = crng.choice(list(HOTELS))
                canc_cl, canc_created = self._create_cl(
                    conf=f'{DUM_PREFIX}{check_in:%Y%m%d}-97', guest=crng.choice(JAMAAH_NAMES),
                    client=None, hotel=hotel_name, check_in=check_in,
                    check_out=check_in + timedelta(days=7), status='CANCELLED',
                    rooms=[('Double', 1, HOTELS[hotel_name]['Double'])],
                    rng=crng, is_group=False,
                )
                counter['cl'] += canc_created and 1 or 0
                counter['room'] += canc_created and 1 or 0

            # Invoice visa ekstra tiap 3 gelombang utk satu agensi.
            if (wi % 3 == 0) and check_in >= date(2026, 9, 1):
                spec = AGENCIES[(wi + 2) % len(AGENCIES)]
                client = clients[spec['name']]
                vrng = random.Random(f'{check_in.isoformat()}-visa')
                qty = vrng.randint(5, 15)
                self._visa_invoice(client, check_in, qty, month_seq, counter)

        self.stdout.write(self.style.SUCCESS(
            '\nSelesai. Counters:\n'
            + '\n'.join(f'  {k}: {v}' for k, v in counter.items())
        ))

    # ── Helpers ────────────────────────────────────────────────────────────
    def _group_rooms(self, rng, prices):
        """Komposisi kamar utk satu grup: kuad/triple dominan."""
        plan = []
        q = rng.randint(6, 18)
        t = rng.randint(0, 4)
        d = rng.randint(0, 2)
        for rt, qty in (('Quad', q), ('Triple', t), ('Double', d)):
            if qty and rt in prices:
                plan.append((rt, qty, prices[rt]))
        if not plan:
            plan = [('Quad', 6, prices['Quad'])]
        return plan

    def _individual_rooms(self, rng, prices):
        rt = rng.choice([rt for rt in ('Double', 'Triple') if rt in prices] or ['Double'])
        return [(rt, rng.randint(1, 3), prices.get(rt, Decimal('400')))]

    def _create_cl(self, conf, guest, client, hotel, check_in, check_out,
                   status, rooms, rng, is_group):
        existing = ConfirmationLetter.objects.filter(
            company=Company.KONOZ, confirmation_number=conf,
        ).first()
        if existing:
            return existing, False

        cl = ConfirmationLetter.objects.create(
            company=Company.KONOZ,
            client=client,
            hotel_name=hotel,
            guest_name=guest,
            guest_phone=f"62812{int(10000000) + rng.randint(0, 9999999)}" if not is_group else '',
            check_in=check_in,
            check_out=check_out,
            confirmation_number=conf,
            reservation_status=status,
            estimasi_tiba=None if rng.random() < 0.3 else rng.choice(
                ['14:30', '16:00', '17:45', '19:20', '21:00', '22:15']
            ),
            pic_name=client.pic if (is_group and client) else '',
            pic_phone=client.wa if (is_group and client) else '',
            note=SEED_TAG + (f'Manifest {conf}' if is_group else f'Jamaah {guest}'),
        )
        for (rt, qty, price) in rooms:
            Room.objects.create(
                cl=cl, room_type=rt, meals=MEALS, quantity=qty, price=price,
            )
        return cl, True

    def _invoice_for_cls(self, cl_objs, month_seq, counter):
        cls = [c for c in cl_objs if c.reservation_status != 'CANCELLED']
        if not cls:
            return None
        first = cls[0]
        issued = first.check_in - timedelta(days=28)
        key = (InvoiceType.HOTEL, f'{issued:%Y%m}')
        month_seq[key] = month_seq.get(key, 0) + 1
        number = f'INV-{issued:%Y%m}-{month_seq[key]:03d}'

        inv = Invoice.objects.filter(
            company=Company.KONOZ, invoice_type=InvoiceType.HOTEL, invoice_number=number,
        ).first()
        if not inv:
            inv = Invoice.objects.create(
                company=Company.KONOZ,
                invoice_type=InvoiceType.HOTEL,
                invoice_number=number,
                client=first.client,
                issued_date=issued,
                due_date=issued + timedelta(days=14),
                currency='SAR',
            )
            counter['inv'] += 1

        for cl in cls:
            total = round_half_up(cl.total_price or 0)
            res = Reservation.objects.filter(
                invoice=inv, reservation_number=cl.confirmation_number,
            ).first()
            if not res:
                res = Reservation.objects.create(
                    invoice=inv,
                    reservation_number=cl.confirmation_number,
                    hotel=cl.hotel_name or '-',
                    check_in=cl.check_in,
                    check_out=cl.check_out,
                    total_sar=total,
                )
                counter['res'] += 1
                if total:
                    if not Charge.objects.filter(
                        invoice=inv, reservation=res, description__startswith=SEED_TAG,
                    ).exists():
                        Charge.objects.create(
                            company=Company.KONOZ, client=cl.client,
                            invoice=inv, date=issued, amount_sar=total,
                            reservation=res, reason=ChargeReason.INITIAL,
                            description=SEED_TAG + f'Invoice {number} dari CL {cl.confirmation_number}',
                        )
                        counter['charge'] += 1
            if not cl.invoice_id:
                cl.invoice = inv
                cl.save(update_fields=['invoice'])
        inv.status = 'draft'
        inv.save(update_fields=['status'])
        return inv

    def _visa_invoice(self, client, check_in, qty, month_seq, counter):
        issued = check_in - timedelta(days=35)
        key = (InvoiceType.VISA, f'{issued:%Y%m}')
        month_seq[key] = month_seq.get(key, 0) + 1
        number = f'SVC-{issued:%Y%m}-{month_seq[key]:03d}'

        inv = Invoice.objects.filter(
            company=Company.KONOZ, invoice_type=InvoiceType.VISA, invoice_number=number,
        ).first()
        if not inv:
            inv = Invoice.objects.create(
                company=Company.KONOZ,
                invoice_type=InvoiceType.VISA,
                invoice_number=number,
                client=client,
                customer_name=client.brand or client.name,
                issued_date=issued,
                due_date=issued + timedelta(days=30),
                currency='SAR',
            )
            counter['inv'] += 1

        si = ServiceItem.objects.filter(invoice=inv, service_number=1).first()
        if not si:
            si = ServiceItem.objects.create(
                invoice=inv, service_number=1, name='Visa Umrah',
                qty=qty, price=int(VISA_PRICE),
            )
            counter['svc_item'] += 1
            if not Charge.objects.filter(
                invoice=inv, service_item=si, description__startswith=SEED_TAG,
            ).exists():
                Charge.objects.create(
                    company=Company.KONOZ, client=client,
                    invoice=inv, date=issued, amount_sar=si.total,
                    service_item=si, reason=ChargeReason.INITIAL,
                    description=SEED_TAG + f'Invoice {number} (visa x{qty})',
                )
                counter['charge'] += 1
        inv.status = 'draft'
        inv.save(update_fields=['status'])
        return inv

    def _seed_payments(self, inv, tag, month_seq, counter):
        """Pembayaran per invoice: 35% lunas, 45% DP, 20% belum bayar."""
        if Allocation.objects.filter(invoice=inv, note__startswith=tag).exists():
            return
        total = inv.total_sar
        if total <= 0:
            return

        prng = random.Random(f'pay-{inv.invoice_number}')
        roll = prng.random()
        if roll < 0.35:
            paid, status = total, 'paid'
        elif roll < 0.80:
            paid = max(1, int(total * prng.uniform(0.25, 0.50)))
            if paid >= total:
                paid, status = total, 'paid'
            else:
                status = 'partial'
        else:
            paid, status = 0, 'sent'

        inv.status = status
        inv.save(update_fields=['status'])

        if not paid:
            return

        payment_date = min(
            date.today(),
            inv.issued_date + timedelta(days=prng.randint(2, 9)),
        )
        method = prng.choices(['Transfer Bank', 'Direct'], weights=[3, 1])[0]
        received = CashAccount.PUSAT if method == 'Direct' else CashAccount.SBY

        use_idr = prng.random() < 0.15
        if use_idr:
            rate = Decimal(prng.choice(['4425', '4380', '4401', '4350']))
            amount, currency = paid * int(rate), 'IDR'
        else:
            rate = Decimal('1')
            amount, currency = paid, 'SAR'

        # CashMovement — sumber Invoice.total_paid_sar / kas.
        cash = CashMovement.objects.filter(
            invoice=inv, from_account=CashAccount.CLIENT, to_account=received,
            amount=amount, currency=currency, note__startswith=tag,
        ).first()
        if not cash:
            CashMovement.objects.create(
                company=Company.KONOZ,
                client=inv.client,
                date=payment_date,
                from_account=CashAccount.CLIENT,
                to_account=received,
                amount=amount,
                currency=currency,
                exchange_rate=rate,
                method=method,
                invoice=inv,
                note=tag + f'DP/pelunasan {inv.invoice_number} ({status})',
            )
            counter['cash'] += 1

        # Allocation + Payment per reservation (dimensi penyelesaian piutang).
        ress = list(inv.reservations.all())
        siss = list(inv.service_items.all())
        targets = [(r, r.total_sar) for r in ress if r.total_sar] or [(r, 1) for r in ress]
        # Untuk visa: target service item.
        if not targets and siss:
            targets = [(s, s.total) for s in siss]
        if not targets:
            return
        weights = [w for _, w in targets]
        shares = _split_integer(paid, weights)

        for (target, _w), share in zip(targets, shares):
            if share <= 0:
                continue
            if not Allocation.objects.filter(
                invoice=inv, note__startswith=tag,
                **({'reservation': target} if isinstance(target, Reservation)
                   else {'service_item': target}),
            ).exists():
                kwargs = ({'reservation': target} if isinstance(target, Reservation)
                          else {'service_item': target})
                Allocation.objects.create(
                    company=Company.KONOZ,
                    client=inv.client,
                    date=payment_date,
                    amount_sar=share,
                    invoice=inv,
                    reason=AllocationReason.INITIAL,
                    note=tag + f'Alokasi {inv.invoice_number}',
                    **kwargs,
                )
                counter['alloc'] += 1
            # Payment legacy per CL/SI — idempotent via (invoice, linked_number).
            linked = target.reservation_number if isinstance(target, Reservation) else inv.invoice_number
            cl = (
                ConfirmationLetter.objects.filter(confirmation_number=linked).first()
                if isinstance(target, Reservation) else None
            )
            if not Payment.objects.filter(
                invoice=inv, linked_number=linked, amount=(
                    share * int(rate) if use_idr else share
                ), currency=currency,
            ).exists():
                Payment.objects.create(
                    invoice=inv,
                    cl=cl,
                    linked_number=linked,
                    payment_date=payment_date,
                    method=method,
                    amount=(share * int(rate) if use_idr else share),
                    currency=currency,
                    exchange_rate=rate,
                    note=tag + f'Pembayaran {inv.invoice_number}',
                )
                counter['pay'] += 1