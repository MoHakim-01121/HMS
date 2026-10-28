import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, in_scope, scope
from ..finance import fund_flow, posting, remittance_allocation
from ..finance_helpers import FinanceError
from ..i18n import tr
from ..models import Remittance, RemittanceLine, RemittancePlanLine
from ..permissions import require_perm
from .helpers import csv_export_response, pagination_props, validate_proof_file
from .helpers import period_label as _period_label

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


def _plan_from_query(raw):
    """`?plan=12:1500,14:800` dari tab Tracking → [{invoice_line_id, amount_sar}]."""
    items = []
    for part in (raw or '').split(','):
        line_id, _, amount = part.partition(':')
        if line_id.strip().isdigit() and amount.strip().isdigit():
            items.append({'invoice_line_id': int(line_id), 'amount_sar': int(amount)})
    return items


def _plan_from_post(raw):
    import json
    try:
        items = json.loads(raw) if raw else []
    except ValueError:
        raise FinanceError('Format rencana tidak valid') from None
    if not isinstance(items, list):
        raise FinanceError('Format rencana tidak valid')
    return items


def _plan_props(items, *, strict):
    """Baris rencana untuk form. Dari Tracking (`strict=False`) nominal dipangkas
    ke yang masih bisa direncanakan; saat simpan gagal, apa adanya."""
    from ..models import Invoice
    rows = remittance_allocation.plannable_rows()
    # Nama klien seperti di tab Tracking, bukan nama customer di invoice.
    client_names = dict(
        Invoice.objects.filter(pk__in={r['invoice_id'] for r in rows.values() if r['invoice_id']})
        .values_list('pk', 'client__name')
    )
    out = []
    for item in items:
        try:
            line_id, amount = int(item['invoice_line_id']), int(item['amount_sar'])
        except (KeyError, TypeError, ValueError):
            continue
        row = rows.get(line_id)
        if row is None:
            continue
        if not strict:
            amount = min(amount, row['plannable'])
        out.append({
            'invoice_line_id': line_id,
            'linked_number': row['linked_number'],
            'client_name': client_names.get(row['invoice_id']) or row['customer_name'] or '',
            'hotel': row['hotel'] or '',
            'check_in': row['check_in'].strftime('%d/%m/%Y') if row['check_in'] else None,
            'amount_sar': amount,
            'plannable': row['plannable'],
        })
    return out


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
        'fx_unpriced': fx['unpriced'],
        'fx_priced': len(fx['transfers']) - fx['unpriced'],
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


# The remittance figures (obligation to send, FX profit, tracking, ledger) are
# built for Surabaya -> head office, today's only operating branch. Only a user
# covering Surabaya sees them; a branch without its own figures yet sees none.
REMITTING_BRANCH = 'sby'


def _sees_remittance_figures(user):
    return in_scope(user, REMITTING_BRANCH)


def _remittances(request):
    """Transfers sent from the user's branches' accounts."""
    return scope(Remittance.objects.all(), request.user)


def _can_record_receipt(rem):
    """Record Receipt terbuka selama Pusat belum menerima penuh -- aturan yang
    sama ditegakkan di settlement_service.add_settlement."""
    return rem.status == Remittance.STATUS_PENDING


