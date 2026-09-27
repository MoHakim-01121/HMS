import logging
from datetime import date, datetime, time as dt_time

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import (
    ActivityLog, Client, ConfirmationLetter, Reservation, log_activity,
)
from ..permissions import require_perm
from ..finance import queries as finance_queries
from ..finance import posting
from ..finance_helpers import FinanceError
from .helpers import (
    _is_mobile,
    _parse_date,
    _to_float,
    money_account_choices,
    pagination_props,
    resolve_money_account,
    period_label as _period_label,
    snapshot_fields,
    track_changes,
    validate_proof_file,
)

logger = logging.getLogger(__name__)


@require_perm('clients', 'view')
def client_list(request):
    qs = Client.objects.all()

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(city__icontains=q) | Q(pic__icontains=q))

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)

    qs = qs.order_by('name')
    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Client is information only (no money figures): the one activity fact
    # shown is when this client last booked, taken from its latest CL.
    from django.db.models import Max
    from django.utils import timezone
    last_cl = dict(
        ConfirmationLetter.objects.filter(client_id__in=[c.pk for c in page_obj])
        .values('client_id').annotate(t=Max('created_at'))
        .values_list('client_id', 't')
    )

    def _days_since_booking(client_id):
        last = last_cl.get(client_id)
        return (timezone.now() - last).days if last else None

    rows = []
    for c in page_obj:
        rows.append({
            "id": c.pk,
            "name": c.name,
            "brand": c.brand,
            "city": c.city,
            "province": c.province,
            "pic": c.pic,
            "wa": c.wa,
            "wa_group": c.wa_group,
            "reminder_target": c.reminder_target,
            "days_since_last_order": _days_since_booking(c.pk),
            "is_active": c.is_active,
        })
    return inertia_render(request, "Client/List", props={
        "clients": rows, "q": q, "status": status,
        "total_count": paginator.count,
        "pagination": pagination_props(page_obj),
    })


def _validate_client(data):
    errors = {}
    if not data.get("name", "").strip():
        errors["name"] = "Agent name is required."
    return errors


def _client_echo(data):
    """Echo submitted values back to the form on validation error."""
    return {
        "name": data.get("name", ""), "brand": data.get("brand", ""),
        "city": data.get("city", ""),
        "province": data.get("province", ""), "address": data.get("address", ""),
        "pic": data.get("pic", ""),
        "wa": data.get("wa", ""), "wa_group": data.get("wa_group", ""),
        "reminder_target": data.get("reminder_target", "GROUP"), "email": data.get("email", ""),
        "note": data.get("note", ""), "lat": data.get("lat", ""),
        "lng": data.get("lng", ""), "is_active": data.get("is_active") == "on",
    }


@require_perm('clients', 'create')
def client_new(request):
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            return inertia_render(request, "Client/Form", props={
                "client": _client_echo(request.POST), "edit": False, "errors": errors,
            })
        c = Client()
        _save_client(c, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name)
        messages.success(request, f'Client "{c.name}" added successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={"client": None, "edit": False})


@require_perm('clients', 'edit')
def client_edit(request, pk):
    c = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            echo = _client_echo(request.POST); echo["id"] = c.pk
            return inertia_render(request, "Client/Form", props={
                "client": echo, "edit": True, "errors": errors,
            })
        _before = snapshot_fields(c, ['name', 'brand', 'city', 'province', 'address', 'pic', 'wa', 'email'])
        _save_client(c, request.POST)
        _after = snapshot_fields(c, ['name', 'brand', 'city', 'province', 'address', 'pic', 'wa', 'email'])
        changes = track_changes(
            _before, _after,
            labels={'name': 'Name', 'brand': 'Brand', 'city': 'City', 'province': 'Province', 'address': 'Address', 'pic': 'PIC', 'wa': 'WhatsApp', 'email': 'Email'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, changes)
        messages.success(request, f'Client "{c.name}" updated successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": {
            "id": c.pk, "name": c.name, "brand": c.brand, "city": c.city, "province": c.province,
            "address": c.address,
            "pic": c.pic, "wa": c.wa, "wa_group": c.wa_group, "reminder_target": c.reminder_target,
            "email": c.email, "note": c.note,
            "lat": c.lat, "lng": c.lng, "is_active": c.is_active,
        },
        "edit": True,
    })


