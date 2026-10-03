import logging

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import Remittance, RemittanceLine
from ..finance import fund_flow, posting, remittance_allocation
from ..finance_helpers import FinanceError
from ..permissions import require_perm
from .helpers import validate_proof_file, period_label as _period_label, csv_export_response

logger = logging.getLogger(__name__)


def _parse_int(raw):
    raw = (raw or '').strip().replace(',', '').replace('.', '')
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _parse_transfer_fields(request):
    """Field transfer bank fisik dari form -- semuanya opsional.

    amount_idr    : nominal yang keluar dari rekening asal (mata uang rekening itu)
    exchange_rate : kurs rencana (mata uang asal per 1 SAR)
    (nilai ketiga, nominal diterima manual jalur lama, tidak dipakai lagi)
    """
    def _num(key):
        raw = (request.POST.get(key) or '').strip().replace(',', '')
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    amount_idr = _num('amount_idr')
    exchange_rate = _num('exchange_rate')
    received = _num('received_amount_sar')
    return (
        int(amount_idr) if amount_idr else None,
        exchange_rate if exchange_rate else None,
        int(received) if received else None,
    )


def _prev_sent_map(rem, linked_numbers):
    """Total SAR yang sudah dialokasikan per reservasi lewat remittance SEBELUM
    `rem` (urut tanggal kirim, lalu waktu dibuat)."""
    if not linked_numbers:
        return {}
    earlier = (
        Q(settlement__remittance__date__lt=rem.date)
        | Q(settlement__remittance__date=rem.date, settlement__remittance__created_at__lt=rem.created_at)
    )
    return {
        row['number']: int(row['total'] or 0)
        for row in RemittanceLine.objects.filter(
            earlier, invoice_line__confirmation_letter__confirmation_number__in=list(linked_numbers),
        ).exclude(settlement__remittance=rem).values(
            number=F('invoice_line__confirmation_letter__confirmation_number'),
        ).annotate(total=Sum('amount_sar'))
    }


def _fx_stats():
    from ..finance import fund_flow
    fx = fund_flow.fx_profit(branch='sby')
    held = fx['client_money_held']
    return {
        'fx_profit_idr': fx['total_profit_idr'],
        'client_idr_held': held.get('IDR', {}).get('amount', 0),
        'client_usd_held': held.get('USD', {}).get('amount', 0),
    }


def _compute_stats():
    """KPI tab Transfer.

    Baris utama memakai empat istilah tetap remittance (dikirim, diterima, di
    jalan, diterima belum dialokasikan) -- angka yang sama dengan Recap, Detail,
    dan Tracking. Posisi kas di bawahnya sekunder: angka yang tidak ada di tab
    lain. `total_tagihan`, kas Pusat, dan kas Surabaya sengaja tidak lagi di
    sini (sudah di Invoice / Finance Dashboard, dan kas Surabaya tumpang tindih
    dengan "Masih di Surabaya" di Tracking)."""
    from ..finance import queries as finance_queries

    stats = remittance_allocation.transfer_totals()
    # Sepasang angka wajib berdampingan: kewajiban_kirim sendirian bisa salah
    # dibaca sebagai kredit Surabaya padahal surplus itu bisa milik klien
    # (kelebihan bayar langsung ke pusat), bukan milik Surabaya.
    stats.update({
        'kewajiban_kirim': finance_queries.kewajiban_kirim_sby(),
        'saldo_dana_klien': finance_queries.total_client_credit_balance(),
        # The branch's income is the exchange spread: realized profit on what
        # was sent, and the client money still held (at cost) not yet sent.
        **_fx_stats(),
    })
    return stats


# Dipindah ke hw/finance/remittance_allocation.py (dipakai juga oleh service
# alokasi penerimaan); nama lama dipertahankan untuk pemanggil yang ada.
_build_reservasi_mengendap = remittance_allocation.build_reservasi_mengendap


def _can_record_receipt(rem):
    """Record Receipt terbuka selama Pusat belum menerima penuh -- aturan yang
    sama ditegakkan di settlement_service.add_settlement."""
    return rem.status == Remittance.STATUS_PENDING


