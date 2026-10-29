import json
import logging
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import redirect
from django.utils import timezone
from inertia import render as inertia_render

from ..branch_scope import get_in_scope_or_404, scope
from ..finance import queries as fq
from ..finance.errors import FinanceError
from ..i18n import tr
from ..models import ActivityLog, Client, ConfirmationLetter, Invoice, InvoiceLine, log_activity
from ..models.choices import InvoiceType
from ..permissions import require_perm
from ..utils import round_half_up
from .context import _build_reservation_context
from .credit_note_views import invoice_credit_props
from .helpers import (
    _client_options,
    _parse_date,
    _render_list_pdf,
    csv_export_response,
    due_soon_alert,
    pagination_props,
    snapshot_fields,
    track_changes,
)
from .invoice_billing import _billing_props
from .pdf import _logo_file_url, _render_invoice_pdf

logger = logging.getLogger(__name__)


def _resolve_client_from_post(request):
    """Resolve Client from the submitted client_id, or from linked CLs as fallback."""
    client_id = request.POST.get("client_id")
    if client_id:
        try:
            return scope(Client.objects.all(), request.user).get(pk=client_id, is_active=True)
        except (Client.DoesNotExist, ValueError):
            pass
    # Fallback: resolve from linked CLs
    cl_ids = _parse_cl_ids(request)
    if cl_ids:
        cl_clients = set(
            scope(ConfirmationLetter.objects.filter(pk__in=cl_ids), request.user).values_list('client_id', flat=True)
        )
        if len(cl_clients) == 1:
            try:
                return scope(Client.objects.all(), request.user).get(pk=next(iter(cl_clients)))
            except Client.DoesNotExist:
                pass
    return None


def _issuing_branches(user):
    from ..models.branch import Branch
    return scope(Branch.objects.filter(is_active=True), user).order_by("name")


def _branch_choices(user):
    return [{"value": b.code, "label": b.name} for b in _issuing_branches(user)]


def _posted_branch(request, client, current=None):
    """Issuing branch for the invoice: the form's pick (one of the user's
    branches), otherwise the branch it already has, otherwise ("Automatic" on a
    new invoice) the client's owner branch."""
    code = (request.POST.get("branch") or "").strip()
    if code and _issuing_branches(request.user).filter(code=code).exists():
        return code
    return current or client.owner_branch_id


def _filter_by_status(qs, status):
    """Filter a hotel Invoice queryset by payment status (lunas/belum/partial).

    Done in Python, not SQL: total_paid_sar needs per-payment currency
    conversion, which isn't expressible as a queryset filter. Paid amounts
    come from one bulk ledger query -- reading the total_paid_sar property
    here used to cost one ledger query per invoice.
    """
    if status == 'void':
        return qs.filter(status=Invoice.STATUS_VOID)
    if status not in ('lunas', 'belum', 'partial'):
        return qs
    invoices = [inv for inv in qs if not inv.is_void]
    ids = [inv.pk for inv in invoices]
    paid_map = fq.invoice_paid_map(ids)
    credited_map = fq.invoice_credited_map(ids)
    filtered_ids = []
    for inv in invoices:
        credited, deposited = credited_map.get(inv.pk, (0, 0))
        paid = paid_map.get(inv.pk, 0) - deposited
        due = inv.total_sar - credited
        if status == 'lunas' and paid >= due:
            filtered_ids.append(inv.pk)
        elif status == 'belum' and paid < 1 and due > 0:
            filtered_ids.append(inv.pk)
        elif status == 'partial' and paid >= 1 and paid < due:
            filtered_ids.append(inv.pk)
    return qs.filter(pk__in=filtered_ids)


def _filter_invoice_qs(base_qs, request, apply_status=True, order=True):
    """Apply standard hotel-invoice filters (q/status/dates) to a queryset.

    Shared by the list, PDF and CSV endpoints so the three never drift.
    """
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    qs = base_qs
    if q:
        qs = qs.filter(Invoice.objects.name_matches(q))
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)
    if apply_status:
        qs = _filter_by_status(qs, status)
    if order:
        qs = qs.order_by(F('due_date').asc(nulls_last=True), '-created_at')

    return qs, {'q': q, 'status': status, 'date_from': date_from, 'date_to': date_to}


def _hotel_invoices(request):
    """Hotel invoices issued by the user's branches."""
    return scope(Invoice.objects.filter(invoice_type=InvoiceType.HOTEL), request.user)