@require_perm('remittance', 'view')
def remittance_list(request):
    """Remittance list (Record View HMS canvas): what was sent to HQ in the
    month (IDR, and SAR at the book), cash in transit, what is still due to HQ
    and the FX gain; the table shows IDR sent against SAR received. The
    Tracking and Recap views stay as tabs."""
    from django.db.models import Q

    from ..finance import fund_flow
    from ..finance import queries as finance_queries
    from .helpers import csv_list, list_per_page, list_period, pct_delta, prev_month_range
    tab = request.GET.get('tab', '')
    if tab not in ('tracking', 'recap'):
        tab = 'transfers'
    sees = _sees_remittance_figures(request.user)
    q = request.GET.get('q', '').strip()
    statuses = csv_list(request, 'status', ['transit', 'partial', 'received'])
    accounts = csv_list(request, 'acct')
    date_from, date_to, period = list_period(request)
    today = timezone.localdate()

    rows, kpis, counts, account_counts, page_obj, totals = [], None, {}, [], None, None
    if tab == 'transfers':
        qs = _remittances(request).select_related('from_account', 'to_account').prefetch_related('settlements').order_by('-date', '-pk')
        if q:
            qs = qs.filter(Q(remittance_number__icontains=q) | Q(receipt_reference__icontains=q) | Q(note__icontains=q))
        in_transit_only = statuses == ['transit'] or set(statuses) == {'transit', 'partial'}
        period_qs = qs if in_transit_only else qs.filter(**{k: v for k, v in (('date__gte', date_from), ('date__lte', date_to)) if v})
        figs = remittance_allocation.figures_for(list(period_qs))
        fx = {t['id']: t for t in fund_flow.fx_profit(branch='sby')['transfers']} if sees else {}
        state_key = {'pending': 'transit', 'partial': 'partial', 'received': 'received'}
        counts = {k: 0 for k in ('transit', 'partial', 'received')}
        acc_n = {}
        for rem, fig in figs:
            counts[state_key[fig['state']]] += 1
            acc_n[str(rem.from_account)] = acc_n.get(str(rem.from_account), 0) + 1
        account_counts = [{'name': k, 'count': v} for k, v in sorted(acc_n.items())]
        chosen = [(r, f) for r, f in figs
                  if (not statuses or state_key[f['state']] in statuses) and (not accounts or str(r.from_account) in accounts)]
        page_obj = Paginator(chosen, list_per_page(request)).get_page(request.GET.get('page'))
        for rem, fig in page_obj:
            t = fx.get(rem.pk) or {}
            rows.append({
                'id': rem.pk, 'remittance_number': rem.remittance_number, 'date': rem.date.isoformat(),
                'from': str(rem.from_account), 'to': str(rem.to_account),
                'currency': rem.from_account.currency, 'amount_sent': rem.amount_sent,
                'received_sar': fig['received'], 'outstanding_sar': fig['outstanding'],
                'rate': float(rem.exchange_rate), 'fx_gain_idr': t.get('profit_idr'),
                'state': fig['state'], 'days': (today - rem.date).days,
                'proof_url': rem.proof.url if rem.proof else None, 'can_record_receipt': _can_record_receipt(rem),
            })
        if period['month'] or period['year'] not in ('', 'all') or (date_from and date_to):
            month_figs = [(r, f) for r, f in figs]
            totals = {
                'idr': sum(r.amount_sent for r, f in month_figs if r.from_account.currency == 'IDR'),
                'received_sar': sum(f['received'] for r, f in month_figs),
                'transit_sar': sum(f['outstanding'] for r, f in month_figs),
                'fx_gain_idr': sum((fx.get(r.pk) or {}).get('profit_idr') or 0 for r, f in month_figs),
            }
            idr_rows = [r for r, f in month_figs if r.from_account.currency == 'IDR']
            sar_eq = sum(r.amount_sent / float(r.exchange_rate) for r in idr_rows if r.exchange_rate)
            totals['avg_rate'] = round(totals['idr'] / sar_eq) if sar_eq else None
        if period['month'] and sees:
            pf, pl = prev_month_range(date_from)
            sent_sar = lambda rs: round(sum(r.amount_sent / float(r.exchange_rate) for r in rs if r.exchange_rate))
            cur_rs = list(_remittances(request).filter(date__gte=date_from, date__lte=date_to).select_related('from_account'))
            prev_rs = list(_remittances(request).filter(date__gte=pf, date__lte=pl))
            prev_fx = sum(t['profit_idr'] or 0 for t in fund_flow.fx_profit(branch='sby', date_from=pf, date_to=pl)['transfers'])
            cur_fx = fund_flow.fx_profit(branch='sby', date_from=date_from, date_to=date_to)['transfers']
            transit = [(r, f) for r, f in remittance_allocation.figures_for(list(_remittances(request).prefetch_related('settlements'))) if f['outstanding'] > 0]
            pool = fund_flow.idr_pool('sby')
            send_rates = [t['send_rate'] for t in cur_fx if t['send_rate']]
            kpis = {
                'idr': sum(r.amount_sent for r in cur_rs if r.from_account.currency == 'IDR'),
                'sar': sent_sar(cur_rs), 'prev_sar': sent_sar(prev_rs), 'prev_month': pf.strftime('%Y-%m'),
                'delta': pct_delta(sent_sar(cur_rs), sent_sar(prev_rs)),
                'transit_sar': sum(f['outstanding'] for r, f in transit), 'transit_count': len(transit),
                'transit_oldest': max(((today - r.date).days for r, f in transit), default=0),
                'due_to_hq': finance_queries.kewajiban_kirim_sby(),
                'fx_gain': sum(t['profit_idr'] or 0 for t in cur_fx), 'fx_delta': pct_delta(sum(t['profit_idr'] or 0 for t in cur_fx), prev_fx),
                'avg_send_rate': round(sum(send_rates) / len(send_rates)) if send_rates else None,
                'book_rate': round(pool['rate']) if pool['rate'] else None,
            }

    years = sorted({d.year for d in _remittances(request).dates('date', 'year')} | {today.year})
    return inertia_render(request, "Remittance/List", props={
        "tab": tab,
        "remittances": rows,
        "filters": {"q": q, "status": statuses, "acct": accounts, "per": list_per_page(request), **period},
        "years": years, "counts": counts, "account_counts": account_counts,
        "kpis": kpis, "totals": totals, "sees_figures": sees,
        "pagination": pagination_props(page_obj) if page_obj else None,
        "tracking": _compute_tracking_data() if tab == 'tracking' and sees else None,
        "monthly": _compute_recap_data(request) if tab == 'recap' else None,
    })


