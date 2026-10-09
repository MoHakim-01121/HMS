import json
import logging
from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect

from inertia import render as inertia_render

from ..models import ActivityLog, Client, Invoice, InvoiceLine, log_activity
from ..branch_scope import get_in_scope_or_404, scope
from ..permissions import require_perm
from ..finance import queries as fq
from ..finance.errors import FinanceError
from ..finance.posting import post_invoice_charge
from .context import _build_visa_payments_context, _build_visa_services_context
from .credit_note_views import invoice_credit_props
from .helpers import (
    _client_options,
    _is_mobile,
    _parse_date,
    _render_list_pdf,
    _to_float,
    csv_export_response,
    due_soon_alert,
    pagination_props,
    snapshot_fields,
    track_changes,
)
from .invoice_billing import _billing_props
from .pdf import _render_services_pdf

logger = logging.getLogger(__name__)


def _resolve_client_from_post(request):
    """Resolve Client from the submitted client_id."""
    client_id = request.POST.get("client_id")
    if client_id:
        try:
            return scope(Client.objects.all(), request.user).get(pk=client_id, is_active=True)
        except (Client.DoesNotExist, ValueError):
            pass
    return None


def _service_invoices(request):
    """Services (visa) invoices issued by the user's branches."""
    return scope(Invoice.objects.filter(invoice_type='visa'), request.user)


def _get_service_invoice(request, pk):
    """Fetch a visa invoice of the user's branches (404 otherwise)."""
    return get_in_scope_or_404(_service_invoices(request), request.user, pk=pk)


@require_perm('services', 'view')
def services_list(request):
    qs = _service_invoices(request).with_lines()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Invoice.objects.name_matches(q))

    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    invoices = [{
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "customer_name": inv.customer_name,
        "currency": inv.currency,
        # Same figure as the detail page: sum of the items, in the invoice currency.
        "total": inv.total_sar,
        "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
        "created_at": inv.created_at.strftime("%d/%m/%Y"),
    } for inv in page_obj]
    return inertia_render(request, "Services/List", props={
        "invoices": invoices,
        "total_count": paginator.count,
        "q": q,
        "pagination": pagination_props(page_obj),
    })


@require_perm('services', 'create')
def services_new(request):
    suggested_number = Invoice.suggest_number("visa")
    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")

        def _reject(errors):
            return inertia_render(request, "Services/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": suggested_number,
                "clients": _client_options(request.user),
                "initial": _services_echo(request),
                "errors": errors,
            })

        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return _reject({"invoice_number": f"Invoice number '{invoice_number}' is already in use."})
        client = _resolve_client_from_post(request)
        errors = _validate_service_invoice(request, client)
        if errors:
            return _reject(errors)

        try:
            with transaction.atomic():
                # A services invoice belongs to the branch that owns the client.
                invoice = Invoice.objects.create(
                    invoice_type="visa",
                    invoice_number=invoice_number,
                    client=client,
                    branch_id=client.owner_branch_id,
                    issued_date=_parse_date(request.POST.get("issued_date")),
                    due_date=_parse_date(request.POST.get("due_date")),
                    currency=(request.POST.get("invoice_currency") or "USD").upper(),
                    created_by=request.user,
                )
                Invoice.claim_number("visa", invoice.invoice_number)
                _save_service_items(invoice, request)
        except (FinanceError, ValueError) as e:
            return _reject({"finance": str(e)})
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Services', invoice.invoice_number)
        messages.success(request, f"Services Invoice {invoice.invoice_number} created successfully.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "clients": _client_options(request.user),
    })


@require_perm('services', 'view')
def services_detail(request, pk):
    invoice = _get_service_invoice(request, pk)
    visa_services = _build_visa_services_context(invoice)
    payments_raw = _build_visa_payments_context(invoice)
    services_remaining = sum(s["remaining"] for s in visa_services)
    # linked_number and amount_main mirror Invoice/Detail's payments payload:
    # the service a payment settles is the only reference it carries, and the
    # converted figure is what the totals column adds up.
    payments_history = [{
        "linked_number": p["linked_number"],
        "payment_date": p["payment_date"].strftime("%d/%m/%Y") if p["payment_date"] else None,
        "payment_method": p["payment_method"],
        "payment_amount": p["payment_amount"],
        "payment_amount_main": int(round(p["payment_amount_main"])),
        "payment_currency": p["payment_currency"],
        "payment_exchange": f"{float(p['payment_exchange']):.2f}",
        "payment_note": p["payment_note"],
        "proof_url": p["proof"].url if p["proof"] else None,
    } for p in payments_raw]

    due_alert = due_soon_alert(invoice.due_date, services_remaining)

    return inertia_render(request, "Services/Detail", props={
        "invoice": {
            "pk": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "customer_name": invoice.customer_name,
            "currency": invoice.currency,
            "issued_date": invoice.issued_date.strftime("%d %b %Y") if invoice.issued_date else None,
            "due_date": invoice.due_date.strftime("%d %b %Y") if invoice.due_date else None,
            "created_at": invoice.created_at.strftime("%d/%m/%Y %H:%M"),
            "status": invoice.status,
        },
        "visa_services": visa_services,
        "payments_history": payments_history,
        "services_remaining": services_remaining,
        "due_alert": due_alert,
        **_billing_props(invoice),
        **invoice_credit_props(invoice),
    })


