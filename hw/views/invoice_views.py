import csv
import json
import logging
from datetime import date, timedelta
from django.utils import timezone

from django.contrib import messages
from django.db import transaction
from django.db.models import ExpressionWrapper, F, FloatField, Q
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models import ActivityLog, Client, Company, ConfirmationLetter, Invoice, Reservation, log_activity
from ..permissions import require_perm
from ..utils import convert_to_sar
from .context import _build_reservation_context
from .helpers import (
    _is_mobile,
    _page_range_display,
    _parse_date,
    _render_list_pdf,
    _to_float,
    get_active_company,
)
from .invoice_billing import _billing_client, _billing_props, _save_hotel_payments
from .pdf import _logo_file_url, _render_invoice_pdf

logger = logging.getLogger(__name__)


def _client_options(active_company):
    return list(
        Client.objects.filter(company=active_company, is_active=True)
        .order_by('name').values('id', 'name')
    )


def _resolve_client_from_post(request, active_company):
    """Resolve Client from the submitted client_id, or from linked CLs as fallback."""
    client_id = request.POST.get("client_id")
    if client_id:
        try:
            return Client.objects.get(pk=client_id, company=active_company, is_active=True)
        except (Client.DoesNotExist, ValueError):
            pass
    # Fallback: resolve from linked CLs
    cl_ids = _parse_cl_ids(request)
    if cl_ids:
        cl_clients = set(
            ConfirmationLetter.objects.filter(pk__in=cl_ids)
            .exclude(client__isnull=True).values_list('client_id', flat=True)
        )
        if len(cl_clients) == 1:
            try:
                return Client.objects.get(pk=next(iter(cl_clients)))
            except Client.DoesNotExist:
                pass
    return None


def _filter_by_status(qs, status):
    """Filter a hotel Invoice queryset by payment status (lunas/belum/partial).

    Done in Python, not SQL: total_paid_sar needs per-payment currency
    conversion, which isn't expressible as a queryset filter.
    """
    if status not in ('lunas', 'belum', 'partial'):
        return qs
    filtered_ids = []
    for inv in qs:
        paid = inv.total_paid_sar
        if status == 'lunas' and paid >= inv.total_sar:
            filtered_ids.append(inv.pk)
        elif status == 'belum' and paid < 1:
            filtered_ids.append(inv.pk)
        elif status == 'partial' and paid >= 1 and paid < inv.total_sar:
            filtered_ids.append(inv.pk)
    return qs.filter(pk__in=filtered_ids)


@require_perm('invoice', 'view')
def invoice_list(request):
    active_company = get_active_company(request)
    base_qs = Invoice.objects.filter(
        invoice_type="hotel", company=active_company
    ).prefetch_related('reservations', 'payments')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    due_soon = request.GET.get('due_soon')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    qs = base_qs
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    if due_soon:
        threshold = date.today() + timedelta(days=7)
        qs = qs.filter(due_date__lte=threshold, due_date__gte=date.today())
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)
    qs = _filter_by_status(qs, status)

    qs = qs.order_by(F('due_date').asc(nulls_last=True), '-created_at')

    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    invoices = [{
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "customer_name": inv.customer_name,
        "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
        "due_date": inv.due_date.strftime("%d/%m/%Y") if inv.due_date else None,
        "created_at": inv.created_at.strftime("%d/%m/%Y"),
        "total_sar": inv.total_sar,
        "remaining_sar": inv.remaining_sar,
        "status": (
            "overpaid" if inv.remaining_sar < 0
            else "paid" if inv.remaining_sar == 0
            else "partial" if inv.remaining_sar < inv.total_sar
            else "unpaid"
        ),
    } for inv in page_obj]

    props = {
        "invoices": invoices,
        "total_count": paginator.count,
        "q": q,
        "status_filter": status,
        "date_from": date_from,
        "date_to": date_to,
        "pagination": {
            "number": page_obj.number,
            "num_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
            "has_other_pages": page_obj.has_other_pages(),
            "range": _page_range_display(page_obj),
            "start_index": page_obj.start_index(),
            "end_index": page_obj.end_index(),
            "count": paginator.count,
        },
    }
    if active_company == 'konoz':
        props["remit_stats"] = _invoice_stats(base_qs, active_company)

    return inertia_render(request, "Invoice/List", props=props)