def _invoice_money(invoices):
    """{pk: (due, remaining, status)} for hotel invoices: what is owed after
    credit notes, what is still open, and paid / partial / unpaid / void /
    overpaid. Two bulk ledger queries for the lot."""
    ids = [inv.pk for inv in invoices]
    paid_map = fq.invoice_paid_map(ids)
    credited_map = fq.invoice_credited_map(ids)
    out = {}
    for inv in invoices:
        credited, deposited = credited_map.get(inv.pk, (0, 0))
        due = 0 if inv.is_void else inv.total_sar - credited
        remaining = due - (paid_map.get(inv.pk, 0) - deposited)
        status = ("void" if inv.is_void else "overpaid" if remaining < 0 else "paid" if remaining == 0
                  else "partial" if remaining < due else "unpaid")
        out[inv.pk] = (due, remaining, status)
    return out


def _due_month_kpis(base_qs, first, last, user):
    """Invoiced and collection for invoices due in [first, last]."""
    invs = [i for i in base_qs.filter(due_date__gte=first, due_date__lte=last) if not i.is_void]
    money = _invoice_money(invs)
    due = sum(money[i.pk][0] for i in invs)
    open_ = sum(max(0, money[i.pk][1]) for i in invs)
    return {
        'invoiced': sum(i.total_sar for i in invs), 'count': len(invs),
        'outstanding': open_, 'rate': round((due - open_) * 100 / due) if due else None,
    }


@require_perm('invoice', 'view')
def invoice_list(request):
    """Invoice list (Record View HMS canvas): KPIs for the month invoices fall
    due, the toolbar, and the table one page at a time."""
    from .helpers import list_per_page, list_period, pct_delta, prev_month_range
    base_qs = _hotel_invoices(request).with_lines()
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    sort = request.GET.get('sort', 'due')
    date_from, date_to, period = list_period(request)
    today = timezone.localdate()

    qs = base_qs
    if q:
        qs = qs.filter(Invoice.objects.name_matches(q))
    # A search looks past the month nav; a due range picked in the filter
    # still holds. The KPIs stay on the month.
    search_all = bool(q) and not (period['from'] or period['to']) and date_from is not None
    tbl_from, tbl_to = (None, None) if search_all else (date_from, date_to)
    period_qs = qs
    if tbl_from:
        period_qs = period_qs.filter(due_date__gte=tbl_from)
    if tbl_to:
        period_qs = period_qs.filter(due_date__lte=tbl_to)

    period_invs = list(period_qs.order_by(
        F('due_date').desc(nulls_last=True) if sort == '-due' else F('due_date').asc(nulls_last=True), '-created_at'))
    money = _invoice_money(period_invs)
    counts = {k: sum(1 for v in money.values() if v[2] == k) for k in ('paid', 'partial', 'unpaid', 'void', 'overpaid')}
    counts['paid'] += counts.pop('overpaid')

    # Overdue is over every date (its KPI is not tied to the month).
    if status == 'overdue':
        rows = [i for i in qs.filter(due_date__lt=today).order_by('due_date') if not i.is_void]
        money.update(_invoice_money(rows))
        rows = [i for i in rows if money[i.pk][1] > 0]
    elif status in ('paid', 'partial', 'unpaid', 'void'):
        rows = [i for i in period_invs if money[i.pk][2] == status or (status == 'paid' and money[i.pk][2] == 'overpaid')]
    else:
        rows = period_invs

    page_obj = Paginator(rows, list_per_page(request)).get_page(request.GET.get('page'))
    invoices = []
    for inv in page_obj:
        due, remaining, st = money[inv.pk]
        late = (today - inv.due_date).days if inv.due_date and inv.due_date < today and remaining > 0 and not inv.is_void else 0
        invoices.append({
            "id": inv.id, "invoice_number": inv.invoice_number, "customer_name": inv.customer_name,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "total_sar": inv.total_sar, "remaining_sar": remaining, "status": st, "days_late": late,
        })

    kpis = None
    if period['month']:
        cur = _due_month_kpis(base_qs, date_from, date_to, request.user)
        pf, pl = prev_month_range(date_from)
        prev = _due_month_kpis(base_qs, pf, pl, request.user)
        overdue_all = [i for i in base_qs.filter(due_date__lt=today) if not i.is_void]
        om = _invoice_money(overdue_all)
        overdue = [i for i in overdue_all if om[i.pk][1] > 0]
        unbilled = list(scope(ConfirmationLetter.objects.uninvoiced(), request.user)
                        .exclude(reservation_status='CANCELLED')
                        .filter(check_in__gte=date_from, check_in__lte=date_to)
                        .prefetch_related('rooms').order_by('check_in'))
        kpis = {
            'cur': cur, 'prev': prev, 'prev_month': pf.strftime('%Y-%m'),
            'invoiced_delta': pct_delta(cur['invoiced'], prev['invoiced']),
            'rate_delta': (cur['rate'] - prev['rate']) if cur['rate'] is not None and prev['rate'] is not None else None,
            'overdue': {'value': sum(om[i.pk][1] for i in overdue), 'count': len(overdue),
                        'oldest_days': max(((today - i.due_date).days for i in overdue), default=0)},
            'unbilled': {'value': round_half_up(sum(float(c.total_price or 0) for c in unbilled)), 'count': len(unbilled),
                         'first': unbilled[0].check_in.isoformat() if unbilled else None},
        }

    years = sorted({d.year for d in base_qs.exclude(due_date=None).dates('due_date', 'year')} | {today.year})
    return inertia_render(request, "Invoice/List", props={
        "invoices": invoices,
        "filters": {"q": q, "status": status, "sort": sort, "per": list_per_page(request), **period},
        "search_all": search_all,
        "years": years, "counts": counts, "kpis": kpis,
        "export_qs": "?" + urlencode([(k, v) for k, v in [
            ("q", q), ("date_from", tbl_from.isoformat() if tbl_from else ""),
            ("date_to", tbl_to.isoformat() if tbl_to else ""),
            ("status", {"paid": "lunas", "unpaid": "belum", "partial": "partial", "void": "void"}.get(status, "")),
        ] if v]),
        "pagination": pagination_props(page_obj),
    })