@require_perm('remittance', 'view')
def remittance_list(request):
    from django.db.models import Q
    from ..finance import queries as finance_queries
    tab = request.GET.get('tab', '')
    if tab not in ('tracking', 'recap'):
        tab = 'transfers'
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()

    remittances, stats = [], None
    if tab == 'transfers':
        qs = Remittance.objects.all().prefetch_related('settlements__allocations').order_by('-date')
        if q:
            qs = qs.filter(
                Q(remittance_number__icontains=q) |
                Q(receipt_reference__icontains=q) |
                Q(note__icontains=q)
            )
        qs = remittance_allocation.annotate_statuses(qs.annotate(settled_sar_sum=Sum(
            'settlements__received_amount_sar', filter=Q(settlements__voided_at__isnull=True),
        )))
        # Status is derived from the receipts, so the filter runs here.
        if status_filter in ('pending', 'received'):
            qs = [rem for rem in qs if rem.status == status_filter]
        sent_map = finance_queries.remittance_sent_map([rem.pk for rem in qs])
        stats = _compute_stats()
        remittances = [{
            "id": rem.id,
            "remittance_number": rem.remittance_number,
            "date": rem.date.strftime("%d/%m/%Y"),
            "total_sar": int(sent_map.get(rem.pk, 0)),
            "status": rem.status,
            "settled_sar": int(rem.settled_sar_sum or 0),
            "expected_sar": rem.expected_sar,
            "allocated_sar": sum(int(a.amount_sar) for s in rem.settlements.all() for a in s.allocations.all()),
            "proof_url": rem.proof.url if rem.proof else None,
            "can_record_receipt": _can_record_receipt(rem),
        } for rem in qs]

    return inertia_render(request, "Remittance/List", props={
        "tab": tab,
        "remittances": remittances,
        "stats": stats,
        "status_filter": status_filter,
        "q": q,
        "total_count": Remittance.objects.all().count(),
        "tracking": _compute_tracking_data() if tab == 'tracking' else None,
        "monthly": _compute_recap_data() if tab == 'recap' else None,
    })


@require_perm('remittance', 'create')
@transaction.atomic
def remittance_new(request):
    """Transfer baru = lump-sum: uang IDR keluar dari bank Surabaya dengan kurs
    tertentu. Tidak memilih reservasi -- alokasi ke reservasi dilakukan saat
    Pusat mencatat penerimaan (hw/finance/remittance_allocation.py), karena
    baru saat itu jelas uang siapa yang didahulukan."""
    from ..models.bank import BankAccount
    # Transfers leave a branch's IDR bank account (never HQ's own).
    from_accounts = list(
        BankAccount.objects.filter(is_active=True, currency='IDR')
        .exclude(branch_id='pusat').select_related('branch').order_by('bank_name', 'account_identifier')
    )

    def form_page(error=None):
        return inertia_render(request, "Remittance/Form", props={
            'open_transfers': remittance_allocation.open_transfers(),
            'error': error,
            'today': str(date.today()),
            # Uang client rupiah yang belum disetor + kurs asalnya (laba kurs di form).
            'fx_pool': fund_flow.idr_pool('sby'),
            'from_accounts': [{
                'value': str(a.pk),
                'label': f"{a.bank_name} {a.account_identifier} · {a.branch.name}".strip(),
            } for a in from_accounts],
        })

    if request.method != 'POST':
        return form_page()

    remittance_date = request.POST.get('date') or str(date.today())
    receipt_reference = request.POST.get('receipt_reference', '').strip()
    note = request.POST.get('note', '').strip()
    proof = request.FILES.get('proof')
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            return form_page(proof_error)

    # `received_amount_sar` (jalur lama) sengaja diabaikan di sini sejak
    # 2026-09-14 -- HQ belum tentu sudah menerima apa pun saat remittance
    # baru dibuat, dan mengisinya di sini dulu mengunci remittance ini
    # dari jalur settlement bertahap (RemittanceSettlement) selamanya
    # (lihat guard di settlement_service.add_settlement). Satu-satunya
    # cara mencatat penerimaan untuk remittance baru sekarang: Record
    # Receipt di list/detail. `amount_idr`/`exchange_rate` tetap diterima -- itu
    # fakta sisi KIRIM (uang keluar bank cabang), bukan sisi terima.
    amount_idr, exchange_rate, _legacy_received_sar_ignored = _parse_transfer_fields(request)
    if not amount_idr or not exchange_rate:
        return form_page('Enter the IDR amount and exchange rate.')
    from_account = next((a for a in from_accounts if str(a.pk) == request.POST.get('from_bank_account')), None)
    if from_account is None:
        return form_page('Choose the IDR bank account the money left from.'
                         if from_accounts else 'Add an IDR bank account in Bank Balances first.')

    from ..finance.bank_ledger import default_account
    to_account = default_account('pusat', 'SAR')
    if to_account is None:
        return form_page('Add an HQ SAR account in Bank Balances first.')
    rem = Remittance.objects.create(
        remittance_number=Remittance.generate_number(),
        date=remittance_date,
        receipt_reference=receipt_reference,
        amount_sent=amount_idr,
        exchange_rate=exchange_rate,
        from_account=from_account,
        to_account=to_account,
        note=note,
    )
    # Cash book: the rupiah that left the branch account (fund-flow report).
    from ..finance.bank_ledger import record_bank_transaction
    record_bank_transaction(
        account=from_account, direction='out', amount_sar=rem.expected_sar,
        currency='IDR', amount=amount_idr, source_type='Remittance', source_id=rem.pk,
        transaction_date=rem.date, reference=receipt_reference,
    )
    if proof:
        rem.proof = proof
        rem.save()

    # Uang sudah keluar bank tapi belum milik reservasi mana pun. Posting
    # aggregate SBY->Transit via jurnal (Fase 7: tanpa shadow CashMovement).
    try:
        posting.resync_remittance(rem, created_by=request.user)
    except FinanceError as e:
        logger.warning("remittance %s: journal send resync gagal: %s", rem.remittance_number, e)
        messages.warning(request, f'Remittance dibuat, tapi jurnal belum tercatat: {e}')

    return redirect('remittance_detail', pk=rem.pk)