def _invoice_stats(invoice_qs, company):
    from .. import ledger
    from ..models import Account

    invoice_ids = list(invoice_qs.values_list('id', flat=True))
    total_tagihan = ledger.total_charge(company, invoice_ids)
    terbayar_surabaya = ledger.client_paid_to(Account.SBY, company, invoice_ids)
    terbayar_pusat = ledger.client_paid_to(Account.PUSAT, company, invoice_ids)

    return {
        'total_tagihan': total_tagihan,
        'belum_terbayar': max(0, total_tagihan - terbayar_surabaya - terbayar_pusat),
        # mengendap boleh negatif: Surabaya bisa mengirim lebih dari yang pernah
        # diterima untuk invoice-invoice ini (kredit di pusat), lihat hw/ledger.py.
        'mengendap': ledger.kas_surabaya(company, invoice_ids),
        'terbayar_surabaya': terbayar_surabaya,
        'terbayar_pusat': terbayar_pusat,
    }


@require_perm('invoice', 'create')
def invoice_new(request):
    suggested_number = Invoice.generate_number("hotel")
    active_company = get_active_company(request)

    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return inertia_render(request, "Invoice/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": invoice_number,
                "cl_data": _cl_data_for_form(active_company),
                "clients": _client_options(active_company),
                "initial": _invoice_echo(request),
                "errors": {"invoice_number": f"Invoice number '{invoice_number}' is already in use."},
            })

        with transaction.atomic():
            client = _resolve_client_from_post(request, active_company)
            invoice = Invoice.objects.create(
                # Server-assigned, never read from the POST body. The form used to
                # submit a company of its own, unchecked against can_use_company —
                # so a user restricted to one company could file a record under the
                # other, and every read path here (list/detail/edit/delete/PDF/CSV)
                # filters by the active company, meaning the row simply vanished
                # from the list it was created in.
                company=active_company,
                invoice_type="hotel",
                invoice_number=invoice_number,
                client=client,
                customer_name=client.name if client else request.POST.get("customer_name", ""),
                issued_date=_parse_date(request.POST.get("issued_date")),
                due_date=_parse_date(request.POST.get("due_date")),
                currency="SAR",
            )
            # CL must be linked before _save_reservations/_save_hotel_payments run --
            # both call _billing_client(invoice), which resolves the client from
            # invoice.confirmation_letters. Linking after would leave every Charge
            # created here with client=None even when a CL was selected.
            cl_ids = _parse_cl_ids(request)
            if cl_ids:
                ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

            _save_reservations(invoice, request)
            _save_hotel_payments(invoice, request)

        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
        return redirect("invoice_detail", pk=invoice.pk)

    return inertia_render(request, "Invoice/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "cl_data": _cl_data_for_form(active_company),
        "clients": _client_options(active_company),
    })