def _invoice_stats(invoice_qs):
    from ..finance import accounts as coa

    invoice_ids = list(invoice_qs.values_list('id', flat=True))
    total_tagihan = fq.total_charged(invoice_ids)
    terbayar_surabaya = fq.paid_into(coa.CASH_SBY, invoice_ids)
    terbayar_pusat = fq.paid_into(coa.CASH_PUSAT, invoice_ids)

    return {
        'total_tagihan': total_tagihan,
        'belum_terbayar': max(0, total_tagihan - terbayar_surabaya - terbayar_pusat),
        # mengendap boleh negatif: Surabaya bisa mengirim lebih dari yang pernah
        # diterima untuk invoice-invoice ini (kredit di pusat), lihat hw/ledger.py.
        'mengendap': fq.mengendap(invoice_ids),
        'terbayar_surabaya': terbayar_surabaya,
        'terbayar_pusat': terbayar_pusat,
    }


@require_perm('invoice', 'create')
def invoice_new(request):
    suggested_number = Invoice.suggest_number(InvoiceType.HOTEL)

    if request.method == "POST":
        # The approved form has no number field: the next number is issued
        # with the invoice. A number posted by an older client still wins.
        posted_number = request.POST.get("invoice_number", "").strip()
        invoice_number = posted_number or suggested_number

        def _reject(errors):
            return inertia_render(request, "Invoice/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": invoice_number or suggested_number,
                "cl_data": _cl_data_for_form(request.user),
                "clients": _client_options(request.user),
                "branch_choices": _branch_choices(request.user),
                "initial": _invoice_echo(request),
                "errors": errors,
            })

        if posted_number and Invoice.objects.filter(invoice_number=posted_number).exists():
            return _reject({"invoice_number": f"Invoice number '{posted_number}' is already in use."})

        cl_ids = _billable_cl_ids(request)
        client = _resolve_client_from_post(request)
        errors = _validate_hotel_invoice(request, cl_ids, client)
        if errors:
            return _reject(errors)

        try:
            with transaction.atomic():
                issued_d = _parse_date(request.POST.get("issued_date"))
                if posted_number:
                    invoice_number = posted_number
                else:
                    # Allocate inside the transaction that inserts the invoice,
                    # from the issued date the user picked (not from the date
                    # the form was opened).
                    invoice_number = Invoice.generate_number(InvoiceType.HOTEL, issued_date=issued_d)
                invoice = Invoice.objects.create(
                    invoice_type=InvoiceType.HOTEL,
                    invoice_number=invoice_number,
                    client=client,
                    branch_id=_posted_branch(request, client),
                    issued_date=issued_d,
                    due_date=_parse_date(request.POST.get("due_date")),
                    currency="SAR",
                    created_by=request.user,
                )
                if posted_number:
                    Invoice.claim_number(InvoiceType.HOTEL, invoice.invoice_number, issued_date=issued_d)
                _sync_hotel_lines(invoice, cl_ids, request.user)
        except IntegrityError:
            return _reject({"invoice_number": f"Invoice number '{invoice_number}' is already in use."})
        except (FinanceError, ValueError) as e:
            return _reject({"finance": str(e)})

        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number)
        messages.success(request, tr(request, f"Invoice {invoice.invoice_number} created.", f"Invoice {invoice.invoice_number} dibuat."))
        return redirect("invoice_detail", pk=invoice.pk)

    initial = None
    preselect_cl = scope(ConfirmationLetter.objects.uninvoiced(), request.user).filter(pk=request.GET.get("cl") or 0).first()
    if preselect_cl:
        initial = {"linked_cl_ids": [preselect_cl.pk]}

    return inertia_render(request, "Invoice/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "cl_data": _cl_data_for_form(request.user),
        "clients": _client_options(request.user),
        "branch_choices": _branch_choices(request.user),
        "initial": initial,
    })


