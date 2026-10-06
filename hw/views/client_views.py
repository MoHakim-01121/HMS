import logging
from datetime import date, datetime, time as dt_time

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from inertia import render as inertia_render

from ..models import (
    ActivityLog, Client, ConfirmationLetter, log_activity,
)
from ..permissions import require_perm
from ..finance import queries as finance_queries
from ..finance_helpers import FinanceError
from ..utils import round_half_up
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


def _branch_choices():
    from ..models.branch import Branch
    return [{"value": b.code, "label": b.name} for b in Branch.objects.filter(is_active=True).order_by("name")]


def _validate_client(data, instance=None):
    from ..models.branch import Branch
    from ..models.client import DEFAULT_OWNER_BRANCH, client_name_key
    errors = {}
    name = data.get("name", "").strip()
    if not name:
        errors["name"] = "Agent name is required."
    else:
        # Satu perusahaan satu baris: "PT. Safaar" dan "SAFAAR" dianggap sama.
        clash = Client.objects.filter(name_key=client_name_key(name))
        if instance is not None and instance.pk:
            clash = clash.exclude(pk=instance.pk)
        other = clash.first()
        if other:
            errors["name"] = f'A client named "{other.name}" already exists.'
    branch = (data.get("owner_branch") or DEFAULT_OWNER_BRANCH).strip()
    if not Branch.objects.filter(code=branch, is_active=True).exists():
        errors["owner_branch"] = "Choose the branch that owns this client."
    return errors


def _client_echo(data):
    """Echo submitted values back to the form on validation error."""
    return {
        "name": data.get("name", ""), "brand": data.get("brand", ""),
        "owner_branch": data.get("owner_branch", ""),
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
                "branch_choices": _branch_choices(),
            })
        c = Client()
        _save_client(c, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name)
        messages.success(request, f'Client "{c.name}" added successfully.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": None, "edit": False, "branch_choices": _branch_choices(),
    })


@require_perm('clients', 'edit')
def client_edit(request, pk):
    c = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        errors = _validate_client(request.POST, instance=c)
        if errors:
            echo = _client_echo(request.POST); echo["id"] = c.pk
            return inertia_render(request, "Client/Form", props={
                "client": echo, "edit": True, "errors": errors,
                "branch_choices": _branch_choices(),
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
            "owner_branch": c.owner_branch_id,
            "address": c.address,
            "pic": c.pic, "wa": c.wa, "wa_group": c.wa_group, "reminder_target": c.reminder_target,
            "email": c.email, "note": c.note,
            "lat": c.lat, "lng": c.lng, "is_active": c.is_active,
        },
        "edit": True,
        "branch_choices": _branch_choices(),
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
    branch = (data.get('owner_branch') or '').strip()
    if branch:
        c.owner_branch_id = branch
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
    account = resolve_money_account(P.get('from_account'))
    amount = round_half_up(_to_float(P.get('amount_sar')))
    note = (P.get('note') or '').strip()
    proof = request.FILES.get('proof')

    errors = {}
    if account is None:
        errors['from_account'] = 'Choose the account the refund is paid from.'
    if amount <= 0:
        errors['amount_sar'] = 'Enter an amount greater than zero.'
    paid = amount
    if account is not None and account.currency != 'SAR':
        paid = round_half_up(_to_float(P.get('amount_paid')))
        if paid <= 0:
            errors['amount_paid'] = f'Enter the amount paid in {account.currency}.'
    if proof:
        proof_error = validate_proof_file(proof)
        if proof_error:
            errors['proof'] = proof_error

    if not errors:
        # A numbered refund document, pending: another user approves it and
        # only then is the journal (DR Titipan / CR the account) and the
        # cash-book movement posted. Only the client's deposit can be refunded
        # (checked now and again on approval). Repeated refunds are legal →
        # no idempotency key; PRG + a disabled button guard double submits.
        from ..finance.deposit import request_refund
        try:
            refund = request_refund(
                client_obj, account=account, amount_sar=amount, amount_paid=paid,
                refund_date=date.today(), created_by=request.user, note=note, proof=proof,
            )
        except FinanceError as e:
            errors['amount_sar'] = str(e)
        else:
            logger.info("ledger: refund %s SAR (%s %s) to client %s from %s",
                        amount, paid, account.currency, client_obj.pk, account)
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Refund', client_obj.name)
            messages.success(request, f'Refund {refund.refund_number}: {amount} SAR to {client_obj.name} — menunggu persetujuan user lain.')
            return redirect('client_finance_statement', pk=pk)

    return page(errors, {
        'from_account': P.get('from_account', ''), 'amount_sar': P.get('amount_sar', ''),
        'amount_paid': P.get('amount_paid', ''), 'note': note,
    })


@require_perm('payments', 'edit')
def client_deposit_transfer(request, pk):
    """Move part of a client's deposit to another client (a numbered document)."""
    from ..finance.deposit import request_transfer
    client_obj = get_object_or_404(Client, pk=pk)

    def page(errors=None, initial=None):
        return inertia_render(request, 'Finance/DepositTransfer', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name,
                       'saldo_dana': finance_queries.client_credit_balance(client_obj.id)},
            'clients': [{'id': c.pk, 'name': c.name} for c in Client.objects.filter(is_active=True)
                        .exclude(pk=client_obj.pk).order_by('name')],
            'errors': errors or {},
            'initial': initial or {},
        })

    if request.method != 'POST':
        return page()
    P = request.POST
    note = (P.get('note') or '').strip()
    amount = round_half_up(_to_float(P.get('amount_sar')))
    to_client = Client.objects.filter(pk=P.get('to_client') or 0).exclude(pk=client_obj.pk).first()
    errors = {}
    if to_client is None:
        errors['to_client'] = 'Choose the client that receives the deposit.'
    if amount <= 0:
        errors['amount_sar'] = 'Enter an amount greater than zero.'
    if not errors:
        try:
            transfer = request_transfer(client_obj, to_client, amount_sar=amount, transfer_date=date.today(),
                                        created_by=request.user, note=note)
        except FinanceError as e:
            errors['amount_sar'] = str(e)
        else:
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Deposit Transfer', transfer.transfer_number)
            messages.success(request, f'{transfer.transfer_number}: {amount} SAR to {to_client.name} — menunggu persetujuan user lain.')
            return redirect('client_finance_statement', pk=pk)
    return page(errors, {'to_client': P.get('to_client', ''), 'amount_sar': P.get('amount_sar', ''), 'note': note})


