import logging
import re
from datetime import date, datetime
from datetime import time as dt_time

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, scope, with_head_office
from ..finance import queries as finance_queries
from ..finance_helpers import FinanceError
from ..i18n import tr
from ..models import (
    ActivityLog,
    Client,
    ConfirmationLetter,
    log_activity,
)
from ..permissions import require_perm
from ..utils import round_half_up
from .helpers import (
    _parse_date,
    _to_float,
    money_account_choices,
    pagination_props,
    resolve_money_account,
    snapshot_fields,
    track_changes,
    validate_proof_file,
)
from .helpers import (
    period_label as _period_label,
)

logger = logging.getLogger(__name__)


def _season_activity(clients_qs, start, end):
    """{client_id: [cl_count, room_nights, last_check_in]} for live CLs of
    `clients_qs` checking in between start and end."""
    out = {}
    cls = (ConfirmationLetter.objects.filter(client__in=clients_qs, check_in__gte=start, check_in__lte=end)
           .exclude(reservation_status='CANCELLED').prefetch_related('rooms'))
    for cl in cls:
        row = out.setdefault(cl.client_id, [0, 0, None])
        row[0] += 1
        row[1] += sum(r.quantity for r in cl.rooms.all()) * (cl.num_nights or 0)
        row[2] = max(row[2], cl.check_in) if row[2] else cl.check_in
    return out


def _client_season_status(cid, cur, prev, first_seen, start, active):
    if not active:
        return 'inactive'
    if cid in cur:
        return 'new' if first_seen.get(cid) and first_seen[cid] >= start else 'active'
    return 'dormant' if cid in prev else 'inactive'