def _overpaid_props(reservations):
    """Reservasi yang kelebihan bayar dan pembayaran yang uangnya ada di sana,
    untuk dua jalan keluarnya di layar: realokasi pembayaran itu ke reservasi
    lain, atau pindahkan kelebihannya ke deposit client."""
    from ..models.payment import PaymentAllocation, PaymentRecord
    overpaid = [
        {"line_id": r["id"], "number": r["number"], "excess_sar": -r["remaining_int"]}
        for r in reservations if r["remaining_int"] < 0
    ]
    rows = (
        PaymentAllocation.objects.filter(
            invoice_line_id__in=[o["line_id"] for o in overpaid],
            payment__status__in=PaymentRecord.EFFECTIVE_STATUSES,
        )
        .values("payment_id", "payment__payment_number").distinct().order_by("payment_id")
    ) if overpaid else []
    return {
        "overpaid": overpaid,
        "overpaid_payments": [{"id": r["payment_id"], "number": r["payment__payment_number"]} for r in rows],
    }


@require_perm('invoice', 'view')
def invoice_detail(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.filter(invoice_type=InvoiceType.HOTEL), request.user, pk=pk)
    res_ctx = _build_reservation_context(invoice)
    reservations = [{
        "id": r["id"],
        "number": r["number"],
        "hotel": r["hotel"],
        "check_in": r["check_in"].strftime("%d/%m/%Y") if r["check_in"] else None,
        "check_out": r["check_out"].strftime("%d/%m/%Y") if r["check_out"] else None,
        "total_int": r["total_int"],
        "paid_int": r["paid_int"],
        "remaining_int": r["remaining_int"],
        "remaining_class": r["remaining_class"],
        "credited_int": r["credited_int"],
        "cl_pk": r["cl_pk"],
    } for r in res_ctx]

    payments = [{
        "id": p["pk"],
        "status": p["status"],
        "unallocated_sar": p["unallocated_sar"],
        "linked_number": p["ref"],
        "payment_date": p["payment_date"].strftime("%d/%m/%Y") if p["payment_date"] else None,
        "payment_label": p["payment_date"].strftime("%d %b %Y") if p["payment_date"] else None,
        "payment_iso": p["payment_date"].isoformat() if p["payment_date"] else None,
        "payment_number": p["payment_number"],
        "method": p["method"],
        "amount_int": int(round(p["amount"])),
        "currency": p["currency"],
        "exchange_rate": p["exchange_rate"],
        "exchange_rate_fmt": f"{p['exchange_rate']:.2f}",
        "amount_sar_int": p["amount_sar"],
        "proof_url": p["proof"].url if p["proof"] else None,
        "note": p["note"],
    } for p in fq.payment_history_rows(invoice)]

    due_alert = due_soon_alert(invoice.due_date, invoice.remaining_sar)

    # Who confirmed each payment — for the activity timeline.
    from ..models.payment import PaymentRecord
    confirmers = {
        pr.pk: (pr.confirmed_by.get_full_name() or pr.confirmed_by.username) if pr.confirmed_by else None
        for pr in PaymentRecord.objects.filter(pk__in=[p["id"] for p in payments]).select_related("confirmed_by")
    }
    for p in payments:
        p["confirmed_by"] = confirmers.get(p["id"])

    from ..models import Receipt
    receipt = (
        Receipt.objects.filter(invoice=invoice).exclude(status=Receipt.STATUS_VOIDED)
        .order_by("-pk").values("pk", "receipt_number").first()
    )
    client = invoice.client
    logs = [{
        "action": l.action,
        "action_label": l.get_action_display(),
        "by": l.actor_display,
        "changes": l.changes,
        "timestamp": l.timestamp.strftime("%d %b %Y %H:%M"),
        "date": l.timestamp.date().isoformat(),
    } for l in ActivityLog.objects.filter(
        model_name="Invoice Hotel", object_ref=invoice.invoice_number,
    ).select_related("user").order_by("-timestamp")]
    # "Pay to": the issuing branch's accounts flagged for invoices, one block each.
    pay_to = [{
        "id": b.pk,
        "bank_name": b.bank_name,
        "account_identifier": b.account_identifier,
        "account_name": b.account_name,
        "currency": b.currency,
    } for b in invoice.pay_to_accounts()]

    last_payment = max((p["payment_iso"] for p in payments if p["payment_iso"]), default=None) \
        if invoice.remaining_sar == 0 else None

    return inertia_render(request, "Invoice/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "issued_date": invoice.issued_date.strftime("%d %b %Y") if invoice.issued_date else None,
            "due_date": invoice.due_date.strftime("%d %b %Y") if invoice.due_date else None,
            "due_iso": invoice.due_date.isoformat() if invoice.due_date else None,
            "terms_days": (invoice.due_date - invoice.issued_date).days
            if invoice.due_date and invoice.issued_date else None,
            "settled_date": date.fromisoformat(last_payment).strftime("%d %b %Y") if last_payment else None,
            "created_at": invoice.created_at.strftime("%d %b %Y") if invoice.created_at else None,
            "created_iso": invoice.created_at.date().isoformat() if invoice.created_at else None,
            "prepared_by": (invoice.created_by.get_full_name() or invoice.created_by.username)
            if invoice.created_by_id else None,
            "client": {"pk": client.pk, "name": client.name, "phone": client.wa} if client else None,
            "receipt": receipt,
            "branch": {"code": invoice.branch_id, "name": invoice.branch.name} if invoice.branch_id else None,
            "total_sar": invoice.total_sar,
            "total_paid_sar": invoice.total_paid_sar,
            "remaining_sar": invoice.remaining_sar,
            "status": invoice.status,
            "payment_state": invoice.financial_state,
        },
        "reservations": reservations,
        # Overpaid on its reservations: shown with a "move to deposit" action.
        "excess_sar": sum(-r["remaining_int"] for r in reservations if r["remaining_int"] < 0),
        **_overpaid_props(reservations),
        "payments": payments,
        "due_alert": due_alert,
        "logs": logs,
        "pay_to": pay_to,
        **_billing_props(invoice),
        **invoice_credit_props(invoice),
    })