@require_perm('services', 'edit')
def services_edit(request, pk):
    invoice = _get_service_invoice(request, pk)
    if invoice.is_void:
        messages.error(request, f'Invoice {invoice.invoice_number} sudah void dan tidak bisa diubah.')
        return redirect('services_detail', pk=pk)

    if request.method == "POST":
        _before = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date', 'currency'])
        new_number = request.POST.get("invoice_number", "")

        def _reject(errors):
            echo = _services_echo(request)
            echo["pk"] = invoice.pk
            return inertia_render(request, "Services/Form", props={
                "edit": True,
                "invoice": _serialize_service_invoice(invoice),
                "clients": _client_options(request.user),
                "initial": echo,
                "errors": errors,
            })

        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            return _reject({"invoice_number": f"Invoice number '{new_number}' is already in use."})
        client = _resolve_client_from_post(request)
        errors = _validate_service_invoice(request, client)
        if errors:
            return _reject(errors)

        try:
            with transaction.atomic():
                invoice.invoice_number = new_number
                invoice.client = client
                invoice.issued_date = _parse_date(request.POST.get("issued_date"))
                invoice.due_date = _parse_date(request.POST.get("due_date"))
                invoice.currency = (request.POST.get("invoice_currency") or "USD").upper()
                invoice.save()
                Invoice.claim_number("visa", invoice.invoice_number)
                _save_service_items(invoice, request)
        except (FinanceError, ValueError) as e:
            invoice.refresh_from_db()
            return _reject({"finance": str(e)})
        _after = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date', 'currency'])
        changes = track_changes(
            _before, _after,
            labels={'customer_name': 'Customer Name', 'invoice_number': 'Invoice No.', 'issued_date': 'Issued Date', 'due_date': 'Due Date', 'currency': 'Currency'},
        )
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Invoice Services', invoice.invoice_number, changes)
        messages.success(request, f"Services Invoice {invoice.invoice_number} updated successfully.")
        return redirect("services_detail", pk=invoice.pk)

    return inertia_render(request, "Services/Form", props={
        "edit": True,
        "invoice": _serialize_service_invoice(invoice),
        "clients": _client_options(request.user),
    })


@require_perm('services', 'delete')
def services_delete(request, pk):
    invoice = _get_service_invoice(request, pk)
    if request.method == "POST":
        num = invoice.invoice_number
        # System of record: invoice yang sudah menyentuh general ledger
        # tidak boleh hilang dari riwayat keuangan.
        from ..models.journal import JournalLine
        if JournalLine.objects.filter(invoice=invoice).exists():
            messages.error(request, f'Invoice {num} tidak bisa dihapus karena sudah tercatat di jurnal keuangan.')
            return redirect('services_detail', pk=pk)
        with transaction.atomic():
            invoice.lines.all().delete()
            invoice.delete()
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Services', num)
        messages.success(request, f"Services Invoice {num} deleted successfully.")
        return redirect("services_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("services_list")


@require_perm('services', 'export')
def services_pdf(request, pk):
    invoice = _get_service_invoice(request, pk)
    return _render_services_pdf(invoice)


@require_perm('services', 'export')
def services_list_pdf(request):
    qs = _service_invoices(request)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Invoice.objects.name_matches(q))
    return _render_list_pdf(
        request, qs,
        template="hw/services/services_list_pdf.html",
        filename="invoices_services.pdf",
        extra_ctx={"invoices": list(qs)},
    )


@require_perm('services', 'export')
def services_export_csv(request):
    qs = _service_invoices(request)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Invoice.objects.name_matches(q))
    headers = ['Invoice #', 'Customer', 'Currency', 'Issued Date', 'Due Date']
    rows = ([
        inv.invoice_number, inv.customer_name,
        inv.currency, inv.issued_date or '', inv.due_date or '',
    ] for inv in qs)
    return csv_export_response('invoices_services.csv', headers, rows)


@require_perm('services', 'create')
@transaction.atomic
def services_duplicate(request, pk):
    original = _get_service_invoice(request, pk)
    new_num = Invoice.generate_number("visa")
    today = date.today()
    new_inv = Invoice.objects.create(
        invoice_type="visa",
        invoice_number=new_num,
        client_id=original.client_id,
        branch_id=original.branch_id,
        issued_date=today,
        due_date=today + timedelta(days=30),
        currency=original.currency,
        created_by=request.user,
    )
    for item in original.service_items:
        new_inv.add_service_line(item.description, item.quantity, item.unit_price)
    post_invoice_charge(new_inv, created_by=request.user)
    messages.success(request, f"Services Invoice duplicated as {new_num} (from {original.invoice_number}).")
    return redirect("services_edit", pk=new_inv.pk)