@require_perm('invoice', 'view')
def invoice_detail(request, pk):
    filters = {'pk': pk, 'invoice_type': 'hotel', 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
    res_ctx = _build_reservation_context(invoice)
    reservations = [{
        "number": r["number"],
        "hotel": r["hotel"],
        "check_in": r["check_in"].strftime("%d/%m/%Y") if r["check_in"] else None,
        "check_out": r["check_out"].strftime("%d/%m/%Y") if r["check_out"] else None,
        "total_int": r["total_int"],
        "remaining_int": r["remaining_int"],
        "remaining_class": r["remaining_class"],
        "cl_pk": r["cl_pk"],
    } for r in res_ctx]

    payments = [{
        "linked_number": p.linked_number,
        "payment_date": p.payment_date.strftime("%d/%m/%Y") if p.payment_date else None,
        "method": p.method,
        "amount_int": int(round(float(p.amount))),
        "currency": p.currency,
        "exchange_rate": float(p.exchange_rate),
        "exchange_rate_fmt": f"{float(p.exchange_rate):.2f}",
        "amount_sar_int": p.amount_sar,
        "proof_url": p.proof.url if p.proof else None,
        "note": p.note,
    } for p in invoice.payments.all()]

    due_alert = None
    if invoice.due_date and invoice.remaining_sar > 0:
        days = (invoice.due_date - timezone.now().date()).days
        if days < 0:
            due_alert = {"type": "red", "msg": f"Payment is {abs(days)} day(s) overdue."}
        elif days == 0:
            due_alert = {"type": "red", "msg": "Due today!"}
        elif days <= 7:
            due_alert = {"type": "yellow", "msg": f"Due in {days} day(s)."}

    return inertia_render(request, "Invoice/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "issued_date": invoice.issued_date.strftime("%d %b %Y") if invoice.issued_date else None,
            "total_sar": invoice.total_sar,
            "total_paid_sar": invoice.total_paid_sar,
            "remaining_sar": invoice.remaining_sar,
        },
        "reservations": reservations,
        "payments": payments,
        "due_alert": due_alert,
        **_billing_props(invoice),
    })


