"""Alokasi uang remittance ke reservasi -- dilakukan SAAT PUSAT MENERIMA.

Transfer baru keluar dari Kas SBY sebagai lump-sum (tanpa dimensi reservasi).
Setiap RemittanceSettlement membawa alokasinya sendiri (RemittanceLine dengan
`settlement` terisi). Jurnalnya berupa reklasifikasi Kas SBY bertanggal
penerimaan:

    Dr Kas SBY (tanpa reservasi)   Σ
       Cr Kas SBY [reservasi a]      a
       Cr Kas SBY [reservasi c]      c

Saldo Kas SBY tidak berubah, tapi kredit per reservasi membuat
`reservation_cash_breakdown().mengendap` turun. Jurnal kirim tidak pernah
diposting ulang, jadi periode bulan transfer yang sudah ditutup tidak
menghalangi alokasi.

(Dulu ada jalur lama: baris dialokasikan saat kirim,
dijurnal lewat segmen kirim `send_segments`).
"""
from datetime import date

from django.db.models import Sum

from ..models.journal import JournalEntry
from .errors import FinanceError

ALLOCATION_SOURCE = 'RemittanceAllocation'


def build_reservasi_mengendap():
    """Semua reservasi Konoz, termasuk yang belum ada pembayaran sama sekali.

    Reservasi Cancelled disembunyikan kecuali uangnya terlanjur bergerak
    (sudah dibayar client dan/atau sudah dikirim), sama seperti aturan di
    `_build_ledger_rows`.
    """
    from ..models import ConfirmationLetter, Reservation
    from . import queries as finance_queries

    reservations = Reservation.objects.all().select_related('invoice__client')
    breakdown = finance_queries.reservation_cash_breakdown()

    cancelled_numbers = set(
        ConfirmationLetter.objects.filter(
            reservation_status__iexact='CANCELLED',
        ).values_list('confirmation_number', flat=True)
    )

    empty = {'terbayar_sby': 0, 'terbayar_direct': 0, 'sudah_dikirim': 0, 'mengendap': 0}
    result = []
    for r in reservations:
        d = breakdown.get(r.id, empty)
        terbayar_sby = d['terbayar_sby']
        terbayar_direct = d['terbayar_direct']
        sudah_dikirim = d['sudah_dikirim']
        # mengendap boleh negatif: Surabaya bisa mengirim lebih dari yang
        # pernah diterima untuk reservasi ini (kredit di pusat).
        mengendap = d['mengendap']
        # Baris yang sudah di-void (invoice void / reservasi dikeluarkan) dan
        # reservasi batal hanya relevan kalau uangnya terlanjur bergerak.
        if (
            (r.voided_at is not None or r.reservation_number in cancelled_numbers)
            and not terbayar_sby and not terbayar_direct and not sudah_dikirim
        ):
            continue
        result.append({
            'reservation_id': r.id,
            'linked_number': r.reservation_number,
            'invoice_id': r.invoice_id,
            'invoice_number': r.invoice.invoice_number,
            'customer_name': r.invoice.customer_name,
            'hotel': r.hotel,
            'check_in': r.check_in,
            'check_out': r.check_out,
            'total_sar': r.total_sar,
            'terbayar_sby': terbayar_sby,
            'terbayar_direct': terbayar_direct,
            'terbayar_total': terbayar_sby + terbayar_direct,
            'sudah_dikirim': sudah_dikirim,
            'mengendap': mengendap,
        })

    result.sort(key=lambda x: x['check_in'] or date.max)
    return result


def candidates(remittance, settlement=None):
    """Reservasi yang uang klien-nya siap dialokasikan untuk penerimaan ini.

    `available` = uang klien di Surabaya yang belum dialokasikan. Saat
    mengoreksi `settlement`, alokasinya sendiri dihitung balik sebagai tersedia.
    Urutan = urutan isian otomatis: yang lunas dulu, lalu check-in terdekat
    (klien yang belum lunas sengaja ditahan belakangan)."""
    own = {}
    if settlement is not None:
        for line in settlement.allocations.all():
            key = (line.linked_number, line.invoice_id)
            own[key] = own.get(key, 0) + int(line.amount_sar or 0)

    rows = []
    for r in build_reservasi_mengendap():
        current = own.get((r['linked_number'], r['invoice_id']), 0)
        available = max(int(r['mengendap']) + current, 0)
        if available <= 0:
            continue
        total = int(r['total_sar'] or 0)
        rows.append({
            **r,
            'available': available,
            'current': current,
            'paid_in_full': total > 0 and r['terbayar_total'] >= total,
        })
    rows.sort(key=lambda x: (not x['paid_in_full'], x['check_in'] or date.max, x['linked_number']))
    return rows