@require_perm('remittance', 'view')
def remittance_detail(request, pk):
    from ..models import Reservation
    rem = get_object_or_404(Remittance.objects.select_related('from_account', 'to_account'), pk=pk)

    from ..finance.settlement_service import diff_is_closed
    settlements = list(
        rem.settlements.order_by('received_date', 'id')
        .prefetch_related('allocations__invoice_line__invoice__client', 'allocations__invoice_line__confirmation_letter')
    )
    from ..models.bank_transaction import BankTransaction
    reconciled_receipts = set(
        BankTransaction.objects.filter(source_type='RemittanceSettlement', source_id__in=[x.pk for x in settlements])
        .filter(Q(status=BankTransaction.STATUS_RECONCILED) | Q(statement_lines__isnull=False))
        .values_list('source_id', flat=True)
    )
    alloc_res = {
        r['reservation_number']: r
        for r in Reservation.objects.numbered(
            a.linked_number for s in settlements for a in s.allocations.all()
        ).reservation_rows()
    }
    settled_total_sar = sum(int(s.received_amount_sar) for s in settlements)
    basis_sar = rem.settlement_basis_sar
    diff_closed = bool(settlements) and diff_is_closed(rem)
    # Selisih basis kirim vs Σ diterima: positif = kurang (biaya/FX),
    # negatif = lebih (laba kurs). Hanya bermakna setelah ada penerimaan.
    diff_sar = basis_sar - settled_total_sar if settlements and basis_sar is not None else None

    from ..finance import fund_flow
    sender = rem.from_account.branch_id if rem.from_account_id else 'sby'
    fx_row = next((r for r in fund_flow.fx_profit(branch=sender, date_to=rem.date)['transfers'] if r['id'] == rem.pk), None)

    return inertia_render(request, "Remittance/Detail", props={
        "fx": fx_row,
        "is_legacy": rem.is_legacy,
        "rem": {
            "id": rem.id,
            "remittance_number": rem.remittance_number,
            "date": rem.date.strftime("%d/%m/%Y"),
            "status": rem.status,
            "proof_url": rem.proof.url if rem.proof else None,
            "receipt_reference": rem.receipt_reference,
            "from_account": f"{rem.from_account.bank_name} {rem.from_account.account_identifier}".strip(),
            "to_account": str(rem.to_account),
            "note": rem.note,
            "total_sar": rem.total_sar,
            # Transfer bank fisik + progres alokasi ke reservasi
            "amount_idr": rem.amount_idr,
            "exchange_rate": float(rem.exchange_rate) if rem.exchange_rate else None,
            "expected_sar": rem.expected_sar,
            "received_amount_sar": None,
            "allocated_sar": rem.allocated_sar,
            "unallocated_sar": rem.unallocated_sar,
            # Penerimaan Pusat (RemittanceSettlement) -- lihat hw/models/settlement.py.
            "settlement_status": rem.settlement_status,
            "settled_total_sar": settled_total_sar,
            "settlement_basis_sar": basis_sar,
            "diff_sar": diff_sar,
            "diff_closed": diff_closed,
            "can_record_receipt": _can_record_receipt(rem),
            "can_close_diff": bool(diff_sar) and not diff_closed,
            "can_reopen_diff": diff_closed,
            "settlements": [{
                "id": s.pk,
                "received_amount_sar": int(s.received_amount_sar),
                "received_date": s.received_date.strftime("%d/%m/%Y"),
                "reference": s.reference,
                "can_delete": not diff_closed and s.pk not in reconciled_receipts,
                "allocations": [{
                    "linked_number": a.linked_number,
                    "amount_sar": int(a.amount_sar),
                    "customer_name": a.invoice.customer_name if a.invoice_id else "",
                    "hotel": alloc_res.get(a.linked_number, {}).get('hotel') or "",
                    "check_in": (
                        alloc_res[a.linked_number]['check_in'].strftime("%d/%m/%Y")
                        if alloc_res.get(a.linked_number, {}).get('check_in') else None
                    ),
                } for a in s.allocations.all()],
            } for s in settlements],
            # Transfer lump-sum: alokasi ke reservasi terjadi per penerimaan.
            "can_allocate": rem.expected_sar is not None,
            "position": remittance_allocation.transfer_position(rem),
        },
        # Allocations live under their receipts; there are no send-time lines.
        "lines": [],
    })