@require_perm('remittance', 'create')
@transaction.atomic
def remittance_new(request):
    """Transfer baru = lump-sum: uang IDR keluar dari bank Surabaya dengan kurs
    tertentu. Tidak memilih reservasi -- alokasi ke reservasi dilakukan saat
    Pusat mencatat penerimaan (hw/finance/remittance_allocation.py), karena
    baru saat itu jelas uang siapa yang didahulukan."""
    from ..models.bank import BankAccount
    if not _sees_remittance_figures(request.user):
        raise Http404  # the form shows Surabaya's rupiah pool and open transfers
    # Transfers leave an IDR bank account of the user's branch (never HQ's own).
    from_accounts = list(
        scope(BankAccount.objects.filter(is_active=True, currency='IDR'), request.user)
        .exclude(branch__is_hq=True).select_related('branch').order_by('bank_name', 'account_identifier')
    )

    from ..finance.bank_ledger import default_account
    from ..models.bank import MoneyAccount
    hq_default = default_account('pusat', 'SAR')
    to_accounts = list(
        MoneyAccount.objects.filter(is_active=True, currency='SAR', branch__is_hq=True)
        .exclude(kind=MoneyAccount.KIND_STAFF).order_by('kind', 'bank_name', 'name')
    )

    def form_page(error=None, plan=None):
        if plan is None:
            plan = _plan_props(_plan_from_query(request.GET.get('plan')), strict=False)
        return inertia_render(request, "Remittance/Form", props={
            # Reservasi yang dipilih di tab Tracking untuk transfer ini.
            'plan': plan,
            'open_transfers': remittance_allocation.open_transfers(),
            'error': error,
            'today': str(timezone.localdate()),
            # Uang client rupiah yang belum disetor + kurs asalnya (laba kurs di form).
            'fx_pool': fund_flow.idr_pool('sby'),
            'from_accounts': [{
                'value': str(a.pk),
                'label': f"{a.bank_name} {a.account_identifier} · {a.branch.name}".strip(),
                'name': str(a), 'number': a.account_identifier,
            } for a in from_accounts],
            'to_accounts': [{'value': str(a.pk), 'label': str(a), 'number': a.account_identifier,
                             'is_default': hq_default is not None and a.pk == hq_default.pk} for a in to_accounts],
        })

    if request.method != 'POST':
        return form_page()

    try:
        plan_items = _plan_from_post(request.POST.get('plan'))
    except FinanceError as e:
        return form_page(str(e), plan=[])
    posted_plan = _plan_props(plan_items, strict=True)

    def form_page_with_plan(error):
        return form_page(error, plan=posted_plan)

    remittance_date = request.POST.get('date') or str(timezone.localdate())
    receipt_reference = request.POST.get('receipt_reference', '').strip()
    note = request.POST.get('note', '').strip()
    proof = request.FILES.get('proof')
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            return form_page_with_plan(proof_error)

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
        return form_page_with_plan('Enter the IDR amount and exchange rate.')
    from_account = next((a for a in from_accounts if str(a.pk) == request.POST.get('from_bank_account')), None)
    if from_account is None:
        return form_page_with_plan('Choose the IDR bank account the money left from.'
                         if from_accounts else 'Add an IDR bank account in Bank Balances first.')

    to_account = next((a for a in to_accounts if str(a.pk) == request.POST.get('to_account')), None) or hq_default
    if to_account is None:
        return form_page_with_plan('Add an HQ SAR account in Bank Balances first.')
    # The transfer, its cash book row (the rupiah that left the branch account)
    # and its send journal (SBY -> Transit, not yet any reservation's money)
    # are one fact: when the account does not hold the rupiah or the period is
    # closed, nothing is saved and the form says why.
    from ..finance.bank_ledger import record_bank_transaction
    try:
        remittance_date = date.fromisoformat(remittance_date)
    except ValueError:
        return form_page_with_plan('Tanggal transfer tidak valid.')
    try:
        with transaction.atomic():
            plan = remittance_allocation.validate_plan(plan_items)
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
            record_bank_transaction(
                account=from_account, direction='out', amount_sar=rem.expected_sar,
                currency='IDR', amount=amount_idr, source_type='Remittance', source_id=rem.pk,
                transaction_date=rem.date, reference=receipt_reference,
            )
            if proof:
                rem.proof = proof
                rem.save()
            RemittancePlanLine.objects.bulk_create([
                RemittancePlanLine(remittance=rem, invoice_line_id=row['reservation_id'], amount_sar=amount)
                for row, amount in plan
            ])
            posting.resync_remittance(rem, created_by=request.user)
    except FinanceError as e:
        return form_page_with_plan(f'Tidak tersimpan: {e}')

    return redirect('remittance_detail', pk=rem.pk)