def suggest(rows, amount):
    """Isian otomatis: isi berurutan sesuai `candidates` sampai `amount` habis.
    → {linked_number: nominal}."""
    left = max(int(amount or 0), 0)
    out = {}
    for r in rows:
        if left <= 0:
            break
        take = min(r['available'], left)
        if take > 0:
            out[r['linked_number']] = take
            left -= take
    return out


def remaining_to_allocate(remittance, settlement=None):
    """Sisa nominal transfer yang belum dialokasikan (di luar `settlement`)."""
    if remittance.expected_sar is None:
        return 0
    others = remittance.lines.all()
    if settlement is not None:
        others = others.exclude(settlement=settlement)
    return max(remittance.expected_sar - int(others.aggregate(t=Sum('amount_sar'))['t'] or 0), 0)


def transfer_position(remittance, inputs=None):
    """Uang transfer lump-sum yang belum dialokasikan, dipecah menurut
    keberadaannya. Bagian-bagiannya selalu berjumlah `unallocated`, jadi
    "Masih di Surabaya" = Σ uang klien belum dialokasikan − Σ unallocated.

    - in_transit: belum diterima Pusat
    - received_unallocated: sudah diterima, belum dibagikan ke reservasi
    - fee: sisa pada transfer yang selisihnya sudah ditutup (biaya/kurs)
    None untuk transfer lama tanpa nominal IDR/kurs.

    `inputs` = hasil _position_inputs() untuk daftar (lewat positions_for);
    tanpa itu angkanya diambil per transfer."""
    expected = remittance.expected_sar
    if expected is None:
        return None
    if inputs is None:
        inputs = _position_inputs([remittance])
    pk = remittance.pk

    allocated = inputs['allocated'].get(pk, 0)
    settled = inputs['settled'].get(pk, 0)
    basis = inputs['sent'].get(pk, 0) or expected  # = settlement_basis_sar
    unallocated = max(expected - allocated, 0)
    done = remittance.status == remittance.STATUS_RECEIVED or pk in inputs['diff_closed']
    waiting = 0 if done else max(basis - settled, 0)
    in_transit = min(waiting, unallocated)
    received_unallocated = min(max(settled - allocated, 0), unallocated - in_transit)
    return {
        'expected': expected,
        'allocated': allocated,
        'settled': settled,
        'unallocated': unallocated,
        'in_transit': in_transit,
        'received_unallocated': received_unallocated,
        'fee': unallocated - in_transit - received_unallocated,
    }


def _sum_by_remittance(qs, field, key='remittance_id'):
    return {
        row[key]: int(row['t'] or 0)
        for row in qs.order_by().values(key).annotate(t=Sum(field))
    }


def _position_inputs(remittances):
    """Angka yang dibaca transfer_position, untuk banyak transfer sekaligus:
    jumlah query tetap, tidak bertambah per transfer."""
    from ..models import RemittanceLine
    from ..models.settlement import RemittanceSettlement
    from . import queries

    ids = [r.pk for r in remittances]
    reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
    return {
        'allocated': _sum_by_remittance(
            RemittanceLine.objects.filter(settlement__remittance_id__in=ids), 'amount_sar', 'settlement__remittance_id',
        ),
        'settled': _sum_by_remittance(
            RemittanceSettlement.objects.filter(remittance_id__in=ids), 'received_amount_sar',
        ),
        'sent': {k: int(v) for k, v in queries.remittance_sent_map(ids).items()},
        'diff_closed': set(
            JournalEntry.objects.for_source('RemittanceDiff', ids).live().values_list('source_remittance_id', flat=True)
        ),
    }