@require_perm('remittance', 'export')
def remittance_export_csv(request):
    remittances = Remittance.objects.all().prefetch_related(
        'settlements__allocations__invoice_line__invoice', 'settlements__allocations__invoice_line__confirmation_letter',
    )
    headers = ['Tanggal', 'Total SAR', 'Note', 'Res#', 'Invoice', 'Amount SAR']
    rows = []
    for rem in remittances:
        lines = [a for s in rem.settlements.all() for a in s.allocations.all()]
        if lines:
            for i, line in enumerate(lines):
                rows.append([
                    rem.date.strftime('%d/%m/%Y') if i == 0 else '',
                    rem.total_sar if i == 0 else '',
                    rem.note if i == 0 else '',
                    line.linked_number,
                    line.invoice.invoice_number if line.invoice else '',
                    line.amount_sar,
                ])
        else:
            rows.append([rem.date.strftime('%d/%m/%Y'), rem.total_sar, rem.note, '', '', ''])
    return csv_export_response('remittance.csv', headers, rows)


@require_perm('remittance', 'edit')
def remittance_edit(request, pk):
    # remittance yang sudah Received tetap boleh diedit: koreksi kadang baru
    # ketahuan setelah HQ menandai diterima
    rem = get_object_or_404(Remittance, pk=pk)
    if request.method == 'POST':
        rem.date = request.POST.get('date') or rem.date
        rem.receipt_reference = request.POST.get('receipt_reference', '').strip()
        rem.note = request.POST.get('note', '').strip()
        amount_sent, exchange_rate, _ignored = _parse_transfer_fields(request)
        update_fields = ['date', 'receipt_reference', 'note']
        if rem.is_legacy:
            # Setoran lama: SAR-nya sudah diterima Pusat dan tetap. User mengisi
            # rupiah yang benar-benar dikirim (kurs kirim mengikutinya) dan
            # rupiah yang dulu dibayar client (nominal original).
            sar = rem.expected_sar
            if amount_sent and sar:
                rem.amount_sent = amount_sent
                rem.exchange_rate = (Decimal(amount_sent) / Decimal(sar)).quantize(Decimal('0.0001'))
                update_fields += ['amount_sent', 'exchange_rate']
            original = _parse_int(request.POST.get('original_amount'))
            rem.original_amount = original if original and original > 0 else None
            update_fields.append('original_amount')
        elif amount_sent and exchange_rate and not rem.settlements.exists():
            # The amount and planned rate of the transfer can be corrected while
            # HQ has recorded nothing against it yet.
            rem.amount_sent, rem.exchange_rate = amount_sent, exchange_rate
            update_fields += ['amount_sent', 'exchange_rate']
        if request.POST.get('remove_proof'):
            rem.proof = None
            update_fields.append('proof')
        elif request.FILES.get('proof'):
            proof_error = validate_proof_file(request.FILES['proof'])
            if proof_error:
                raise ValueError(f"Remittance proof: {proof_error}")
            rem.proof = request.FILES['proof']
            update_fields.append('proof')
        rem.save(update_fields=update_fields)

        # The cash book and the journal's send leg follow the transfer.
        from ..finance.bank_ledger import sync_bank_transaction
        try:
            sync_bank_transaction(
                account=rem.from_account, direction='out', amount_sar=rem.expected_sar,
                currency=rem.from_account.currency, amount=rem.amount_sent, source_type='Remittance',
                source_id=rem.pk, transaction_date=rem.date, reference=rem.receipt_reference,
            )
            posting.resync_remittance(rem, created_by=request.user)
        except FinanceError as e:
            logger.warning("remittance %s: buku kas / jurnal kirim gagal disamakan: %s", rem.remittance_number, e)
            messages.warning(request, f'Tersimpan, tapi buku kas/jurnal belum ikut berubah: {e}')
        return redirect('remittance_detail', pk=rem.pk)

    # Allocations are made per receipt (Record Receipt / change allocation).
    lines_editable = False
    lines = []
    return inertia_render(request, "Remittance/Edit", props={
        "rem": {
            "id": rem.id,
            "remittance_number": rem.remittance_number,
            "date": rem.date.strftime("%Y-%m-%d"),
            "receipt_reference": rem.receipt_reference or "",
            "status": rem.status,
            "has_receipts": rem.settlements.exists(),
            "note": rem.note or "",
            "proof_url": rem.proof.url if rem.proof else None,
            "amount_idr": rem.amount_sent,
            "exchange_rate": float(rem.exchange_rate) if rem.exchange_rate else None,
            "expected_sar": rem.expected_sar,
            "is_legacy": rem.is_legacy,
            "original_amount": rem.original_amount,
        },
        # Posisi uang client tepat sebelum setoran ini (kurs asalnya).
        "fx_pool": fund_flow.idr_pool(rem.from_account.branch_id, before=rem.pk),
        "lines": [{
            "line_id": l.pk,
            "linked_number": l.linked_number,
            "amount_sar": int(l.amount_sar or 0),
            "invoice": {
                "pk": l.invoice.pk,
                "invoice_number": l.invoice.invoice_number,
                "customer_name": l.invoice.customer_name,
            } if l.invoice_id else None,
        } for l in lines],
        "reservasi": [],
        "lines_editable": lines_editable,
    })