@require_perm('clients', 'view')
def client_list(request):
    """Client list (Record View HMS canvas): KPIs for the umrah season against
    the season before at the same point (new, active, retention, dormant)."""
    from django.db.models import Max, Min

    from ..models.period import Season
    from .helpers import csv_list, list_per_page
    base = scope(Client.objects.all(), request.user)
    q = request.GET.get('q', '').strip()
    statuses = csv_list(request, 'status', ['new', 'active', 'dormant', 'inactive'])
    city = request.GET.get('city', '').strip()
    sort = request.GET.get('sort', '-last')
    today = timezone.localdate()

    seasons = list(Season.objects.order_by('-date_from'))
    season = next((x for x in seasons if x.name == request.GET.get('season')), None) \
        or next((x for x in seasons if x.date_from <= today <= x.date_to), None) or (seasons[0] if seasons else None)
    prev_season = next((x for x in seasons if season and x.date_to < season.date_from), None)

    qs = base
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(city__icontains=q) | Q(pic__icontains=q))
    if city:
        qs = qs.filter(city__iexact=city)

    last_cl = dict(ConfirmationLetter.objects.filter(client__in=base).exclude(reservation_status='CANCELLED')
                   .values('client_id').annotate(t=Max('check_in')).values_list('client_id', 't'))
    kpis, cur, prev = None, {}, {}
    if season:
        point = min(today, season.date_to)
        cur = _season_activity(base, season.date_from, point)
        first_seen = dict(ConfirmationLetter.objects.filter(client__in=base).exclude(reservation_status='CANCELLED')
                          .values('client_id').annotate(t=Min('check_in')).values_list('client_id', 't'))
        if prev_season:
            same_point = prev_season.date_from + (point - season.date_from)
            prev = _season_activity(base, prev_season.date_from, prev_season.date_to)
            prev_to_point = _season_activity(base, prev_season.date_from, min(same_point, prev_season.date_to))
            before_prev = next((x for x in seasons if x.date_to < prev_season.date_from), None)
            pp = _season_activity(base, before_prev.date_from, before_prev.date_to) if before_prev else {}
        else:
            prev_to_point, pp, same_point = {}, {}, None
        active_ids = set(base.filter(is_active=True).values_list('pk', flat=True))
        new_now = [c for c in cur if first_seen.get(c) and first_seen[c] >= season.date_from]
        new_then = [c for c in prev_to_point if prev_season and first_seen.get(c) and first_seen[c] >= prev_season.date_from]
        dormant_now = [c for c in prev if c not in cur and c in active_ids]
        dormant_then = [c for c in pp if c not in prev_to_point]
        back = sum(1 for c in prev if c in cur)
        back_then = sum(1 for c in pp if c in prev)
        kpis = {
            'season': season.name, 'prev_season': prev_season.name if prev_season else None,
            'range': f"{season.date_from.strftime('%B')} to {season.date_to.strftime('%B')}",
            'new': len(new_now), 'new_then': len(new_then) if prev_season else None,
            'active': len(cur), 'active_then': len(prev_to_point) if prev_season else None, 'clients': len(active_ids),
            'retention': round(back * 100 / len(prev)) if prev else None, 'back': back, 'prev_active': len(prev),
            'retention_then': round(back_then * 100 / len(pp)) if pp else None,
            'dormant': len(dormant_now), 'dormant_then': len(dormant_then) if pp else None,
            'dormant_nights': sum(prev[c][1] for c in dormant_now),
        }
        status_of = lambda c: _client_season_status(c.pk, cur, prev, first_seen, season.date_from, c.is_active)
    else:
        # No season set up: the CL and room-night columns count all time.
        cur = _season_activity(base, date(2000, 1, 1), date(2100, 1, 1))
        status_of = lambda c: 'active' if c.is_active else 'inactive'

    rows_all = list(qs)
    counts = {k: 0 for k in ('new', 'active', 'dormant', 'inactive')}
    for c in rows_all:
        c._status = status_of(c)
        counts[c._status] += 1
    rows_all = [c for c in rows_all if not statuses or c._status in statuses]
    if sort == 'name':
        rows_all.sort(key=lambda c: (c.brand or c.name).lower())
    else:
        rows_all.sort(key=lambda c: (last_cl.get(c.pk) or date.min), reverse=True)

    page_obj = Paginator(rows_all, list_per_page(request)).get_page(request.GET.get('page'))
    clients = [{
        "id": c.pk, "name": c.name, "brand": c.brand, "city": c.city, "pic": c.pic, "wa": c.wa,
        "wa_group": c.wa_group, "reminder_target": c.reminder_target,
        "last_booking": last_cl[c.pk].isoformat() if c.pk in last_cl else None,
        "cl_count": cur.get(c.pk, [0])[0], "room_nights": cur.get(c.pk, [0, 0])[1],
        "status": c._status, "is_active": c.is_active,
    } for c in page_obj]
    return inertia_render(request, "Client/List", props={
        "clients": clients,
        "filters": {"q": q, "status": statuses, "city": city, "sort": sort, "season": season.name if season else "",
                    "per": list_per_page(request)},
        "seasons": [{"name": x.name, "current": x.date_from <= today <= x.date_to} for x in seasons],
        "cities": sorted({c for c in base.exclude(city='').values_list('city', flat=True)}, key=str.lower),
        "counts": counts, "kpis": kpis,
        "pagination": pagination_props(page_obj),
    })


@require_perm('clients', 'export')
def client_export_csv(request):
    """Clients with their contact: name, brand, city, PIC and WhatsApp."""
    from .helpers import csv_export_response
    qs = scope(Client.objects.all(), request.user).order_by('name')
    return csv_export_response('clients.csv', ['Client', 'Brand', 'City', 'Province', 'PIC', 'WhatsApp', 'Status'], [
        [c.name, c.brand, c.city, c.province, c.pic, c.wa, 'Active' if c.is_active else 'Inactive'] for c in qs
    ])


def _owner_branches(user):
    """Branches the user may give a client to: the ones they cover."""
    from ..models.branch import Branch
    return scope(Branch.objects.filter(is_active=True), user).order_by("name")


def _branch_choices(user):
    return [{"value": b.code, "label": b.name} for b in _owner_branches(user)]


def _owner_branch(data, user, instance=None):
    """The owner branch posted, else the client's current one, else the user's
    only branch, else the default."""
    from ..models.client import DEFAULT_OWNER_BRANCH
    posted = (data.get("owner_branch") or "").strip()
    if posted:
        return posted
    if instance is not None and instance.owner_branch_id:
        return instance.owner_branch_id
    branches = list(_owner_branches(user).values_list("code", flat=True))
    return branches[0] if len(branches) == 1 else DEFAULT_OWNER_BRANCH