def _save_service_items(invoice, request):
    """Make the invoice's service lines match the submitted rows, then re-post
    its charge (DR Piutang / CR Pendapatan Services, idempotent by content).

    Rows are matched to existing lines by `service_number` (rows without one
    are matched in order), and a matched line is updated in place: its key is
    what the ledger, payment allocations and credit notes point at. A line
    that was dropped is deleted only when nothing references it; otherwise it
    is voided, and refused outright when money stands against it.
    """
    from ..finance.posting import post_invoice_charge
    from .invoice_views import _line_has_service_money, _line_is_service_referenced

    try:
        rows = json.loads(request.POST.get("service_items", "[]"))
    except (ValueError, TypeError):
        rows = []
    rows = [r for r in rows if isinstance(r, dict) and (r.get("name") or "").strip()]

    with transaction.atomic():
        existing = list(invoice.lines.filter(kind=InvoiceLine.KIND_SERVICE, voided_at__isnull=True).order_by('line_no'))
        by_number = {line.line_no: line for line in existing}
        matched = []
        for r in rows:
            try:
                number = int(r.get("service_number") or 0)
            except (TypeError, ValueError):
                number = 0
            matched.append(by_number.pop(number, None))
        spare = sorted(by_number.values(), key=lambda line: line.line_no)
        for i, line in enumerate(matched):
            if line is None and spare and not rows[i].get("service_number"):
                matched[i] = spare.pop(0)

        for line in spare:
            if _line_has_service_money(line):
                raise ValueError(
                    f"Service #{line.line_no} {line.description} sudah tersentuh pembayaran, "
                    "jadi tidak bisa dihapus dari invoice. Balikkan pembayarannya dulu lewat modul Payment."
                )
            if _line_is_service_referenced(line):
                line.void()
            else:
                line.delete()

        for r, line in zip(rows, matched):
            name = r["name"].strip()
            qty_raw, price_raw = _to_float(r.get("qty"), 1) or 1, _to_float(r.get("price"))
            if qty_raw != int(qty_raw) or price_raw != int(price_raw) or qty_raw < 1 or price_raw < 0:
                # Money is kept in whole units; a fraction would be dropped silently.
                raise ValueError(f"{name}: jumlah dan harga harus bilangan bulat, tanpa desimal.")
            qty, price = int(qty_raw), int(price_raw)
            if line is None:
                invoice.add_service_line(name, qty, price)
            elif (line.description, line.quantity, line.unit_price) != (name, qty, price):
                line.description, line.quantity, line.unit_price = name, qty, price
                line.save(update_fields=['description', 'quantity', 'unit_price'])
        post_invoice_charge(invoice, created_by=request.user)
    logger.info(
        "ledger: %d service item(s) synced for invoice %s",
        len(rows), invoice.invoice_number,
    )


def _validate_service_invoice(request, client):
    """{field: message} for a services invoice form."""
    from ..models.currency import CURRENCY_CODES
    if client is None:
        return {"client_id": "Choose the client this invoice bills."}
    if (request.POST.get("invoice_currency") or "USD").upper() not in CURRENCY_CODES:
        return {"invoice_currency": "Choose SAR, USD or IDR."}
    return {}


def _services_echo(request):
    """Echo submitted values (incl. JSON arrays) back to the form on error."""
    try:
        items = json.loads(request.POST.get("service_items", "[]"))
    except (ValueError, TypeError):
        items = []
    try:
        pays = json.loads(request.POST.get("payments", "[]"))
    except (ValueError, TypeError):
        pays = []
    return {
        "client_id": request.POST.get("client_id", ""),
        "customer_name": request.POST.get("customer_name", ""),
        "invoice_number": request.POST.get("invoice_number", ""),
        "invoice_currency": request.POST.get("invoice_currency", "USD"),
        "issued_date": request.POST.get("issued_date", ""),
        "due_date": request.POST.get("due_date", ""),
        "service_items": items,
        "payments": pays,
    }


def _serialize_service_invoice(invoice):
    """Invoice + service items + payments serialized for the React form."""
    return {
        "pk": invoice.pk,
        "client_id": invoice.client_id or "",
        "customer_name": invoice.customer_name,
        "invoice_number": invoice.invoice_number,
        "invoice_currency": invoice.currency,
        "issued_date": invoice.issued_date.strftime("%Y-%m-%d") if invoice.issued_date else "",
        "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "",
        "service_items": [{
            "service_number": it.service_number,
            "name": it.name,
            "qty": it.qty,
            "price": float(it.price),
        } for it in invoice.service_items],
        "payments": [{
            "ref": p["ref"],
            "date": p["payment_date"].strftime("%Y-%m-%d") if p["payment_date"] else "",
            "method": p["method"],
            "amount": float(p["amount"]),
            "currency": p["currency"],
            "exchange": p["exchange_rate"],
            "note": p["note"],
            "proof_keep": p["proof"].name if p["proof"] else "",
            "proof_url": p["proof"].url if p["proof"] else None,
        } for p in fq.payment_history_rows(invoice)],
    }