@require_perm('remittance', 'export')
def remittance_pdf(request, pk):
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url
    from ..models import Reservation
    rem = get_object_or_404(Remittance, pk=pk)
    raw_lines = list(
        rem.lines.select_related('invoice_line__invoice__client', 'invoice_line__confirmation_letter', 'settlement')
        .order_by('invoice_line__confirmation_letter__confirmation_number')
    )
    linked_numbers = [l.linked_number for l in raw_lines]

    res_map = {
        r['reservation_number']: r
        for r in Reservation.objects.numbered(linked_numbers).reservation_rows()
    }
    prev_map = _prev_sent_map(rem, linked_numbers)

    lines = [{'line': l, 'check_in': res_map.get(l.linked_number, {}).get('check_in'), 'hotel': res_map.get(l.linked_number, {}).get('hotel', '—'), 'prev_sent': prev_map.get(l.linked_number, 0)} for l in raw_lines]
    # urutkan berdasarkan check-in terdekat lebih dulu; baris tanpa check-in ditaruh paling bawah
    lines.sort(key=lambda row: (row['check_in'] is None, row['check_in'] or date.max, row['line'].linked_number or ''))

    return _render_list_pdf(
        request, rem.lines.none(),
        template='hw/remittance/remittance_pdf.html',
        filename=f'remittance_{rem.date}.pdf',
        extra_ctx={'rem': rem, 'lines': lines, 'logo_url': _logo_file_url(), 'total_sar': sum(int(l.amount_sar or 0) for l in raw_lines)},
    )


@require_perm('remittance', 'edit')
@require_POST
def remittance_upload_proof(request, pk):
    rem = get_object_or_404(Remittance, pk=pk)
    proof = request.FILES.get('proof')
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            raise ValueError(f"Remittance proof: {proof_error}")
        rem.proof = proof
        rem.save(update_fields=['proof'])
    return redirect('remittance_detail', pk=rem.pk)


@require_perm('remittance', 'delete')
@require_POST
def remittance_delete(request, pk):
    rem = get_object_or_404(Remittance, pk=pk)
    # System of record (Fase 7): jurnal REMITTANCE hidup merepresentasikan
    # perpindahan kas SBY->PUSAT. Remittance yang sudah menyentuh jurnal --
    # langsung atau lewat baris -- tidak boleh hilang diam-diam.
    from ..finance import queries as finance_queries
    # Entry yang sudah dibalik pun tetap menunjuk transfer ini sebagai sumbernya.
    if (rem.settlements.exists() or rem.journal_entries.exists()
            or finance_queries.remittance_has_live_entries(rem.pk)):
        messages.error(request, f'Remittance {rem.remittance_number} tidak bisa dihapus karena sudah tercatat di ledger keuangan.')
        return redirect('remittance_detail', pk=pk)
    from ..finance.bank_ledger import void_bank_transactions
    try:
        with transaction.atomic():
            # The transfer never happened: its cash-book row stops counting.
            void_bank_transactions('Remittance', rem.pk)
            rem.delete()
    except FinanceError as e:
        messages.error(request, str(e))
        return redirect('remittance_detail', pk=pk)
    return redirect('remittance_list')