@require_perm('clients', 'delete')
@require_POST
def client_delete(request, pk):
    c = get_object_or_404(Client, pk=pk)
    name = c.name
    try:
        c.delete()
    except Exception as exc:
        # JournalLine.client / PaymentRecord.client use PROTECT — a client with
        # financial history must never vanish from the ledger's perspective.
        from django.db.models.deletion import ProtectedError
        if isinstance(exc, ProtectedError):
            messages.error(
                request,
                f'Client "{name}" tidak bisa dihapus karena sudah tercatat di '
                'jurnal keuangan/pembayaran. Nonaktifkan saja (is_active=False).',
            )
            return redirect('client_detail', pk=pk)
        raise
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Client', name)
    messages.success(request, f'Client "{name}" deleted.')
    return redirect('client_list')


@require_perm('clients', 'view')
def client_detail(request, pk):
    """Client information only. Money (invoices, balances, fund activity,
    transfer/refund, statement) lives under Finance → Client Ledger."""
    from django.utils import timezone
    c = get_object_or_404(Client, pk=pk)
    cls = list(c.cls.order_by('-created_at'))
    cls_data = [{
        "pk": cl.pk,
        "confirmation_number": cl.confirmation_number,
        "guest_name": cl.guest_name,
        "hotel_name": cl.hotel_name,
        "check_in": cl.check_in.strftime("%d/%m/%Y") if cl.check_in else None,
    } for cl in cls]
    days_since_last_booking = (timezone.now() - cls[0].created_at).days if cls else None

    return inertia_render(request, "Client/Detail", props={
        "client": {
            "pk": c.pk,
            "name": c.name,
            "brand": c.brand,
            "city": c.city,
            "province": c.province,
            "address": c.address,
            "pic": c.pic,
            "wa": c.wa,
            "wa_group": c.wa_group,
            "reminder_target": c.reminder_target,
            "email": c.email,
            "note": c.note,
            "is_active": c.is_active,
            "days_since_last_order": days_since_last_booking,
        },
        "cls": cls_data,
    })


@require_perm('clients', 'view')
def client_map(request):
    qs = Client.objects.filter(lat__isnull=False, lng__isnull=False)
    return inertia_render(request, "Client/Map", props={"clients_count": qs.count()})


@require_perm('clients', 'view')
def client_map_data(request):
    qs = Client.objects.filter(lat__isnull=False, lng__isnull=False)

    data = [
        {
            'id': c.pk,
            'name': c.name,
            'brand': c.brand,
            'city': c.city,
            'province': c.province,
            'lat': c.lat,
            'lng': c.lng,
            'is_active': c.is_active,
            'url': reverse('client_detail', args=[c.pk]),
            'wa': c.wa,
            'pic': c.pic,
        }
        for c in qs
    ]
    return JsonResponse({'clients': data})


def _save_client(c, data):
    c.name      = data.get('name', '').strip()
    c.brand     = data.get('brand', '').strip()
    c.city      = data.get('city', '').strip()
    c.province  = data.get('province', '').strip()
    c.address   = data.get('address', '').strip()
    c.pic       = data.get('pic', '').strip()
    c.wa        = data.get('wa', '').strip()
    c.wa_group  = data.get('wa_group', '').strip()
    rt = data.get('reminder_target', '').strip()
    c.reminder_target = rt if rt in dict(Client.REMINDER_TARGET_CHOICES) else 'GROUP'
    c.email     = data.get('email', '').strip()
    c.note      = data.get('note', '').strip()
    c.is_active = data.get('is_active') == 'on'
    try: c.lat = float(data.get('lat') or 0) or None
    except (ValueError, TypeError): c.lat = None
    try: c.lng = float(data.get('lng') or 0) or None
    except (ValueError, TypeError): c.lng = None
    c.save()