@require_perm('invoice', 'edit')
def invoice_edit(request, pk):
    active_company = get_active_company(request)
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type='hotel', company=active_company)

    if request.method == "POST":
        def _res_snapshot(inv):
            rows = [
                f"{r.hotel} {r.check_in}–{r.check_out} ({int(r.total_sar or 0)} SAR)"
                for r in inv.reservations.order_by('id')
            ]
            return ' | '.join(rows) if rows else '—'

        _before = {
            'Customer Name':    invoice.customer_name,
            'Invoice No.':      invoice.invoice_number,
            'Issued Date':      str(invoice.issued_date or ''),
            'Due Date':         str(invoice.due_date or ''),
            'Company':          invoice.company,
            'Reservations':     _res_snapshot(invoice),
        }
        new_number = request.POST.get("invoice_number", "")
        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            return inertia_render(request, "Invoice/Form", props={
                "edit": True,
                "invoice": _serialize_hotel_invoice(invoice),
                "cl_data": _cl_data_for_form(active_company),
                "clients": _client_options(active_company),
                "initial": _invoice_echo(request),
                "errors": {"invoice_number": f"Invoice number '{new_number}' is already in use."},
            })

        # invoice.company is deliberately left alone: the fetch above already
        # constrains it to active_company, so any value arriving in the POST
        # body could only ever move the record OUT of the caller's own scope.
        with transaction.atomic():
            client = _resolve_client_from_post(request, active_company)
            invoice.invoice_number = new_number
            invoice.client = client
            invoice.customer_name = client.name if client else request.POST.get("customer_name", "")
            invoice.issued_date = _parse_date(request.POST.get("issued_date"))
            invoice.due_date = _parse_date(request.POST.get("due_date"))
            invoice.save()

            invoice.reservations.all().delete()
            invoice.payments.all().delete()

            # Relink CL selection before recreating reservations/payments -- see
            # the matching comment in invoice_new for why the order matters.
            cl_ids = _parse_cl_ids(request)
            ConfirmationLetter.objects.filter(invoice=invoice).update(invoice=None)
            if cl_ids:
                ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

            _save_reservations(invoice, request)
            _save_hotel_payments(invoice, request)
        _after = {
            'Customer Name':    invoice.customer_name,
            'Invoice No.':      invoice.invoice_number,
            'Issued Date':      str(invoice.issued_date or ''),
            'Due Date':         str(invoice.due_date or ''),
            'Company':          invoice.company,
            'Reservations':     _res_snapshot(invoice),
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Hotel', invoice.invoice_number, invoice.company, changes)
        messages.success(request, f"Invoice {invoice.invoice_number} updated successfully.")
        return redirect("invoice_detail", pk=invoice.pk)

    return inertia_render(request, "Invoice/Form", props={
        "edit": True,
        "invoice": _serialize_hotel_invoice(invoice),
        "cl_data": _cl_data_for_form(active_company),
        "clients": _client_options(active_company),
    })


@require_perm('invoice', 'delete')
def invoice_delete(request, pk):
    filters = {'pk': pk, 'invoice_type': 'hotel', 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
    if request.method == "POST":
        num = invoice.invoice_number
        # System of record: menghapus invoice meng-cascade Reservations →
        # Charges (ledger). Dokumen yang sudah tercatat di ledger tidak boleh
        # hilang diam-diam dari riwayat keuangan.
        from ..models import Charge, Allocation, CashMovement
        has_ledger = (
            Charge.objects.filter(invoice=invoice).exists()
            or Allocation.objects.filter(invoice=invoice).exists()
            or CashMovement.objects.filter(invoice=invoice).exists()
        )
        if has_ledger:
            messages.error(request, f'Invoice {num} tidak bisa dihapus karena sudah tercatat di ledger keuangan.')
            return redirect('invoice_detail', pk=pk)
        invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Hotel', num, invoice.company)
        messages.success(request, f"Invoice {num} deleted successfully.")
        return redirect("invoice_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("invoice_list")


@require_perm('invoice', 'export')
def invoice_pdf(request, pk):
    filters = {'pk': pk, 'invoice_type': 'hotel', 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
    return _render_invoice_pdf(invoice)


@require_perm('invoice', 'export')
def invoice_list_pdf(request):
    active_company = get_active_company(request)
    qs = Invoice.objects.filter(invoice_type="hotel", company=active_company).prefetch_related('reservations')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)
    qs = _filter_by_status(qs, status)
    qs = qs.order_by(F('due_date').asc(nulls_last=True), '-created_at')
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
            "logo_rel_path": _logo_file_url(active_company),
            "company_label": dict(Company.choices).get(active_company, active_company),
        },
    )


@require_perm('invoice', 'export')
def invoice_export_csv(request):
    qs = Invoice.objects.filter(invoice_type="hotel", company=get_active_company(request))
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)
    qs = _filter_by_status(qs, status)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="invoices_hotel.csv"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['Invoice #', 'Company', 'Customer', 'Issued Date', 'Due Date', 'Total SAR', 'Paid SAR', 'Sisa SAR'])
    for inv in qs:
        writer.writerow([
            inv.invoice_number, inv.company, inv.customer_name,
            inv.issued_date or '', inv.due_date or '',
            inv.total_sar, inv.total_sar - inv.remaining_sar, inv.remaining_sar,
        ])
    return response


@require_perm('invoice', 'create')
def invoice_duplicate(request, pk):
    original = get_object_or_404(Invoice, pk=pk, invoice_type='hotel', company=get_active_company(request))
    new_num = Invoice.generate_number("hotel")
    today = date.today()
    new_inv = Invoice.objects.create(
        company=original.company,
        invoice_type="hotel",
        invoice_number=new_num,
        customer_name=original.customer_name,
        issued_date=today,
        due_date=today + timedelta(days=30),
        currency=original.currency,
    )
    for res in original.reservations.all():
        Reservation.objects.create(
            invoice=new_inv,
            reservation_number=res.reservation_number,
            hotel=res.hotel,
            check_in=res.check_in,
            check_out=res.check_out,
            total_sar=res.total_sar,
        )
    messages.success(request, f"Invoice duplicated as {new_num} (from {original.invoice_number}).")
    return redirect("invoice_edit", pk=new_inv.pk)