def _validate_client(data, user, instance=None):
    from ..models.client import client_name_key
    errors = {}
    name = data.get("name", "").strip()
    if not name:
        errors["name"] = "Company name is required."
    else:
        # Satu perusahaan satu baris: "PT. Safaar" dan "SAFAAR" dianggap sama.
        clash = Client.objects.filter(name_key=client_name_key(name))
        if instance is not None and instance.pk:
            clash = clash.exclude(pk=instance.pk)
        other = clash.first()
        if other:
            errors["name"] = f'A client named "{other.name}" already exists.'
    if not _owner_branches(user).filter(code=_owner_branch(data, user, instance)).exists():
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
        errors = _validate_client(request.POST, request.user)
        if errors:
            return inertia_render(request, "Client/Form", props={
                "client": _client_echo(request.POST), "edit": False, "errors": errors,
                "branch_choices": _branch_choices(request.user),
            })
        c = Client()
        _save_client(c, request.POST, _owner_branch(request.POST, request.user))
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name)
        messages.success(request, tr(request, f'Client "{c.name}" added.', f'Client "{c.name}" ditambahkan.'))
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": None, "edit": False, "branch_choices": _branch_choices(request.user),
    })


@require_perm('clients', 'edit')
def client_edit(request, pk):
    c = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)
    if request.method == 'POST':
        errors = _validate_client(request.POST, request.user, instance=c)
        if errors:
            echo = _client_echo(request.POST); echo["id"] = c.pk
            return inertia_render(request, "Client/Form", props={
                "client": echo, "edit": True, "errors": errors,
                "branch_choices": _branch_choices(request.user),
            })
        _before = snapshot_fields(c, ['name', 'brand', 'city', 'province', 'address', 'pic', 'wa', 'email'])
        _save_client(c, request.POST, _owner_branch(request.POST, request.user, c))
        _after = snapshot_fields(c, ['name', 'brand', 'city', 'province', 'address', 'pic', 'wa', 'email'])
        changes = track_changes(
            _before, _after,
            labels={'name': 'Name', 'brand': 'Brand', 'city': 'City', 'province': 'Province', 'address': 'Address', 'pic': 'PIC', 'wa': 'WhatsApp', 'email': 'Email'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, changes)
        messages.success(request, tr(request, f'Client "{c.name}" updated.', f'Client "{c.name}" diperbarui.'))
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
        "branch_choices": _branch_choices(request.user),
    })


@require_perm('clients', 'edit')
@require_POST
def client_toggle_active(request, pk):
    """Deactivate / activate in one click: the reversible way to retire a
    client, which Delete refuses once it has financial history."""
    c = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)
    c.is_active = not c.is_active
    c.save(update_fields=['is_active', 'updated_at'])
    log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name,
                 [{'label': 'Status', 'before': 'Inactive' if c.is_active else 'Active',
                   'after': 'Active' if c.is_active else 'Inactive'}])
    messages.success(request, tr(request, f'Client "{c.name}" is now {"active" if c.is_active else "inactive"}.', f'Client "{c.name}" sekarang {"aktif" if c.is_active else "nonaktif"}.'))
    return redirect('client_detail', pk=pk)


@require_perm('clients', 'delete')
@require_POST
def client_delete(request, pk):
    c = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)
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
                tr(request, f'Client "{name}" is in the financial journal or payments and cannot be deleted. Deactivate it instead.', f'Client "{name}" tidak bisa dihapus karena sudah tercatat di jurnal keuangan/pembayaran. Nonaktifkan saja.'),
            )
            return redirect('client_detail', pk=pk)
        raise
    log_activity(request.user, ActivityLog.ACTION_DELETE, 'Client', name)
    messages.success(request, tr(request, f'Client "{name}" deleted.', f'Client "{name}" dihapus.'))
    return redirect('client_list')