def _client_reservation_options(client_obj):
    """Reservations for this client's from/to transfer pickers.

    Sourced from the journal's client+reservation dimensions via
    finance_queries.client_reservation_ids rather than Invoice.client/CL.client
    (frequently unpopulated) or the legacy Charge table (no longer written by
    the billing flow since the journal became the system of record).
    """
    reservation_ids = finance_queries.client_reservation_ids(client_obj.pk)
    reservations = Reservation.objects.filter(pk__in=reservation_ids).select_related('invoice').order_by('-check_in')
    return [{
        'id': r.id,
        'label': f'{r.reservation_number} — {r.invoice.invoice_number}',
        'piutang': finance_queries.piutang(r.id),
    } for r in reservations]


@require_perm('payments', 'edit')
def client_transfer(request, pk):
    client_obj = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        try:
            from_id = int(request.POST.get('from_reservation') or 0)
            to_id = int(request.POST.get('to_reservation') or 0)
        except (ValueError, TypeError):
            from_id = to_id = 0
        amount = int(round(_to_float(request.POST.get('amount_sar'))))
        note = (request.POST.get('note') or '').strip()

        errors = {}
        if not from_id or not to_id:
            errors['from_reservation'] = 'Choose both reservations.'
        elif from_id == to_id:
            errors['to_reservation'] = 'Choose a different reservation to move to.'
        if amount <= 0:
            errors['amount_sar'] = 'Enter an amount greater than zero.'

        # Scoped to this client's own reservations (sumber sama dengan
        # _client_reservation_options: dimensi jurnal client+reservation)
        # supaya id reservasi tamper-an milik client lain tidak ikut ter-tag
        # ke client ini.
        client_reservation_ids = finance_queries.client_reservation_ids(client_obj.pk)
        from_res = Reservation.objects.filter(pk=from_id).first() if from_id in client_reservation_ids else None
        to_res = Reservation.objects.filter(pk=to_id).first() if to_id in client_reservation_ids else None
        if from_id and not from_res:
            errors['from_reservation'] = 'Reservation not found.'
        if to_id and not to_res:
            errors['to_reservation'] = 'Reservation not found.'

        if not errors:
            # Journal (Fase 5+): piutang di-re-tag antar reservasi. Shadow
            # Allocation tidak lagi ditulis (Fase 7). Transfer berulang bisa
            # sah, jadi tidak ada idempotency_key; POST-redirect-GET + tombol
            # yang men-disable diri melindungi dari double-submit.
            try:
                posting.post_fund_transfer(
                    client_obj, from_reservation=from_res, to_reservation=to_res,
                    amount_sar=amount, created_by=request.user, entry_date=date.today(),
                )
            except FinanceError as e:
                errors['amount_sar'] = f'Jurnal gagal dicatat: {e}'
            else:
                logger.info(
                    "ledger: transfer %s SAR from reservation %s to %s (client %s)",
                    amount, from_res.reservation_number, to_res.reservation_number, client_obj.pk,
                )
                log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Fund Transfer', client_obj.name)
                messages.success(request, f'Moved {amount} SAR from {from_res.reservation_number} to {to_res.reservation_number}.')
                return redirect('client_finance_statement', pk=pk)

        return inertia_render(request, 'Finance/ClientTransfer', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': finance_queries.client_credit_balance(client_obj.id)},
            'reservations': _client_reservation_options(client_obj),
            'errors': errors,
            'initial': {'from_reservation': from_id or '', 'to_reservation': to_id or '', 'amount_sar': request.POST.get('amount_sar', ''), 'note': note},
        })

    return inertia_render(request, 'Finance/ClientTransfer', props={
        'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': finance_queries.client_credit_balance(client_obj.id)},
        'reservations': _client_reservation_options(client_obj),
    })


