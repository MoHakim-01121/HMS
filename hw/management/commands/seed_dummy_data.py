"""Wipe the DEV database's business data and seed realistic demo data.

Everything is created through the same services the app uses (invoice charge
posting, payment allocate/confirm, cash book, currency exchange, remittance +
HQ receipt with allocation, expenses), so journals, the cash book, statements
and the fund-flow report all tie out exactly like real data.

Kept: users/roles, branches, chart of accounts, seeded cash accounts, expense
categories, meal plans, the hotel catalog (hotels + room types), WhatsApp
templates and landing content. Everything else is deleted.

The business it mimics: travel agents book Makkah/Madinah hotels through the
Surabaya branch; clients pay in IDR (some USD, some SAR direct to HQ); USD is
exchanged to IDR; the branch sends IDR lump sums to HQ at the bank rate and
earns the spread; HQ receives SAR only.

Refuses to run unless DEBUG is on and the database is SQLite.

Usage:
    python manage.py seed_dummy_data --reset
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

KEEP_MODELS = {
    'Branch', 'UserProfile', 'RoleDefinition', 'LedgerAccount', 'CashAccount', 'ExpenseCategory',
    'MealPlan', 'Hotel', 'RoomType', 'WATarget', 'MessageTemplate', 'TeamMember', 'Pricelist',
}

CLIENTS = [
    # name, brand, city, province, pic, wa, lat, lng
    ('PT Gema Ijabah Sejahtera', 'Ijabah Group', 'Surabaya', 'Jawa Timur', 'H. Abdul Rozaq', '6281234567801', -7.2575, 112.7521),
    ('PT Cahaya Multazam Wisata', 'Cahaya Multazam', 'Bandung', 'Jawa Barat', 'Pak Haidar', '6281234567802', -6.9175, 107.6191),
    ('PT Darmawisata Indonesia', 'Darmawisata', 'Surabaya', 'Jawa Timur', 'Bu Laila', '6281234567803', -7.2891, 112.7340),
    ('PT Global Tour Travel', 'Global Tour', 'Sidoarjo', 'Jawa Timur', 'Pak Hendra', '6281234567804', -7.4478, 112.7183),
    ('PT Asosiasi Berpahala Umrah', 'Pokoknya Umrah', 'Malang', 'Jawa Timur', 'Ust. Fauzan', '6281234567805', -7.9666, 112.6326),
    ('PT Nurul Haramain Travel', 'Nurul Haramain', 'Semarang', 'Jawa Tengah', 'H. Mahfud', '6281234567806', -6.9667, 110.4167),
    ('PT Al Madinah Mubarak', 'Al Madinah', 'Yogyakarta', 'DI Yogyakarta', 'Bu Aisyah', '6281234567807', -7.7956, 110.3695),
    ('PT Barokah Safar Mulia', 'Barokah Safar', 'Gresik', 'Jawa Timur', 'Pak Syamsul', '6281234567808', -7.1566, 112.6555),
    ('PT Rahmatan Lil Alamin Tour', 'RLA Tour', 'Jember', 'Jawa Timur', 'H. Qomaruddin', '6281234567809', -8.1724, 113.7000),
    ('PT Zamzam Amanah Wisata', 'Zamzam Amanah', 'Kediri', 'Jawa Timur', 'Bu Rahma', '6281234567810', -7.8480, 112.0178),
]

# SAR per room per night by guest count, per hotel star rating.
PRICE = {
    5: {2: 650, 3: 720, 4: 800, 5: 880},
    3: {1: 240, 2: 320, 3: 380, 4: 440, 5: 500},
}
MADINAH_PRICE = {2: 260, 3: 300, 4: 340, 5: 380}


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Required: wipe business data, then seed.')

    def handle(self, *args, **options):
        if not settings.DEBUG or connection.vendor != 'sqlite':
            raise CommandError('Dev only: needs DEBUG=True and the SQLite database.')
        if not options['reset']:
            raise CommandError('This deletes all business data. Run again with --reset.')
        self.user = User.objects.filter(is_superuser=True).order_by('pk').first()
        if self.user is None:
            raise CommandError('No superuser to record the seed as.')
        self.rng = random.Random(20260927)
        self.today = date.today()
        self._wipe()
        with transaction.atomic():
            self._seed()
        self._report()

    # ── wipe ────────────────────────────────────────────────────────────
    def _wipe(self):
        tables = []
        for model in apps.get_app_config('hw').get_models(include_auto_created=True):
            if model._meta.auto_created:
                # M2M through table: keep only between two kept models.
                related = {f.related_model.__name__ for f in model._meta.fields if f.related_model}
                if related <= KEEP_MODELS:
                    continue
            elif model.__name__ in KEEP_MODELS:
                continue
            tables.append(model._meta.db_table)
        with connection.cursor() as cur:
            cur.execute('PRAGMA foreign_keys = OFF')
            for table in tables:
                cur.execute(f'DELETE FROM "{table}"')
                cur.execute('DELETE FROM sqlite_sequence WHERE name = %s', [table])
            cur.execute('PRAGMA foreign_keys = ON')
        from hw.models import CashAccount
        CashAccount.objects.update(opening_balance=0, opening_date=None)
        self.stdout.write(f'Wiped {len(tables)} tables.')

    # ── seed ────────────────────────────────────────────────────────────
    def _seed(self):
        from hw.models import BankAccount, CashAccount, Client, LedgerAccount
        from hw.models.period import FinancialPeriod
        from hw.finance.bank_ledger import sync_opening_balance

        self.start = self.today - timedelta(days=90)
        # Monthly open periods covering the whole timeline (bookings reach
        # back up to ~140 days, before the cash-flow window starts).
        month = (self.today - timedelta(days=150)).replace(day=1)
        end = self.today + timedelta(days=150)
        while month <= end:
            nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            FinancialPeriod.objects.create(name=month.strftime('%B %Y'), date_from=month, date_to=nxt - timedelta(days=1))
            month = nxt

        la_sby = LedgerAccount.objects.get(code='1000-KAS-SBY')
        la_pusat = LedgerAccount.objects.get(code='1000-KAS-PUSAT')
        self.idr = BankAccount.objects.create(
            branch_id='sby', name='1400017736512', currency='IDR', bank_name='Bank Mandiri',
            account_identifier='1400017736512', account_name='PT Konoz United Indonesia',
            ledger_account=la_sby, show_on_invoice=True,
            opening_balance=35_000_000, opening_date=self.start,
        )
        sync_opening_balance(self.idr)
        self.usd = BankAccount.objects.create(
            branch_id='sby', name='1400017736520', currency='USD', bank_name='Bank Mandiri',
            account_identifier='1400017736520', account_name='PT Konoz United Indonesia',
            ledger_account=la_sby, show_on_invoice=True,
        )
        BankAccount.objects.create(
            branch_id='pusat', name='SA4180000123608010456789', currency='SAR', bank_name='Al Rajhi Bank',
            account_identifier='SA4180000123608010456789', account_name='Konoz United Est.',
            ledger_account=la_pusat, show_on_invoice=True,
        )
        self.cash_pusat = CashAccount.objects.get(branch_id='pusat')

        self.clients = []
        for name, brand, city, prov, pic, wa, lat, lng in CLIENTS:
            self.clients.append(Client.objects.create(
                name=name, brand=brand, city=city, province=prov, pic=pic, wa=wa,
                wa_group=f'Grup {brand}', reminder_target='BOTH',
                address=f'Jl. Raya {city} No. {self.rng.randint(3, 180)}', lat=lat, lng=lng,
                email=f"admin@{brand.lower().replace(' ', '')}.co.id",
            ))

        self.cl_no = 7800
        self.inv_seq = {}
        trips = self._trips()
        for trip in trips:
            self._book(trip)
        self._cash_flow(trips)
        self._services()
        self._expenses()
        self._controls()

    def _trips(self):
        """Umrah trips: each client ~4 departures spread over the timeline."""
        trips = []
        for client in self.clients:
            for _ in range(self.rng.randint(3, 5)):
                check_in = self.today + timedelta(days=self.rng.randint(-80, 110))
                trips.append({'client': client, 'check_in': check_in,
                              'booked': check_in - timedelta(days=self.rng.randint(25, 60)),
                              'pax_groups': self.rng.randint(2, 7)})
        trips.sort(key=lambda t: t['booked'])
        return trips

    def _next_cl(self):
        self.cl_no += self.rng.randint(3, 41)
        return str(self.cl_no)

    def _rooms(self, hotel, n_rooms, nights):
        """Rooms for a group CL; price per room per night by capacity/stars."""
        from hw.models import MealPlan
        types = list(hotel.room_types.filter(is_active=True))
        meal = hotel.meal_plans.order_by('code').first() or MealPlan.objects.order_by('code').first()
        madinah = (hotel.city or '').lower() == 'madinah'
        table = MADINAH_PRICE if madinah else PRICE.get(hotel.stars if hotel.stars in PRICE else 3)
        rooms = []
        for cap in self.rng.sample([2, 3, 4, 4, 4, 5], k=min(n_rooms, 3)):
            match = [t for t in types if t.capacity == cap] or types
            rt = self.rng.choice(match) if match else None
            capacity = rt.capacity if rt else cap
            base = table.get(capacity, table[max(table)])
            view = 1.1 if rt and 'view' in rt.name.lower() and 'non' not in rt.name.lower() else 1.0
            rooms.append({
                'room_type': rt.name if rt else {2: 'Double', 3: 'Triple', 4: 'Quad', 5: 'Quint'}.get(cap, 'Quad'),
                'room_type_ref': rt, 'meal_plan': meal, 'meals': meal.code if meal else '',
                'quantity': self.rng.randint(1, 4), 'price': Decimal(round(base * view / 5) * 5),
            })
        return rooms

    def _book(self, trip):
        """A trip = Makkah CL (+ Madinah CL for most). Invoiced when booked."""
        from hw.models import ConfirmationLetter, Hotel, Room
        client = trip['client']
        makkah = list(Hotel.objects.filter(city__iexact='makkah', is_active=True))
        madinah = list(Hotel.objects.filter(city__iexact='madinah', is_active=True))
        legs = [(self.rng.choice(makkah), self.rng.randint(4, 8))]
        if madinah and self.rng.random() < 0.7:
            legs.append((self.rng.choice(madinah), self.rng.randint(3, 4)))
        future_far = trip['check_in'] > self.today + timedelta(days=60)
        status = 'TENTATIVE' if future_far and self.rng.random() < 0.5 else 'DEFINITE'
        if self.rng.random() < 0.06:
            status = 'CANCELLED'
        cls = []
        day = trip['check_in']
        for hotel, nights in legs:
            cl = ConfirmationLetter.objects.create(
                client=client, hotel=hotel, hotel_name=hotel.name, guest_name=client.brand or client.name,
                guest_phone=client.wa, check_in=day, check_out=day + timedelta(days=nights),
                confirmation_number=self._next_cl(), reservation_status=status,
                pic_name=client.pic, pic_phone=client.wa,
            )
            for r in self._rooms(hotel, trip['pax_groups'], nights):
                Room.objects.create(cl=cl, **r)
            ConfirmationLetter.objects.filter(pk=cl.pk).update(created_at=_dt(trip['booked']))
            cls.append(cl)
            day += timedelta(days=nights)
        trip['cls'] = cls
        trip['invoice'] = self._invoice(trip) if status == 'DEFINITE' and trip['booked'] <= self.today else None

    def _invoice_number(self, prefix, issued):
        key = (prefix, issued.strftime('%Y%m'))
        self.inv_seq[key] = self.inv_seq.get(key, 0) + 1
        return f'{prefix}-{issued:%Y%m}-{self.inv_seq[key]:03d}'

    def _invoice(self, trip):
        from hw.finance import posting
        from hw.finance.reservation_rules import reservation_total_for_cl
        from hw.models import Invoice, Reservation
        issued = trip['booked']
        client = trip['client']
        inv = Invoice.objects.create(
            invoice_type='hotel', invoice_number=self._invoice_number('INV', issued), client=client,
            customer_name=client.name, issued_date=issued, due_date=trip['check_in'] - timedelta(days=10),
            currency='SAR', branch_id='sby', created_by=self.user,
        )
        for cl in trip['cls']:
            Reservation.objects.create(
                invoice=inv, confirmation_letter=cl, client=client, reservation_number=cl.confirmation_number,
                hotel=cl.hotel_name, check_in=cl.check_in, check_out=cl.check_out,
                total_sar=reservation_total_for_cl(cl), owner_branch_id='sby',
            )
            cl.invoice = inv
            cl.save(update_fields=['invoice'])
        posting.post_invoice_charge(inv, created_by=self.user, entry_date=issued)
        Invoice.objects.filter(pk=inv.pk).update(created_at=_dt(issued))
        return inv

    # ── money ───────────────────────────────────────────────────────────
    def _pay(self, inv, targets, day, share, settle=False):
        """One client payment covering `share` of each target's total.
        `settle` pays the exact outstanding amount (the final payment), in
        IDR or SAR only — a USD amount rounds to whole dollars and would
        leave a few riyal open."""
        from hw.finance import posting
        from hw.finance.receipt_service import ensure_receipt
        from hw.finance_helpers import confirm_payment, create_payment_record
        from hw.models.payment import PaymentRecord
        if settle:
            inv.refresh_from_db()
            sar = int(inv.remaining_sar)          # exactly what is still open
        else:
            sar = sum(int(t.total_sar if hasattr(t, 'total_sar') else t.total) * share for t in targets)
            sar = int(sar // 100 * 100)
        if sar <= 0:
            return None
        roll = self.rng.random()
        if settle and 0.12 <= roll < 0.24:
            roll = 0.5
        if roll < 0.12:       # SAR paid straight to HQ
            kw = dict(amount=sar, currency='SAR', exchange_rate=1, received_in='pusat',
                      cash_account=self.cash_pusat, method='Direct')
        elif roll < 0.24:     # USD into the branch USD account
            rate = Decimal('3.70')
            usd = int(Decimal(sar) / rate)
            kw = dict(amount=usd, currency='USD', exchange_rate=rate, bank_account=self.usd, method='Transfer')
        else:                 # IDR into the branch IDR account (the usual case)
            rate = self.rng.choice([4870, 4880, 4890, 4900, 4910, 4920])
            kw = dict(amount=sar * rate, currency='IDR', exchange_rate=rate, bank_account=self.idr, method='Transfer')
        p = create_payment_record(
            inv, inv.client, day, created_by=self.user,
            reference=f'TRF{day:%y%m%d}{self.rng.randint(1000, 9999)}', **kw,
        )
        total = int(p.amount_sar)
        weights = [int(t.total_sar if hasattr(t, 'total_sar') else t.total) for t in targets]
        allocs, left = [], total
        for i, (t, w) in enumerate(zip(targets, weights)):
            amt = left if i == len(targets) - 1 else int(total * w / sum(weights))
            allocs.append((t, amt))
            left -= amt
        posting.allocate_payment(p, [a for a in allocs if a[1] > 0], created_by=self.user)
        confirm_payment(p, confirmed_by=self.user)
        p.status = p.derive_status()
        p.save(update_fields=['status'])
        ensure_receipt(p, created_by=self.user)
        PaymentRecord.objects.filter(pk=p.pk).update(created_at=_dt(day))
        return p

    def _cash_flow(self, trips):
        """Payments, USD exchanges, weekly transfers to HQ and HQ receipts,
        replayed day by day so each step sees the state before it."""
        events = []
        for trip in trips:
            inv = trip['invoice']
            if inv is None:
                continue
            reservations = list(inv.reservations.all())
            dp_day = trip['booked'] + timedelta(days=self.rng.randint(1, 6))
            due = inv.due_date
            late = self.rng.random() < 0.15
            events.append((dp_day, 'pay', (inv, reservations, Decimal(self.rng.choice(['0.3', '0.4', '0.5'])))))
            if not late:
                events.append((due - timedelta(days=self.rng.randint(0, 5)), 'pay_rest', (inv, reservations)))
        day = self.start
        while day <= self.today:
            if day.weekday() == 0:
                events.append((day, 'exchange', None))
            if day.weekday() == 3:
                events.append((day, 'remit', None))
            day += timedelta(days=1)
        events = [e for e in events if e[0] <= self.today]
        events.sort(key=lambda e: (e[0], ['pay', 'pay_rest', 'exchange', 'remit'].index(e[1])))
        for day, kind, arg in events:
            if kind == 'pay':
                self._pay(arg[0], arg[1], day, arg[2])
            elif kind == 'pay_rest':
                inv, reservations = arg
                inv.refresh_from_db()
                if inv.remaining_sar > 0:
                    self._pay(inv, reservations, day, None, settle=True)
            elif kind == 'exchange':
                self._exchange(day)
            elif kind == 'remit':
                self._remit(day)
        from hw.models import Invoice
        for inv in Invoice.objects.all():
            inv.sync_status()

    def _exchange(self, day):
        from hw.finance import exchange_service, fund_flow
        flow = fund_flow.fund_flow(branch='sby', date_to=day)
        usd = next(l for l in flow['lines'] if l['key'] == 'closing')['values'].get('USD', 0)
        if usd >= 500:
            rate = self.rng.choice([18150, 18180, 18200, 18220, 18250])
            exchange_service.record_exchange(
                from_account=self.usd, amount_out=usd, to_account=self.idr, amount_in=usd * rate,
                exchange_date=day, created_by=self.user, reference=f'FX{day:%y%m%d}',
            )

    def _remit(self, day):
        """Weekly IDR lump sum to HQ at the bank rate, received a few days
        later with the money allocated to the reservations it belongs to."""
        from hw.finance import fund_flow, posting, remittance_allocation, settlement_service
        from hw.finance.bank_ledger import record_bank_transaction
        from hw.models.remittance import Remittance
        held = fund_flow.fx_profit(branch='sby', date_to=day)['client_money_held'].get('IDR', {})
        sar = int(held.get('sar', 0) * 0.9) // 1000 * 1000
        if sar < 20_000:
            return
        rate = self.rng.choice([4735, 4745, 4750, 4760, 4770, 4780])
        amount_idr = sar * rate
        rem = Remittance.objects.create(
            remittance_number=Remittance.generate_number(), date=day, amount_idr=amount_idr,
            exchange_rate=Decimal(rate), from_bank_account=self.idr,
            receipt_reference=f'MDR{day:%y%m%d}{self.rng.randint(100, 999)}',
        )
        record_bank_transaction(
            account=self.idr, direction='out', amount_sar=rem.expected_sar, currency='IDR', amount=amount_idr,
            source_type='Remittance', source_id=rem.pk, transaction_date=day, reference=rem.receipt_reference,
        )
        posting.resync_remittance(rem, created_by=self.user, send_segments=[])
        received_day = day + timedelta(days=self.rng.randint(2, 4))
        if received_day > self.today:
            return  # still in transit
        received = rem.expected_sar - self.rng.randint(15, 45)  # correspondent-bank fee
        rows = remittance_allocation.candidates(rem)
        allocations = [
            {'linked_number': r['linked_number'], 'invoice_id': r['invoice_id'], 'amount_sar': amt}
            for r in rows
            for number, amt in remittance_allocation.suggest(rows, rem.expected_sar).items()
            if number == r['linked_number']
        ]
        settlement_service.add_settlement(
            rem, received_amount_sar=received, received_date=received_day, created_by=self.user,
            reference=f'ARB{received_day:%y%m%d}', allocations=allocations,
        )
        settlement_service.close_remittance_diff(rem, created_by=self.user, entry_date=received_day)

    def _services(self):
        """A few visa invoices (services), paid in IDR."""
        from hw.finance import posting
        from hw.models import Invoice, ServiceItem
        for client in self.rng.sample(self.clients, 4):
            issued = self.today - timedelta(days=self.rng.randint(10, 70))
            pax = self.rng.randint(12, 45)
            inv = Invoice.objects.create(
                invoice_type='services', invoice_number=self._invoice_number('SVC', issued), client=client,
                customer_name=client.name, issued_date=issued, due_date=issued + timedelta(days=14),
                currency='SAR', branch_id='sby', created_by=self.user,
            )
            item = ServiceItem.objects.create(invoice=inv, service_number=1, name='Visa Umrah', qty=pax, price=550)
            posting.post_invoice_charge(inv, created_by=self.user, entry_date=issued)
            Invoice.objects.filter(pk=inv.pk).update(created_at=_dt(issued))
            self._pay(inv, [item], issued + timedelta(days=self.rng.randint(1, 5)), None, settle=True)
            inv.sync_status()

    def _expenses(self):
        """Surabaya office running costs, paid in IDR from the branch account."""
        from hw.finance import expense_service
        from hw.models import Branch, ExpenseCategory
        sby = Branch.objects.get(code='sby')
        cats = {c.code: c for c in ExpenseCategory.objects.all()}
        month = self.start.replace(day=1)
        monthly = [('UTIL', 'PLN & PDAM', 1_450_000), ('TELECOM', 'Indihome & pulsa', 925_000),
                   ('TRANSPORT', 'Bensin & tol antar dokumen', 780_000), ('SUPPLIES', 'ATK & tinta printer', 410_000),
                   ('MEALS', 'Konsumsi rapat agen', 650_000)]
        first = True
        while month <= self.today:
            items = list(monthly)
            if first:
                items.append(('RENT', 'Sewa kantor 6 bulan', 30_000_000))
                first = False
            for code, desc, idr in items:
                day = month + timedelta(days=self.rng.randint(2, 20))
                if day > self.today or day < self.start:
                    continue
                rate = 4750
                exp = expense_service.record_expense(
                    branch=sby, expense_date=day, created_by=self.user, vendor=desc.split(' ')[0],
                    description=desc, currency='IDR', exchange_rate=rate,
                    lines=[{'category': cats[code], 'amount': idr, 'description': desc}],
                )
                expense_service.add_expense_payment(
                    exp, amount=idr, currency='IDR', exchange_rate=rate, payment_date=day,
                    bank_account=self.idr, created_by=self.user, reference=f'OUT{day:%y%m%d}',
                )
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    # ── controls: credit note, void invoice, bank statement ───────────
    def _controls(self):
        from hw.finance import credit_note_service as cns
        from hw.models import Invoice

        # A room cancelled after part-payment: credit that share of one stay.
        partial = [i for i in Invoice.objects.filter(invoice_type='hotel', status=Invoice.STATUS_PARTIAL)
                   if i.reservations.count() >= 2]
        if partial:
            inv = self.rng.choice(partial)
            res = max(inv.reservations.all(), key=lambda r: r.total_sar)
            amount = int(res.total_sar * 0.2) // 100 * 100
            cns.issue_credit_note(
                inv, lines=[{'kind': 'reservation', 'id': res.pk, 'amount_sar': amount}],
                reason='1 kamar Quad batal (jamaah tidak berangkat) — tagihan dikurangi',
                issued_date=self.today - timedelta(days=self.rng.randint(1, 6)), created_by=self.user,
            )

        # A group invoiced when booked, then cancelled before any payment:
        # the invoice is voided (number kept) and its CLs released.
        from hw.models import ConfirmationLetter
        trip = {'client': self.rng.choice(self.clients), 'check_in': self.today + timedelta(days=40),
                'booked': self.today - timedelta(days=12), 'pax_groups': 3}
        self._book(trip)
        ids = [cl.pk for cl in trip['cls']]
        ConfirmationLetter.objects.filter(pk__in=ids).update(reservation_status='DEFINITE')
        for cl in trip['cls']:
            cl.reservation_status = 'DEFINITE'
        inv = trip['invoice'] or self._invoice(trip)
        cns.void_invoice(inv, reason='Grup batal sebelum DP — seluruh CL dibatalkan', created_by=self.user,
                         void_date=self.today - timedelta(days=8))
        ConfirmationLetter.objects.filter(pk__in=ids).update(reservation_status='CANCELLED')

        self._bank_statement()

    def _bank_statement(self):
        """Mandiri IDR statement for last month, as the bank would show it:
        every cash-book movement (some a day later on the bank side) plus the
        monthly admin fee nobody has booked yet. Suggested matches are
        accepted, so the fee is the one difference left to resolve."""
        from hw.finance import reconciliation_service as rs
        from hw.models.bank_transaction import BankTransaction
        first = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last = self.today.replace(day=1) - timedelta(days=1)
        if first < self.start:
            return
        rows = BankTransaction.objects.filter(
            bank_account=self.idr, transaction_date__gte=first, transaction_date__lte=last,
        ).exclude(status=BankTransaction.STATUS_VOIDED).exclude(source_type='OpeningBalanceBank').order_by('transaction_date', 'pk')
        labels = {'PaymentRecord': 'TRSF MASUK', 'Remittance': 'TRSF KELUAR SWIFT', 'ExpensePayment': 'PEMBAYARAN',
                  'CurrencyExchangeIn': 'JUAL VALAS USD', 'Refund': 'TRSF KELUAR'}
        lines = []
        for tx in rows:
            day = min(tx.transaction_date + timedelta(days=self.rng.choice([0, 0, 0, 1])), last)
            lines.append({'line_date': day, 'direction': tx.direction, 'amount': tx.amount,
                          'description': f"{labels.get(tx.source_type, 'MUTASI')} {tx.reference}".strip(),
                          'reference': tx.reference})
        fee = 15_000
        lines.append({'line_date': last, 'direction': 'out', 'amount': fee, 'description': 'BIAYA ADM BULANAN', 'reference': ''})
        opening = rs.book_balance(self.idr, first - timedelta(days=1))
        closing = rs.book_balance(self.idr, last) - fee
        st = rs.create_statement(
            account=self.idr, period_start=first, period_end=last, opening_balance=opening, closing_balance=closing,
            lines=lines, created_by=self.user, source_filename=f'mandiri-{first:%Y%m}.csv',
        )
        rs.match_suggested(st)

    def _report(self):
        from hw.finance import fund_flow
        from hw.models import (ConfirmationLetter, CurrencyExchange, Expense, Invoice, Remittance,
                               RemittanceSettlement)
        from hw.models.payment import PaymentRecord
        fx = fund_flow.fx_profit(branch='sby')
        self.stdout.write(self.style.SUCCESS(
            f'Seeded: {ConfirmationLetter.objects.count()} CL, {Invoice.objects.count()} invoices, '
            f'{PaymentRecord.objects.count()} payments, {CurrencyExchange.objects.count()} exchanges, '
            f'{Remittance.objects.count()} transfers ({RemittanceSettlement.objects.count()} received), '
            f'{Expense.objects.count()} expenses. Branch FX profit: {fx["total_profit_idr"]:,} IDR.'
        ))


def _dt(day):
    from datetime import datetime, time
    from django.utils import timezone
    return timezone.make_aware(datetime.combine(day, time(9, 30)))