def _decide_deposit_out(request, kind, pk, decision):
    """Setujui / tolak refund atau transfer deposit yang pending (POST)."""
    from ..finance import deposit
    from ..models import ClientRefund, ClientTransfer
    model = ClientRefund if kind == 'refund' else ClientTransfer
    doc = get_object_or_404(model, pk=pk)
    client_pk = doc.client_id if kind == 'refund' else doc.from_client_id
    if request.method != 'POST':
        return redirect('client_finance_statement', pk=client_pk)
    number = doc.refund_number if kind == 'refund' else doc.transfer_number
    try:
        if decision == 'confirm':
            (deposit.confirm_refund if kind == 'refund' else deposit.confirm_transfer)(doc, confirmed_by=request.user)
        else:
            (deposit.reject_refund if kind == 'refund' else deposit.reject_transfer)(
                doc, rejected_by=request.user, reason=request.POST.get('reason', ''),
            )
    except FinanceError as e:
        messages.error(request, str(e))
    else:
        log_activity(request.user, ActivityLog.ACTION_EDIT,
                     'Client Refund' if kind == 'refund' else 'Client Deposit Transfer', f'{number} {decision}')
        messages.success(request, f'{number} {"disetujui" if decision == "confirm" else "ditolak"}.')
    return redirect('client_finance_statement', pk=client_pk)


@require_perm('payments', 'delete')
def client_refund_confirm(request, pk):
    return _decide_deposit_out(request, 'refund', pk, 'confirm')


@require_perm('payments', 'delete')
def client_refund_reject(request, pk):
    return _decide_deposit_out(request, 'refund', pk, 'reject')


@require_perm('payments', 'delete')
def client_deposit_transfer_confirm(request, pk):
    return _decide_deposit_out(request, 'transfer', pk, 'confirm')


@require_perm('payments', 'delete')
def client_deposit_transfer_reject(request, pk):
    return _decide_deposit_out(request, 'transfer', pk, 'reject')


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