@require_perm('invoice', 'edit')
def invoice_edit(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.filter(invoice_type=InvoiceType.HOTEL), request.user, pk=pk)
    if invoice.is_void:
        messages.error(request, tr(request, f'Invoice {invoice.invoice_number} is void and cannot be changed.', f'Invoice {invoice.invoice_number} sudah void dan tidak bisa diubah.'))
        return redirect('invoice_detail', pk=pk)

    if request.method == "POST":
        def _res_snapshot(inv):
            rows = [
                f"{r.hotel} {r.check_in}–{r.check_out} ({int(r.total_sar or 0)} SAR)"
                for r in inv.reservations.order_by('id')
            ]
            return ' | '.join(rows) if rows else '—'

        _before = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date'])
        _res_before = _res_snapshot(invoice)
        new_number = request.POST.get("invoice_number", "").strip() or invoice.invoice_number

        def _reject(errors):
            return inertia_render(request, "Invoice/Form", props={
                "edit": True,
                "invoice": _serialize_hotel_invoice(invoice),
                "cl_data": _cl_data_for_form(request.user, invoice),
                "clients": _client_options(request.user),
                "branch_choices": _branch_choices(request.user),
                "initial": _invoice_echo(request),
                "errors": errors,
            })

        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            return _reject({"invoice_number": f"Invoice number '{new_number}' is already in use."})

        cl_ids = _billable_cl_ids(request, invoice)
        client = _resolve_client_from_post(request)
        errors = _validate_hotel_invoice(request, cl_ids, client)
        if errors:
            return _reject(errors)

        try:
            with transaction.atomic():
                # Lines first: a client change is only legal together with a
                # full swap of the reservations billed, and the old lines must
                # be off the invoice before its client moves.
                if client.pk != invoice.client_id:
                    _sync_hotel_lines(invoice, [], request.user)
                invoice.invoice_number = new_number
                invoice.client = client
                invoice.branch_id = _posted_branch(request, client, current=invoice.branch_id)
                issued_d = _parse_date(request.POST.get("issued_date"))
                invoice.issued_date = issued_d
                invoice.due_date = _parse_date(request.POST.get("due_date"))
                invoice.save()
                Invoice.claim_number(InvoiceType.HOTEL, invoice.invoice_number, issued_date=issued_d or invoice.issued_date)
                _sync_hotel_lines(invoice, cl_ids, request.user)
        except (FinanceError, ValueError) as e:
            # A finance failure (e.g. PeriodLockedError when a payment falls in a
            # closed period) must roll back cleanly and show the user a form error,
            # not a raw 500.
            return _reject({"finance": str(e)})
        _after = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date'])
        _res_after = _res_snapshot(invoice)
        changes = track_changes(
            {**_before, 'reservations': _res_before},
            {**_after, 'reservations': _res_after},
            labels={'customer_name': 'Customer Name', 'invoice_number': 'Invoice No.', 'issued_date': 'Issued Date', 'due_date': 'Due Date', 'reservations': 'Reservations'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Hotel', invoice.invoice_number, changes)
        messages.success(request, tr(request, f"Invoice {invoice.invoice_number} updated.", f"Invoice {invoice.invoice_number} diperbarui."))
        return redirect("invoice_detail", pk=invoice.pk)

    return inertia_render(request, "Invoice/Form", props={
        "edit": True,
        "invoice": _serialize_hotel_invoice(invoice),
        "cl_data": _cl_data_for_form(request.user, invoice),
        "clients": _client_options(request.user),
        "branch_choices": _branch_choices(request.user),
    })


@require_perm('invoice', 'delete')
def invoice_delete(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.filter(invoice_type=InvoiceType.HOTEL), request.user, pk=pk)
    if request.method == "POST":
        num = invoice.invoice_number
        # System of record: invoice yang sudah menyentuh general ledger
        # (charge/payment) tidak boleh hilang dari riwayat keuangan.
        from ..models.journal import JournalLine
        if JournalLine.objects.filter(invoice=invoice).exists():
            messages.error(request, tr(request, f'Invoice {num} is in the financial journal and cannot be deleted.', f'Invoice {num} tidak bisa dihapus karena sudah tercatat di jurnal keuangan.'))
            return redirect('invoice_detail', pk=pk)
        try:
            with transaction.atomic():
                invoice.lines.all().delete()
                invoice.delete()
        except Exception as exc:
            # A pending PaymentRecord (PROTECT) may still exist even when no
            # journal lines were written; surface that cleanly instead of a 500.
            from django.db.models.deletion import ProtectedError
            if isinstance(exc, ProtectedError):
                messages.error(
                    request,
                    tr(request, f'Invoice {num} still has payments recorded against it and cannot be deleted. Void or reverse those payments first.', f'Invoice {num} tidak bisa dihapus karena masih punya pembayaran terkait. Batalkan/balik pembayarannya dulu.'),
                )
                return redirect('invoice_detail', pk=pk)
            raise
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Hotel', num)
        messages.success(request, tr(request, f"Invoice {num} deleted.", f"Invoice {num} dihapus."))
        return redirect("invoice_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("invoice_list")


@require_perm('invoice', 'export')
def invoice_pdf(request, pk):
    invoice = get_in_scope_or_404(Invoice.objects.filter(invoice_type=InvoiceType.HOTEL), request.user, pk=pk)
    return _render_invoice_pdf(invoice)


@require_perm('invoice', 'export')
def invoice_list_pdf(request):
    base_qs = _hotel_invoices(request).with_lines()
    qs, _ = _filter_invoice_qs(base_qs, request)
    inv_list = list(qs)
    total_sar = sum(i.total_sar for i in inv_list)
    total_remaining = sum(i.remaining_sar for i in inv_list)
    return _render_list_pdf(
        request, qs,
        template="hw/invoice/invoice_list_pdf.html",
        filename="invoices_hotel.pdf",
        extra_ctx={
            "invoices": inv_list,
            "total_sar": total_sar,
            "total_paid": total_sar - total_remaining,
            "total_remaining": total_remaining,
            "logo_rel_path": _logo_file_url(),
        },
    )


@require_perm('invoice', 'export')
def invoice_export_csv(request):
    base_qs = _hotel_invoices(request).with_lines()
    qs, _ = _filter_invoice_qs(base_qs, request)
    headers = ['Invoice #', 'Customer', 'Issued Date', 'Due Date', 'Total SAR', 'Paid SAR', 'Sisa SAR']
    rows = ([
        inv.invoice_number, inv.customer_name,
        inv.issued_date or '', inv.due_date or '',
        inv.total_sar, inv.total_sar - inv.remaining_sar, inv.remaining_sar,
    ] for inv in qs)
    return csv_export_response('invoices_hotel.csv', headers, rows)


def _line_has_money(line):
    """Whether money already stands against this invoice line: a payment (or
    one still pending), an allocation, or an active credit note. Such a line
    cannot leave the invoice; the money has to be moved or reversed first."""
    from ..models.credit_note import CreditNote, CreditNoteLine
    from ..models.payment import PaymentAllocation, PaymentRecord
    open_statuses = (*PaymentRecord.EFFECTIVE_STATUSES, PaymentRecord.STATUS_PENDING)
    settled = fq.line_settled_sar(line.pk)
    return (
        PaymentAllocation.objects.filter(payment__status__in=open_statuses, invoice_line=line).exists()
        or bool(settled)
        or CreditNoteLine.objects.filter(invoice_line=line, credit_note__status=CreditNote.STATUS_ACTIVE).exists()
    )


def _line_is_referenced(line, column=None):
    """Whether any row points at this line (journal, payments, credit notes).
    A referenced line is voided instead of deleted, so that history keeps its key."""
    from ..models.credit_note import CreditNoteLine
    from ..models.journal import JournalLine
    from ..models.payment import PaymentAllocation
    if column == 'penalty_line':
        return (
            JournalLine.objects.filter(invoice_id=line.invoice_id, penalty_id=line.penalty_id).exists()
            or CreditNoteLine.objects.filter(invoice_line=line).exists()
        )
    return (
        JournalLine.objects.filter(invoice_line=line).exists()
        or PaymentAllocation.objects.filter(invoice_line=line).exists()
        or CreditNoteLine.objects.filter(invoice_line=line).exists()
    )


def _line_has_service_money(line):
    return _line_has_money(line)


def _line_is_service_referenced(line):
    return _line_is_referenced(line)


def _sync_hotel_lines(invoice, cl_ids, user):
    """Make the invoice bill exactly the reservations in `cl_ids`, then
    re-post its charge (posting.post_invoice_charge, idempotent by content).

    A hotel line carries no figures of its own: what it bills is read from its
    CL. A reservation taken off the invoice loses its line only when nothing
    references it; once the ledger does, the line is voided (kept, no longer
    billed), and when money stands against it the save is refused.
    """
    from ..finance.posting import post_invoice_charge

    with transaction.atomic():
        wanted = list(ConfirmationLetter.objects.filter(pk__in=cl_ids).select_related('client', 'hotel'))
        wanted_ids = {cl.pk for cl in wanted}
        for line in invoice.lines.filter(kind=InvoiceLine.KIND_HOTEL, voided_at__isnull=True):
            if line.confirmation_letter_id in wanted_ids:
                continue
            if _line_has_money(line):
                raise ValueError(
                    f"Reservasi {line.reservation_number} sudah tersentuh pembayaran, "
                    "jadi tidak bisa dikeluarkan dari invoice. Realokasi atau balikkan "
                    "pembayarannya dulu lewat modul Payment."
                )
            for pen_line in invoice.lines.filter(
                kind=InvoiceLine.KIND_PENALTY, penalty__cl_id=line.confirmation_letter_id, voided_at__isnull=True,
            ):
                pen_line.void() if _line_is_referenced(pen_line, 'penalty_line') else pen_line.delete()
            if _line_is_referenced(line):
                line.void()
            else:
                line.delete()
        for cl in wanted:
            invoice.add_hotel_line(cl)
        post_invoice_charge(invoice, created_by=user)
    logger.info(
        "ledger: %d reservation(s) synced for invoice %s",
        len(wanted), invoice.invoice_number,
    )


def _invoice_echo(request):
    """Echo submitted values (incl. JSON arrays) back to the form on error."""
    def _loads(key):
        try:
            return json.loads(request.POST.get(key, "[]"))
        except (ValueError, TypeError):
            return []
    return {
        # No "company" key — the form no longer submits one and the server
        # assigns it from the session, so there is nothing to echo back.
        "client_id": request.POST.get("client_id", ""),
        "customer_name": request.POST.get("customer_name", ""),
        "invoice_number": request.POST.get("invoice_number", ""),
        "issued_date": request.POST.get("issued_date", ""),
        "due_date": request.POST.get("due_date", ""),
        "branch": request.POST.get("branch", ""),
        "reservations": _loads("reservations"),
        "payments": _loads("payments"),
        "linked_cl_ids": _loads("linked_cl_ids"),
    }


def _serialize_hotel_invoice(invoice):
    """Invoice + reservations + payments serialized for the React form."""
    return {
        "pk": invoice.pk,
        "client_id": invoice.client_id or "",
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "issued_date": invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "",
        "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        "branch": invoice.branch_id or "",
        # Read-only figures for the form's summary rail — payments themselves are
        # recorded through the Payment module, not this form.
        "total_sar": invoice.total_sar,
        "paid_sar": invoice.total_paid_sar,
        "remaining_sar": invoice.remaining_sar,
        "reservations": [{
            "reservation_number": r.reservation_number,
            "hotel": r.hotel,
            "check_in": r.check_in.strftime("%Y-%m-%d") if r.check_in else "",
            "check_out": r.check_out.strftime("%Y-%m-%d") if r.check_out else "",
            "reservation_total": int(r.total_sar or 0),
        } for r in invoice.reservations],
        "payments": [{
            "ref": p["ref"],
            "date": p["payment_date"].strftime("%Y-%m-%d") if p["payment_date"] else "",
            "method": p["method"] or "Cash",
            "amount": float(p["amount"]),
            "amount_sar": p["amount_sar"],
            "currency": p["currency"],
            "exchange": p["exchange_rate"],
            "note": p["note"],
            "proof_keep": p["proof"].name if p["proof"] else "",
            "proof_url": p["proof"].url if p["proof"] else None,
        } for p in fq.payment_history_rows(invoice)],
        "linked_cl_ids": list(invoice.confirmation_letters.values_list("pk", flat=True)),
    }


def _parse_cl_ids(request):
    try:
        ids = json.loads(request.POST.get("linked_cl_ids", "[]"))
    except (ValueError, TypeError):
        ids = []
    return [i for i in ids if i]


def _billable_cl_ids(request, invoice=None):
    """CL pks from the POST this invoice may bill: either not yet on any
    invoice or already on this one (edit). A hotel invoice can only be built
    from existing confirmation letters — there is no manual line."""
    ids = _parse_cl_ids(request)
    if not ids:
        return []
    free = scope(ConfirmationLetter.objects.uninvoiced(), request.user).filter(pk__in=ids)
    allowed = set(free.values_list("pk", flat=True))
    if invoice is not None:
        allowed |= set(invoice.confirmation_letters.filter(pk__in=ids).values_list("pk", flat=True))
    return [i for i in ids if i in allowed]


def _validate_hotel_invoice(request, cl_ids, client):
    """{field: message} for a hotel invoice form. A hotel invoice bills one
    client's reservations, so it needs the client and at least one CL of theirs."""
    if not cl_ids:
        return {"reservations": "Pick at least one confirmation letter that isn't already on an invoice."}
    if client is None:
        return {"client_id": "Choose the client this invoice bills."}
    others = (
        ConfirmationLetter.objects.filter(pk__in=cl_ids).exclude(client=client)
        .values_list("confirmation_number", flat=True)
    )
    if others:
        return {"reservations": (
            f"CL {', '.join(others)} belongs to another client. One invoice bills one client."
        )}
    return {}


def _cl_data_for_form(user, invoice=None):
    # prefetch_related("rooms"): `total` below reads cl.total_price, which sums
    # cl.rooms.all() — one extra query per CL without this, i.e. up to 100 on
    # the [:100] slice. It made /invoice/new/ and /invoice/<pk>/edit/ issue 56
    # queries against 7-12 for every other form, and they are the two slowest
    # form endpoints in the app by roughly 10x. Room.subtotal also walks back to
    # room.cl for num_nights; a reverse-FK prefetch populates that back
    # reference, so it stays free.
    # What the form can bill: CLs on no invoice yet, plus (editing) the ones
    # already on this invoice.
    ids = set(scope(ConfirmationLetter.objects.uninvoiced(), user).values_list("pk", flat=True))
    if invoice is not None:
        ids |= set(invoice.confirmation_letters.values_list("pk", flat=True))
    cl_qs = (scope(ConfirmationLetter.objects.filter(pk__in=ids), user)
             .select_related("client", "hotel")
             .with_invoice()
             .prefetch_related("rooms"))
    return [{
        "id": cl.pk,
        "ref": cl.confirmation_number,
        "guest": cl.guest_name,
        "hotel": cl.hotel_name or "-",
        "check_in": cl.check_in.isoformat() if cl.check_in else "",
        "check_out": cl.check_out.isoformat() if cl.check_out else "",
        "total": int(round(cl.total_price)) if cl.total_price else 0,
        "inv": cl.invoice.invoice_number if cl.invoice_id else "",
        "client_id": cl.client_id or "",
        "client_name": cl.client.name,
    } for cl in cl_qs.order_by("check_in", "confirmation_number")[:500]]