def annotate_statuses(remittances, inputs=None):
    """Hitung `status` banyak transfer dengan jumlah query tetap, lalu simpan
    di objeknya (Remittance.status membacanya). Mengembalikan daftar transfer."""
    from ..models import Remittance
    remittances = list(remittances)
    if inputs is None:
        inputs = _position_inputs(remittances)
    for r in remittances:
        basis = inputs['sent'].get(r.pk, 0) or r.expected_sar or 0
        settled = inputs['settled'].get(r.pk, 0)
        received = (basis and settled >= basis) or r.pk in inputs['diff_closed']
        r._status_cache = Remittance.STATUS_RECEIVED if received else Remittance.STATUS_PENDING
    return remittances


def positions_for(remittances):
    """[(remittance, transfer_position)] untuk banyak transfer lump-sum."""
    remittances = list(remittances)
    inputs = _position_inputs(remittances)
    annotate_statuses(remittances, inputs)
    return [(r, transfer_position(r, inputs)) for r in remittances]


def transfer_figures(remittance, sent=None, settled=None):
    """Angka satu transfer -- satu definisi untuk Recap, KPI tab Transfer, dan
    PDF rekap.

    received = yang benar-benar masuk Kas Pusat: Σ penerimaan.
    outstanding = masih di jalan; difference = biaya (+) / laba kurs (−) pada
    transfer yang sudah diterima. `sent`/`settled` boleh dioper dari query
    bulk supaya daftar tidak N+1."""
    if sent is None:
        sent = int(remittance.total_sar or 0)
    if settled is None:
        settled = remittance.settled_sar
    done = remittance.status == remittance.STATUS_RECEIVED
    received = settled
    basis = sent or remittance.expected_sar or 0
    return {
        'state': 'received' if done else ('partial' if received > 0 else 'pending'),
        'sent': sent,
        'received': received,
        'outstanding': 0 if done else max(basis - received, 0),
        'difference': basis - received if done else 0,
    }


def figures_for(remittances):
    """[(remittance, transfer_figures)] untuk banyak transfer sekaligus.
    Remittance sebaiknya sudah prefetch_related('settlements')."""
    from . import queries
    remittances = annotate_statuses(remittances)
    sent_map = queries.remittance_sent_map([r.pk for r in remittances])
    return [
        (r, transfer_figures(
            r, sent=int(sent_map.get(r.pk, 0)),
            settled=sum(int(s.received_amount_sar) for s in r.settlements.all()),
        ))
        for r in remittances
    ]


def transfer_totals():
    """KPI tab Transfer. `received_unallocated` sama dengan angka di Tracking
    (transfer_position); `in_transit` mencakup semua transfer yang belum
    diterima penuh, termasuk transfer lama yang barisnya diisi saat kirim."""
    from ..models import Remittance
    totals = {'sent': 0, 'received': 0, 'in_transit': 0, 'received_unallocated': 0}
    remittances = list(Remittance.objects.prefetch_related('settlements'))
    for rem, fig in figures_for(remittances):
        totals['sent'] += fig['sent']
        totals['received'] += fig['received']
        totals['in_transit'] += fig['outstanding']
    # pos None: IDR terisi tapi kurs kosong -- belum lump-sum yang bisa dihitung.
    for rem, pos in positions_for(remittances):
        if pos:
            totals['received_unallocated'] += pos['received_unallocated']
    return totals


def open_transfers():
    """Transfer lump-sum yang masih punya uang belum dialokasikan."""
    from ..models import Remittance
    out = []
    for rem, pos in positions_for(Remittance.objects.order_by('date', 'pk')):
        if pos and pos['in_transit'] + pos['received_unallocated'] > 0:
            out.append({
                'id': rem.pk, 'remittance_number': rem.remittance_number,
                'date': rem.date.strftime('%d/%m/%Y'), **pos,
            })
    return out