@require_perm('remittance', 'view')
def remittance_recap(request):
    """URL lama; rekap sekarang tab di halaman Remittance."""
    return redirect('/remittance/?tab=recap')


def _recap_totals(figures):
    """Jumlah per kelompok transfer (bulan Recap / PDF rekap)."""
    totals = {
        'total_sent': 0, 'total_received': 0, 'total_outstanding': 0, 'total_difference': 0,
        'count_pending': 0, 'count_partial': 0, 'count_received': 0,
    }
    for _rem, fig in figures:
        totals['total_sent'] += fig['sent']
        totals['total_received'] += fig['received']
        totals['total_outstanding'] += fig['outstanding']
        totals['total_difference'] += fig['difference']
        totals[f"count_{fig['state']}"] += 1
    return totals


def _compute_recap_data():
    """Rangkuman remittance per bulan transfer (tab Recap).

    "Diterima" = nominal yang benar-benar masuk Kas Pusat
    (remittance_allocation.transfer_figures), bukan nominal kirim transfer yang
    berstatus received. Penerimaan dihitung di bulan transfernya, bukan bulan
    diterima."""
    remittances = (
        Remittance.objects.all().prefetch_related('settlements__allocations').order_by('-date', '-created_at')
    )
    months = {}
    for rem, fig in remittance_allocation.figures_for(remittances):
        key = rem.date.strftime('%Y-%m')
        month = months.setdefault(key, {
            'label': rem.date.strftime('%B %Y'), 'period': key, 'figures': [],
        })
        month['figures'].append((rem, fig))

    out = []
    for month in months.values():
        figures = month.pop('figures')
        month.update(_recap_totals(figures))
        month['remittances'] = [{
            'id': rem.id,
            'remittance_number': rem.remittance_number,
            'date': rem.date.strftime('%d/%m/%Y'),
            'lines_count': sum(len(s.allocations.all()) for s in rem.settlements.all()),
            'state': fig['state'],
            'sent': fig['sent'],
            'received': fig['received'],
            'difference': fig['difference'],
        } for rem, fig in figures]
        out.append(month)
    return out


@require_perm('remittance', 'view')
def remittance_tracking(request):
    """URL lama (masih ditautkan dari luar); tracking sekarang tab di halaman
    Remittance."""
    return redirect('/remittance/?tab=tracking')


def _tracking_bucket(check_in, today):
    if check_in is None:
        return 'later'
    days = (check_in - today).days
    if days < 0:
        return 'past'
    if days <= 7:
        return 'week'
    if days <= 30:
        return 'month'
    return 'later'