@require_perm('payments', 'edit')
def client_refund(request, pk):
    """Pay a client's fund back out of a concrete account.

    Two amounts: the SAR taken from the client's fund (journal) and what the
    account actually paid in its own currency (cash book). They are the same
    number for a SAR account; for an IDR/USD account both are entered."""
    client_obj = get_object_or_404(Client, pk=pk)
    accounts = money_account_choices()

    def page(errors=None, initial=None):
        return inertia_render(request, 'Finance/ClientRefund', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name, 'saldo_dana': finance_queries.client_credit_balance(client_obj.id)},
            'accounts': accounts,
            'errors': errors or {},
            'initial': initial or {},
        })

    if request.method != 'POST':
        return page()

    P = request.POST
    bank, cash = resolve_money_account(P.get('from_account'))
    account = bank or cash
    amount = int(round(_to_float(P.get('amount_sar'))))
    note = (P.get('note') or '').strip()
    proof = request.FILES.get('proof')

    errors = {}
    if account is None:
        errors['from_account'] = 'Choose the account the refund is paid from.'
    if amount <= 0:
        errors['amount_sar'] = 'Enter an amount greater than zero.'
    paid = amount
    if account is not None and account.currency != 'SAR':
        paid = int(round(_to_float(P.get('amount_paid'))))
        if paid <= 0:
            errors['amount_paid'] = f'Enter the amount paid in {account.currency}.'
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            errors['proof'] = proof_error

    if not errors:
        # Journal: DR Titipan / CR Kas cabang rekening. Cash book: the real
        # amount out of that account. Refund berulang bisa sah → tanpa
        # idempotency_key; PRG + tombol disable melindungi dari double-submit.
        from ..finance.bank_ledger import record_bank_transaction
        try:
            with transaction.atomic():
                entry = posting.post_refund(
                    client_obj, from_location=account.branch_id, amount_sar=amount,
                    created_by=request.user, entry_date=date.today(), proof=proof,
                )
                record_bank_transaction(
                    account=account, direction='out', amount_sar=amount,
                    currency=account.currency, amount=paid, source_type='Refund', source_id=entry.pk,
                    transaction_date=entry.entry_date, reference=note[:200],
                )
        except FinanceError as e:
            errors['amount_sar'] = f'Jurnal gagal dicatat: {e}'
        else:
            logger.info("ledger: refund %s SAR (%s %s) to client %s from %s",
                        amount, paid, account.currency, client_obj.pk, account)
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Refund', client_obj.name)
            messages.success(request, f'Refunded {amount} SAR to {client_obj.name}.')
            return redirect('client_finance_statement', pk=pk)

    return page(errors, {
        'from_account': P.get('from_account', ''), 'amount_sar': P.get('amount_sar', ''),
        'amount_paid': P.get('amount_paid', ''), 'note': note,
    })