def validate(remittance, allocations, settlement=None):
    """Normalisasi + validasi payload alokasi → list {row, amount_sar}.

    Aturan (server-side, bukan hanya browser):
    - per reservasi <= uang klien siap (`candidates().available`);
    - Σ seluruh baris remittance <= nominal transfer (expected_sar);
    - hanya untuk transfer lump-sum (punya amount_idr + kurs).
    Nominal per penerimaan sengaja TIDAK dikunci = nominal diterima: penerimaan
    terakhir yang kena biaya/kurs tetap boleh mengalokasikan sisa penuh,
    selisihnya ditutup lewat close_remittance_diff."""
    merged = {}
    for item in allocations or []:
        number = str(item.get('linked_number') or '').strip()
        try:
            amount = int(round(float(item.get('amount_sar') or 0)))
        except (TypeError, ValueError):
            raise FinanceError(f'Nominal alokasi {number or "?"} tidak valid') from None
        if amount < 0:
            raise FinanceError(f'Nominal alokasi {number} tidak boleh negatif')
        if not number or amount == 0:
            continue
        invoice_id = item.get('invoice_id') or None
        key = (number, int(invoice_id) if invoice_id else None)
        merged[key] = merged.get(key, 0) + amount
    if not merged:
        return []

    if remittance.expected_sar is None:
        raise FinanceError(
            f'Remittance {remittance.remittance_number} tidak punya nominal IDR dan kurs — '
            'alokasi per penerimaan hanya untuk transfer lump-sum.'
        )

    rows = candidates(remittance, settlement)
    out = []
    for (number, invoice_id), amount in merged.items():
        matches = [
            r for r in rows
            if r['linked_number'] == number and (invoice_id is None or r['invoice_id'] == invoice_id)
        ]
        if not matches:
            raise FinanceError(f'Reservasi {number} tidak punya uang klien yang siap dialokasikan')
        if len(matches) > 1:
            raise FinanceError(f'Nomor reservasi {number} ada di lebih dari satu invoice — pilih invoice-nya')
        row = matches[0]
        if amount > row['available']:
            raise FinanceError(
                f'Alokasi {number} {amount:,} SAR melebihi uang klien yang siap ({row["available"]:,} SAR)'
            )
        out.append({'row': row, 'amount_sar': amount})

    remaining = remaining_to_allocate(remittance, settlement)
    total = sum(v['amount_sar'] for v in out)
    if total > remaining:
        raise FinanceError(
            f'Total alokasi {total:,} SAR melebihi sisa transfer {remittance.remittance_number} '
            f'yang belum dialokasikan ({remaining:,} SAR)'
        )
    return out


def create_lines(settlement, validated):
    from ..models import RemittanceLine
    return [
        RemittanceLine.objects.create(
            settlement=settlement, invoice_line_id=v['row']['reservation_id'], amount_sar=v['amount_sar'],
        )
        for v in validated
    ]


def live_allocation_entries(settlement):
    return list(JournalEntry.objects.for_source(ALLOCATION_SOURCE, settlement.pk).live())


def post_allocation(settlement, validated, *, entry_date, created_by=None):
    """Reklasifikasi kas rekening asal: pindahkan kredit kirim lump-sum ke dimensi reservasi."""
    if not validated:
        return None
    from ..models import Invoice
    from ..views.invoice_billing import _billing_client
    from .posting import post_entry

    remittance = settlement.remittance
    source, branch = remittance.from_account.ledger_account_id, remittance.from_account.branch_id
    invoices = Invoice.objects.in_bulk({v['row']['invoice_id'] for v in validated if v['row']['invoice_id']})
    total = sum(v['amount_sar'] for v in validated)
    lines = [{'account': source, 'debit': total, 'remittance': remittance.pk, 'branch': branch}]
    for v in validated:
        row = v['row']
        invoice = invoices.get(row['invoice_id'])
        client = _billing_client(invoice) if invoice else None
        lines.append({
            'account': source, 'credit': v['amount_sar'], 'remittance': remittance.pk,
            'branch': branch, 'invoice_line': row['reservation_id'], 'invoice': row['invoice_id'],
            'client': getattr(client, 'pk', None),
        })
    return post_entry(
        entry_type=JournalEntry.TYPE_ALLOCATE,
        description=(
            f"Alokasi {remittance.remittance_number} — penerimaan "
            f"{settlement.received_date:%d/%m/%Y}"
        ),
        entry_date=entry_date,
        lines=lines,
        source_type=ALLOCATION_SOURCE,
        source_id=settlement.pk,
        created_by=created_by,
    )