@require_perm('clients', 'view')
def client_detail(request, pk):
    """Client information only. Money (invoices, balances, fund activity,
    transfer/refund, statement) lives under Finance → Client Ledger."""
    from django.utils import timezone
    c = get_in_scope_or_404(Client.objects.select_related('owner_branch'), request.user, pk=pk)
    cls = list(c.cls.order_by('-created_at'))
    cls_data = [{
        "pk": cl.pk,
        "confirmation_number": cl.confirmation_number,
        "guest_name": cl.guest_name,
        "hotel_name": cl.hotel_name,
        "check_in": cl.check_in.strftime("%d/%m/%Y") if cl.check_in else None,
        "check_out": cl.check_out.strftime("%d/%m/%Y") if cl.check_out else None,
        "num_nights": cl.num_nights,
        "num_guests": cl.num_guests,
        "status": cl.reservation_status,
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
            "branch": c.owner_branch.name if c.owner_branch_id else None,
            "created_at": c.created_at.strftime("%b %Y") if c.created_at else None,
            "lat": c.lat,
            "lng": c.lng,
        },
        "cls": cls_data,
    })


@require_perm('clients', 'view')
def client_map(request):
    qs = scope(Client.objects.filter(lat__isnull=False, lng__isnull=False), request.user)
    return inertia_render(request, "Client/Map", props={"clients_count": qs.count()})


@require_perm('clients', 'view')
def client_map_data(request):
    qs = scope(Client.objects.filter(lat__isnull=False, lng__isnull=False), request.user)

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


def _save_client(c, data, owner_branch):
    c.name      = data.get('name', '').strip()
    c.brand     = data.get('brand', '').strip()
    c.owner_branch_id = owner_branch
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


def _reason_note(P):
    """The form's Reason and Note as the document's one note: the reason
    first, the note after it."""
    reason = (P.get('reason') or '').strip()
    note = (P.get('note') or '').strip()
    return '\n'.join(x for x in (reason, note) if x)


@require_perm('payments', 'edit')
def client_refund(request, pk):
    """Pay a client's fund back out of a concrete account.

    Two amounts: the SAR taken from the client's fund (journal) and what the
    account actually paid in its own currency (cash book). They are the same
    number for a SAR account; for an IDR/USD account both are entered."""
    client_obj = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)
    accounts = money_account_choices(branches=with_head_office(request.user))

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
    note = _reason_note(P)
    refund_date = _parse_date(P.get('refund_date')) or timezone.localdate()
    proof = request.FILES.get('proof')

    errors = {}
    allowed = with_head_office(request.user)
    if account is not None and allowed is not None and account.branch_id not in allowed:
        account = None
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
                refund_date=refund_date, created_by=request.user, note=note, proof=proof,
            )
        except FinanceError as e:
            errors['amount_sar'] = str(e)
        else:
            logger.info("ledger: refund %s SAR (%s %s) to client %s from %s",
                        amount, paid, account.currency, client_obj.pk, account)
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Refund', client_obj.name)
            messages.success(request, tr(request, f'Refund {refund.refund_number}: {amount} SAR to {client_obj.name} — waiting for another user to approve.', f'Refund {refund.refund_number}: {amount} SAR ke {client_obj.name} — menunggu persetujuan user lain.'))
            return redirect('client_finance_statement', pk=pk)

    return page(errors, {
        'from_account': P.get('from_account', ''), 'amount_sar': P.get('amount_sar', ''),
        'amount_paid': P.get('amount_paid', ''), 'note': P.get('note', ''), 'reason': P.get('reason', ''),
        'refund_date': P.get('refund_date', ''),
    })