@require_perm('statements', 'export')
def client_statement_pdf(request, pk):
    """Full customer statement (rekening koran), bitemporal via `as_of`.

    `from`/`to` scope which events show; `as_of` (also a date, taken as
    end-of-day) locks out anything recorded after that point so a reprint of
    a past period always reproduces identical numbers -- see
    hw/ledger.py::client_statement. Rows before `from` aren't dropped, just
    folded into a single opening-balance line computed with the same
    `as_of`, so the closing balance always reconciles with a full statement.
    """
    from django.utils import timezone as dj_timezone

    from .helpers import _render_list_pdf
    from .pdf import _logo_file_url

    c = get_object_or_404(Client, pk=pk)

    mode = request.GET.get('mode', 'balance')
    if mode not in ('balance', 'open', 'byres'):
        mode = 'balance'

    date_from = _parse_date(request.GET.get('from', ''))
    date_to = _parse_date(request.GET.get('to', ''))
    as_of_date = _parse_date(request.GET.get('as_of', ''))
    as_of = dj_timezone.make_aware(datetime.combine(as_of_date, dt_time.max)) if as_of_date else None

    period_label = _period_label(date_from, date_to)

    if mode == 'open':
        open_items = finance_queries.open_items(c.id, date_to=date_to, as_of=as_of)
        return _render_list_pdf(
            request, Client.objects.none(),
            template='hw/client/client_open_items_pdf.html',
            filename=f'open_items_{c.name}_{date.today()}.pdf'.replace(' ', '_'),
            extra_ctx={
                'client': c,
                'open_items': open_items['rows'],
                'total_open': open_items['total_remaining'],
                'period_label': period_label,
                'logo_url': _logo_file_url(),
            },
        )

    if mode == 'byres':
        st = finance_queries.client_statement_by_reservation(
            c.id, date_from=date_from, date_to=date_to, as_of=as_of,
        )
        # This statement is client-facing and English-only, so it does not reuse
        # the Indonesian `_period_label` helper shared by the internal views.
        if date_from and date_to:
            period_en = f"{date_from:%d %b %Y} – {date_to:%d %b %Y}"
        elif date_from:
            period_en = f"From {date_from:%d %b %Y}"
        elif date_to:
            period_en = f"To {date_to:%d %b %Y}"
        else:
            period_en = "All transactions to date"
        reservations = [{
            'no': i,
            'reservation_number': g['reservation_number'],
            'hotel': g['hotel'],
            'check_in': g['check_in'].strftime('%d/%m/%Y') if g['check_in'] else '—',
            'debit': g['billed'],
            'credit': g['paid'],
            'balance': g['balance'],
            'settled': g['settled'],
        } for i, g in enumerate(st['reservations'], start=1)]
        # Subtotal of the per-reservation columns only. `total_debit`/`total_credit`
        # from the query sweep in `unallocated` lines too, so they would not tie
        # out to the sum of what is printed in these columns.
        subtotal_debit = sum(r['debit'] for r in reservations)
        subtotal_credit = sum(r['credit'] for r in reservations)
        return _render_list_pdf(
            request, Client.objects.none(),
            template='hw/client/client_statement_byres_pdf.html',
            filename=f'statement_{c.name}_{date.today()}.pdf'.replace(' ', '_'),
            extra_ctx={
                'client': c,
                'reservations': reservations,
                'subtotal_debit': subtotal_debit,
                'subtotal_credit': subtotal_credit,
                'subtotal_balance': subtotal_debit - subtotal_credit,
                'unallocated_debits': st['unallocated_debits'],
                'unallocated_credits': st['unallocated_credits'],
                'opening_balance': st['opening_balance'],
                'closing_balance': st['closing_balance'],
                'period_label': period_en,
                'logo_url': _logo_file_url(),
            },
        )

    statement = finance_queries.client_statement_with_opening(c.id, date_from=date_from, date_to=date_to, as_of=as_of)
    opening_balance = statement['opening_balance']
    closing_balance = statement['closing_balance']
    total_debit = statement['total_debit']
    total_credit = statement['total_credit']
    formatted_rows = [{
        'date': r['date'].strftime('%d/%m/%Y') if r['date'] else '—',
        'type': r['type'],
        'description': r['description'],
        'invoice_number': r['invoice_number'],
        'debit': r['debit'],
        'credit': r['credit'],
        'balance': r['balance'],
    } for r in statement['rows']]

    return _render_list_pdf(
        request, Client.objects.none(),
        template='hw/client/client_statement_pdf.html',
        filename=f'statement_{c.name}_{date.today()}.pdf'.replace(' ', '_'),
        extra_ctx={
            'client': c,
            'rows': formatted_rows,
            'period_label': period_label,
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'logo_url': _logo_file_url(),
        },
    )