def _compute_tracking_data():
    """Tab Tracking: uang klien di Surabaya yang belum dialokasikan ke uang yang
    diterima Pusat, per reservasi, dikelompokkan menurut dekatnya check-in.

    `summary` = hitungan jembatan yang bisa dicek:
        uang klien belum dialokasikan − di jalan − diterima belum dialokasikan
        − biaya/selisih = masih di Surabaya
    Bagian tengahnya dari transfer_position(), yang selalu berjumlah sisa
    transfer lump-sum yang belum dialokasikan."""
    from ..models import Invoice
    from ..models.settlement import RemittanceSettlement
    from ..finance import queries as finance_queries

    today = date.today()
    rows = remittance_allocation.build_reservasi_mengendap()
    history = finance_queries.reservation_remittance_map([r['linked_number'] for r in rows])
    client_names = dict(
        Invoice.objects.filter(pk__in={r['invoice_id'] for r in rows if r['invoice_id']})
        .values_list('pk', 'client__name')
    )

    reservations = []
    client_unallocated = 0
    for r in rows:
        unallocated = max(int(r['mengendap']), 0)
        events = history.get(r['linked_number'], [])
        if not unallocated and not events and not r['terbayar_total']:
            continue
        client_unallocated += unallocated
        reservations.append({
            'linked_number': r['linked_number'],
            'invoice_id': r['invoice_id'],
            'invoice_number': r['invoice_number'],
            'client_name': client_names.get(r['invoice_id']) or r['customer_name'] or '—',
            'hotel': r['hotel'] or '',
            'check_in': r['check_in'].strftime('%d/%m/%Y') if r['check_in'] else None,
            'bucket': _tracking_bucket(r['check_in'], today),
            'total_sar': int(r['total_sar'] or 0),
            'paid_sar': int(r['terbayar_total'] or 0),
            'unallocated': unallocated,
            'history': [{
                'rmt_id': h['rmt_id'],
                'rmt_number': h['rmt_number'],
                'kind': 'receipt' if h['received_date'] else 'send',
                'date': (h['received_date'] or h['date']).strftime('%d/%m/%Y') if (h['received_date'] or h['date']) else None,
                'status': h['status'],
                'amount_sar': h['amount_sar'],
            } for h in events],
        })

    in_transit = received_unallocated = fee = 0
    pending = []
    positions = [
        (rem, pos) for rem, pos in remittance_allocation.positions_for(
            Remittance.objects.order_by('date', 'pk'),
        ) if pos
    ]
    # Penerimaan yang belum habis dialokasikan: satu query untuk semua transfer.
    receipts_by_rem = {}
    for s in (
        RemittanceSettlement.objects
        .filter(remittance_id__in=[rem.pk for rem, pos in positions if pos['received_unallocated'] > 0])
        .annotate(alloc=Sum('allocations__amount_sar')).order_by('received_date', 'pk')
    ):
        receipts_by_rem.setdefault(s.remittance_id, []).append(s)
    for rem, pos in positions:
        in_transit += pos['in_transit']
        received_unallocated += pos['received_unallocated']
        fee += pos['fee']
        left = pos['received_unallocated']
        if left <= 0:
            continue
        for s in receipts_by_rem.get(rem.pk, []):
            gap = min(int(s.received_amount_sar) - int(s.alloc or 0), left)
            if gap > 0:
                pending.append({
                    'remittance_id': rem.pk, 'remittance_number': rem.remittance_number,
                    'settlement_id': s.pk, 'received_date': s.received_date.strftime('%d/%m/%Y'),
                    'amount_sar': gap,
                })
                left -= gap

    return {
        'summary': {
            'client_unallocated': client_unallocated,
            'in_transit': in_transit,
            'received_unallocated': received_unallocated,
            'fee': fee,
            'still_sby': client_unallocated - in_transit - received_unallocated - fee,
        },
        'pending_allocations': pending,
        'reservations': reservations,
    }