@require_perm('remittance', 'view')
def remittance_detail(request, pk):
    from ..models import Reservation
    rem = get_in_scope_or_404(Remittance.objects.select_related('from_account', 'to_account'), request.user, pk=pk)

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
    remittances = _remittances(request).prefetch_related(
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
    rem = get_in_scope_or_404(Remittance.objects.all(), request.user, pk=pk)
    if request.method == 'POST':
        proof = None if request.POST.get('remove_proof') else request.FILES.get('proof')
        proof_error = validate_proof_file(proof) if proof else None
        if proof_error:
            return _remittance_edit_page(request, rem, f'Bukti transfer: {proof_error}')
        if request.POST.get('date'):
            try:
                rem.date = date.fromisoformat(request.POST['date'])
            except ValueError:
                return _remittance_edit_page(request, rem, 'Tanggal transfer tidak valid.')
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
        elif proof:
            rem.proof = proof
            update_fields.append('proof')

        # The transfer, its cash book row and the journal's send leg are one
        # fact: when the ledger cannot follow (e.g. a closed period), nothing
        # is saved, rather than leaving the document and the books apart.
        from ..finance.bank_ledger import sync_bank_transaction
        try:
            with transaction.atomic():
                rem.save(update_fields=update_fields)
                sync_bank_transaction(
                    account=rem.from_account, direction='out', amount_sar=rem.expected_sar,
                    currency=rem.from_account.currency, amount=rem.amount_sent, source_type='Remittance',
                    source_id=rem.pk, transaction_date=rem.date, reference=rem.receipt_reference,
                )
                posting.resync_remittance(rem, created_by=request.user)
        except FinanceError as e:
            logger.warning("remittance %s: edit refused, ledger cannot follow: %s", rem.remittance_number, e)
            rem.refresh_from_db()
            return _remittance_edit_page(request, rem, f'Tidak tersimpan — buku kas/jurnal tidak bisa ikut berubah: {e}')
        return redirect('remittance_detail', pk=rem.pk)

    return _remittance_edit_page(request, rem)


def _remittance_edit_page(request, rem, error=None):
    """The edit form. A rejected save (`error`) echoes the POST, so the user
    keeps what they typed; the proof file has to be picked again."""
    # Allocations are made per receipt (Record Receipt / change allocation).
    lines_editable = False
    lines = []
    props = {
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
        "error": error,
    }
    if error:
        props["rem"].update({k: request.POST.get(k, '') for k in (
            'date', 'receipt_reference', 'note', 'amount_idr', 'exchange_rate', 'original_amount') if k in request.POST})
    return inertia_render(request, "Remittance/Edit", props=props)




@require_perm('remittance', 'export')
def remittance_pdf(request, pk):
    from ..models import Reservation
    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url
    rem = get_in_scope_or_404(Remittance.objects.all(), request.user, pk=pk)
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
    rem = get_in_scope_or_404(Remittance.objects.all(), request.user, pk=pk)
    proof = request.FILES.get('proof')
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            messages.error(request, tr(request, f'Transfer proof: {proof_error}', f'Bukti transfer: {proof_error}'))
            return redirect('remittance_detail', pk=rem.pk)
        rem.proof = proof
        rem.save(update_fields=['proof'])
    return redirect('remittance_detail', pk=rem.pk)


@require_perm('remittance', 'delete')
@require_POST
def remittance_delete(request, pk):
    rem = get_in_scope_or_404(Remittance.objects.all(), request.user, pk=pk)
    # System of record (Fase 7): jurnal REMITTANCE hidup merepresentasikan
    # perpindahan kas SBY->PUSAT. Remittance yang sudah menyentuh jurnal --
    # langsung atau lewat baris -- tidak boleh hilang diam-diam.
    from ..finance import queries as finance_queries
    # Entry yang sudah dibalik pun tetap menunjuk transfer ini sebagai sumbernya.
    if (rem.settlements.exists() or rem.journal_entries.exists()
            or finance_queries.remittance_has_live_entries(rem.pk)):
        messages.error(request, tr(request, f'Remittance {rem.remittance_number} is in the financial ledger and cannot be deleted.', f'Remittance {rem.remittance_number} tidak bisa dihapus karena sudah tercatat di ledger keuangan.'))
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
    messages.success(request, tr(request, f'Remittance {rem.remittance_number} deleted.', f'Remittance {rem.remittance_number} dihapus.'))
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


def _compute_recap_data(request):
    """Rangkuman remittance per bulan transfer (tab Recap).

    "Diterima" = nominal yang benar-benar masuk Kas Pusat
    (remittance_allocation.transfer_figures), bukan nominal kirim transfer yang
    berstatus received. Penerimaan dihitung di bulan transfernya, bukan bulan
    diterima."""
    remittances = (
        _remittances(request).prefetch_related('settlements__allocations').order_by('-date', '-created_at')
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
    from ..finance import queries as finance_queries
    from ..models import Invoice
    from ..models.settlement import RemittanceSettlement

    today = timezone.localdate()
    rows = remittance_allocation.build_reservasi_mengendap()
    history = finance_queries.reservation_remittance_map([r['linked_number'] for r in rows])
    client_names = dict(
        Invoice.objects.filter(pk__in={r['invoice_id'] for r in rows if r['invoice_id']})
        .values_list('pk', 'client__name')
    )

    plans = remittance_allocation.open_plans()

    reservations = []
    client_unallocated = 0
    for r in rows:
        unallocated = max(int(r['mengendap']), 0)
        events = history.get(r['linked_number'], [])
        if not unallocated and not events and not r['terbayar_total']:
            continue
        client_unallocated += unallocated
        planned = plans.get(r['reservation_id'], [])
        planned_sar = min(sum(p['amount_sar'] for p in planned), unallocated)
        reservations.append({
            'invoice_line_id': r['reservation_id'],
            # Sudah ikut rencana transfer yang belum tuntas; sisanya perlu disetor.
            'planned': [{'rmt_id': p['remittance_id'], 'rmt_number': p['remittance_number'], 'amount_sar': p['amount_sar']}
                        for p in planned],
            'to_send': unallocated - planned_sar,
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
    from ..finance import queries as finance_queries
    from ..models import ConfirmationLetter, Reservation

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
    if not _sees_remittance_figures(request.user):
        raise Http404

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

    remittances = _remittances(request).filter(
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