@require_perm('payments', 'edit')
def client_deposit_transfer(request, pk):
    """Move part of a client's deposit to another client (a numbered document)."""
    from ..finance.deposit import request_transfer
    client_obj = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)

    def page(errors=None, initial=None):
        others = list(scope(Client.objects.filter(is_active=True), request.user).exclude(pk=client_obj.pk).order_by('name'))
        held = finance_queries.client_credit_balances(c.pk for c in others)
        return inertia_render(request, 'Finance/DepositTransfer', props={
            'client': {'pk': client_obj.pk, 'name': client_obj.name,
                       'saldo_dana': finance_queries.client_credit_balance(client_obj.id)},
            'clients': [{'id': c.pk, 'name': c.name, 'city': c.city, 'deposit': held.get(c.pk, 0)} for c in others],
            'errors': errors or {},
            'initial': initial or {},
        })

    if request.method != 'POST':
        return page()
    P = request.POST
    note = _reason_note(P)
    transfer_date = _parse_date(P.get('transfer_date')) or timezone.localdate()
    amount = round_half_up(_to_float(P.get('amount_sar')))
    to_client = scope(Client.objects.all(), request.user).filter(pk=P.get('to_client') or 0).exclude(pk=client_obj.pk).first()
    errors = {}
    if to_client is None:
        errors['to_client'] = 'Choose the client that receives the deposit.'
    if amount <= 0:
        errors['amount_sar'] = 'Enter an amount greater than zero.'
    if not errors:
        try:
            transfer = request_transfer(client_obj, to_client, amount_sar=amount, transfer_date=transfer_date,
                                        created_by=request.user, note=note)
        except FinanceError as e:
            errors['amount_sar'] = str(e)
        else:
            log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client Deposit Transfer', transfer.transfer_number)
            messages.success(request, tr(request, f'{transfer.transfer_number}: {amount} SAR to {to_client.name} — waiting for another user to approve.', f'{transfer.transfer_number}: {amount} SAR ke {to_client.name} — menunggu persetujuan user lain.'))
            return redirect('client_finance_statement', pk=pk)
    return page(errors, {'to_client': P.get('to_client', ''), 'amount_sar': P.get('amount_sar', ''), 'note': P.get('note', ''),
                         'reason': P.get('reason', ''), 'transfer_date': P.get('transfer_date', '')})


def _decide_deposit_out(request, kind, pk, decision):
    """Setujui / tolak refund atau transfer deposit yang pending (POST)."""
    from ..finance import deposit
    from ..models import ClientRefund, ClientTransfer
    model = ClientRefund if kind == 'refund' else ClientTransfer
    doc = get_in_scope_or_404(model.objects.all(), request.user, pk=pk)
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
        messages.success(request, tr(request, f'{number} {"approved" if decision == "confirm" else "rejected"}.', f'{number} {"disetujui" if decision == "confirm" else "ditolak"}.'))
    return redirect('client_finance_statement', pk=client_pk)


@require_perm('payments', 'approve')
def client_refund_confirm(request, pk):
    return _decide_deposit_out(request, 'refund', pk, 'confirm')


@require_perm('payments', 'approve')
def client_refund_reject(request, pk):
    return _decide_deposit_out(request, 'refund', pk, 'reject')


@require_perm('payments', 'approve')
def client_deposit_transfer_confirm(request, pk):
    return _decide_deposit_out(request, 'transfer', pk, 'confirm')


@require_perm('payments', 'approve')
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

    c = get_in_scope_or_404(Client.objects.all(), request.user, pk=pk)

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
            filename=f'open_items_{c.name}_{timezone.localdate()}.pdf'.replace(' ', '_'),
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
        # from the query sweep in adjustments, unapplied payments and deposit
        # lines too, so they would not tie out to what these columns print.
        subtotal_debit = sum(r['debit'] for r in reservations)
        subtotal_credit = sum(r['credit'] for r in reservations)
        return _render_list_pdf(
            request, Client.objects.none(),
            template='hw/client/client_statement_byres_pdf.html',
            # Nama file = nama client; karakter yang dilarang di nama file
            # Windows/macOS diganti spasi.
            filename=re.sub(r'[\\/:*?"<>|]+', ' ', c.name).strip() + '.pdf',
            extra_ctx={
                'client': c,
                'reservations': reservations,
                'subtotal_debit': subtotal_debit,
                'subtotal_credit': subtotal_credit,
                'subtotal_balance': subtotal_debit - subtotal_credit,
                'printed_by': request.user.get_full_name() or request.user.get_username(),
                'count_settled': sum(1 for r in reservations if r['settled']),
                'count_outstanding': sum(1 for r in reservations if not r['settled']),
                'adjustments': st['adjustments'],
                'unapplied_payments': st['unapplied_payments'],
                'deposit_on_account': st['deposit_on_account'],
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
        filename=f'statement_{c.name}_{timezone.localdate()}.pdf'.replace(' ', '_'),
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