def _save_reservations(invoice, request):
    """Dual-write (remittance ledger redesign, Fase 4): the reservations array
    has no row identity either, so like _save_payments this is a full
    delete-then-recreate. Deleting the old Reservation rows already cascades
    to their Charge rows (see hw/models/ledger.py), so we only need to create
    a fresh `initial` Charge for each recreated reservation to keep
    Sum(Charge) in sync with the new total_sar cache."""
    from ..models import Charge, ChargeReason

    try:
        rows = json.loads(request.POST.get("reservations", "[]"))
    except (ValueError, TypeError):
        rows = []
    client = _billing_client(invoice)
    with transaction.atomic():
        for r in rows:
            total_sar = int(round(_to_float(r.get("reservation_total"))))
            res = Reservation.objects.create(
                invoice=invoice,
                reservation_number=(r.get("reservation_number") or "-").strip() or "-",
                hotel=(r.get("hotel") or "-").strip() or "-",
                check_in=_parse_date(r.get("check_in")),
                check_out=_parse_date(r.get("check_out")),
                total_sar=total_sar,
            )
            if total_sar:
                Charge.objects.create(
                    company=invoice.company, client=client, invoice=invoice,
                    date=invoice.issued_date or date.today(),
                    amount_sar=total_sar, reservation=res, reason=ChargeReason.INITIAL,
                    description=f'Sinkron dari reservasi {res.reservation_number}', created_by=request.user,
                )
    logger.info(
        "ledger: %d reservation(s) synced for invoice %s",
        len(rows), invoice.invoice_number,
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
        "reservations": _loads("reservations"),
        "payments": _loads("payments"),
        "linked_cl_ids": _loads("linked_cl_ids"),
    }


def _serialize_hotel_invoice(invoice):
    """Invoice + reservations + payments serialized for the React form."""
    return {
        "pk": invoice.pk,
        "company": invoice.company,
        "client_id": invoice.client_id or "",
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "issued_date": invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "",
        "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        "reservations": [{
            "reservation_number": r.reservation_number,
            "hotel": r.hotel,
            "check_in": r.check_in.strftime("%Y-%m-%d") if r.check_in else "",
            "check_out": r.check_out.strftime("%Y-%m-%d") if r.check_out else "",
            "reservation_total": int(r.total_sar or 0),
        } for r in invoice.reservations.all()],
        "payments": [{
            "ref": p.linked_number,
            "date": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else "",
            "method": p.method or "Cash",
            "amount": float(p.amount),
            "currency": p.currency,
            "exchange": float(p.exchange_rate),
            "note": p.note,
            "proof_keep": p.proof.name if p.proof else "",
            "proof_url": p.proof.url if p.proof else None,
        } for p in invoice.payments.all()],
        "linked_cl_ids": list(invoice.confirmation_letters.values_list("pk", flat=True)),
    }


def _parse_cl_ids(request):
    try:
        ids = json.loads(request.POST.get("linked_cl_ids", "[]"))
    except (ValueError, TypeError):
        ids = []
    return [i for i in ids if i]


def _cl_data_for_form(active_company):
    # prefetch_related("rooms"): `total` below reads cl.total_price, which sums
    # cl.rooms.all() — one extra query per CL without this, i.e. up to 100 on
    # the [:100] slice. It made /invoice/new/ and /invoice/<pk>/edit/ issue 56
    # queries against 7-12 for every other form, and they are the two slowest
    # form endpoints in the app by roughly 10x. Room.subtotal also walks back to
    # room.cl for num_nights; a reverse-FK prefetch populates that back
    # reference, so it stays free.
    cl_qs = (ConfirmationLetter.objects
             .select_related("invoice", "client")
             .prefetch_related("rooms")
             .filter(company=active_company))
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
        "client_name": cl.client.name if cl.client_id else "",
    } for cl in cl_qs.order_by("-created_at")[:100]]