def _build_ledger_rows(date_from=None, date_to=None):
    """Buku besar Surabaya <-> Pusat, satu baris per reservasi.

    Debit   = seluruh uang client yang sudah dibayar untuk reservasi itu.
    Kredit  = uang yang sudah berada di Pusat, yaitu remittance dari Surabaya
              ditambah pembayaran metode 'direct' yang langsung masuk ke Pusat.
    Balance = Total tagihan reservasi dikurangi Kredit, yaitu kewajiban yang
              masih harus dikirim ke Pusat untuk hotel -- tetap muncul walau
              client belum bayar sama sekali, karena kewajiban ke hotel tidak
              tergantung status pembayaran client.

    Pembayaran 'direct' dihitung sebagai debit sekaligus kredit karena uangnya
    tidak pernah singgah di kas Surabaya, jadi tidak menambah saldo mengendap.

    Semua reservasi Definite dan Tentative ikut ditampilkan walau belum ada
    uang masuk atau kiriman, supaya bisa dipakai untuk pelacakan. Reservasi
    Cancelled hanya muncul kalau uangnya terlanjur bergerak.
    """
    from ..models import ConfirmationLetter, Reservation
    from ..finance import queries as finance_queries

    pool = defaultdict(lambda: {'debit': 0, 'credit': 0})
    direct_total = 0

    # semua reservasi Konoz ikut dilacak, bukan hanya yang sudah ada uangnya
    res_rows = list(Reservation.objects.all().reservation_rows())
    res_map = {r['reservation_number']: r for r in res_rows}

    # Debit = seluruh uang client yang sudah dibayar untuk reservasi (kas sby +
    # jkt + direct). Pembayaran 'direct' juga menambah kredit karena uangnya
    # langsung dianggap sampai di Pusat. Derivasi dari JournalLine.
    breakdown = finance_queries.reservation_cash_breakdown()
    for r in res_rows:
        bd = breakdown.get(r['id'])
        if not bd:
            continue
        num = r['reservation_number']
        paid = bd['terbayar_sby'] + bd['terbayar_jkt'] + bd['terbayar_direct']
        pool[num]['debit'] += paid
        pool[num]['credit'] += bd['terbayar_direct']
        direct_total += bd['terbayar_direct']

    for l in RemittanceLine.objects.values(
        linked_number=F('invoice_line__confirmation_letter__confirmation_number'),
    ).annotate(total=Sum('amount_sar')):
        pool[l['linked_number']]['credit'] += int(l['total'] or 0)
    # CL ikut jadi basis baris supaya reservasi yang belum punya invoice tetap terlacak
    cl_map = {
        c.confirmation_number: c
        for c in ConfirmationLetter.objects.with_parties().prefetch_related('rooms')
    }

    rows = []
    for linked_number in sorted(set(res_map) | set(cl_map) | set(pool)):
        data = pool.get(linked_number, {'debit': 0, 'credit': 0})
        res = res_map.get(linked_number, {})
        cl = cl_map.get(linked_number)
        status = (cl.reservation_status or '').upper() if cl else ''
        # Cancelled hanya relevan kalau uangnya terlanjur bergerak
        if status == 'CANCELLED' and not data['debit'] and not data['credit']:
            continue
        check_in = res.get('check_in') or (cl.check_in if cl else None)
        check_out = res.get('check_out') or (cl.check_out if cl else None)
        if date_from and check_in and check_in < date_from:
            continue
        if date_to and check_in and check_in > date_to:
            continue
        total_sar = int((cl.total_price if cl else 0) or 0)
        rows.append({
            'linked_number': linked_number or '—',
            'status': status,
            'hotel': res.get('hotel') or (cl.hotel_name if cl else '') or '—',
            'guest': (cl.guest_name if cl else '') or '—',
            'check_in': check_in,
            'check_out': check_out,
            'total_sar': total_sar,
            'debit': data['debit'],
            'credit': data['credit'],
            'balance': total_sar - data['credit'],
        })

    # urut check-in terdekat lebih dulu, baris tanpa check-in ditaruh paling bawah
    rows.sort(key=lambda r: (r['check_in'] is None, r['check_in'] or date.max, r['linked_number']))
    for i, row in enumerate(rows, start=1):
        row['no'] = i

    total_debit = sum(r['debit'] for r in rows)
    total_credit = sum(r['credit'] for r in rows)
    total_tagihan = sum(r['total_sar'] for r in rows)
    return {
        'rows': rows,
        'total_tagihan': total_tagihan,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance': total_tagihan - total_credit,
        'direct_total': direct_total,
    }


@require_perm('remittance', 'export')
def remittance_ledger_pdf(request):
    from .helpers import _parse_date, _render_list_pdf
    from .pdf import _logo_file_url

    date_from = _parse_date(request.GET.get('from', ''))
    date_to = _parse_date(request.GET.get('to', ''))
    ledger_rows = _build_ledger_rows(date_from, date_to)
    period = _period_label(date_from, date_to)

    return _render_list_pdf(
        request, Remittance.objects.none(),
        template='hw/remittance/remittance_ledger_pdf.html',
        filename='remittance_ledger_surabaya_pusat.pdf',
        extra_ctx={
            'period_label': period,
            'logo_url': _logo_file_url(),
            **ledger_rows,
        },
    )


@require_perm('remittance', 'export')
def remittance_period_pdf(request):
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url
    month = request.GET.get('month', '')
    if not month:
        return redirect('remittance_recap')
    try:
        from datetime import datetime
        period_dt = datetime.strptime(month, '%Y-%m')
    except ValueError:
        return redirect('remittance_recap')

    remittances = Remittance.objects.filter(
        date__year=period_dt.year,
        date__month=period_dt.month,
    ).prefetch_related('settlements__allocations').order_by('date')

    # Sama dengan tab Recap: diterima = nominal yang benar-benar masuk Pusat,
    # "pending" = yang masih di jalan (termasuk sisa transfer diterima sebagian).
    totals = _recap_totals(remittance_allocation.figures_for(remittances))
    total_sent = totals['total_sent']
    total_pending = totals['total_outstanding']
    total_received = totals['total_received']

    filename = f'remittance_recap_{month}.pdf'
    return _render_list_pdf(
        request, Remittance.objects.none(),
        template='hw/remittance/remittance_period_pdf.html',
        filename=filename,
        extra_ctx={
            'remittances': remittances,
            'period_label': period_dt.strftime('%B %Y'),
            'total_sent': total_sent,
            'total_pending': total_pending,
            'total_received': total_received,
            'logo_url': _logo_file_url(),
        },
    )
