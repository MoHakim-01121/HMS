import json
import logging
from datetime import date, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect

from inertia import render as inertia_render

from ..models import ActivityLog, Client, Company, ConfirmationLetter, Invoice, Reservation, log_activity
from ..models.choices import InvoiceType
from ..permissions import require_perm
from ..finance import queries as fq
from ..finance.errors import FinanceError
from .context import _build_reservation_context
from .helpers import (
    _client_options,
    _is_mobile,
    _parse_date,
    _render_list_pdf,
    _to_float,
    csv_export_response,
    due_soon_alert,
    get_active_company,
    pagination_props,
    snapshot_fields,
    track_changes,
)
from .invoice_billing import _billing_client, _billing_props, _save_hotel_payments
from .pdf import _logo_file_url, _render_invoice_pdf

logger = logging.getLogger(__name__)


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
    conversion, which isn't expressible as a queryset filter. Paid amounts
    come from one bulk ledger query -- reading the total_paid_sar property
    here used to cost one ledger query per invoice.
    """
    if status not in ('lunas', 'belum', 'partial'):
        return qs
    invoices = list(qs)
    paid_map = fq.invoice_paid_map([inv.pk for inv in invoices])
    filtered_ids = []
    for inv in invoices:
        paid = paid_map.get(inv.pk, 0)
        if status == 'lunas' and paid >= inv.total_sar:
            filtered_ids.append(inv.pk)
        elif status == 'belum' and paid < 1:
            filtered_ids.append(inv.pk)
        elif status == 'partial' and paid >= 1 and paid < inv.total_sar:
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
        qs = qs.filter(Q(customer_name__icontains=q) | Q(invoice_number__icontains=q))
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)
    if apply_status:
        qs = _filter_by_status(qs, status)
    if order:
        qs = qs.order_by(F('due_date').asc(nulls_last=True), '-created_at')

    return qs, {'q': q, 'status': status, 'date_from': date_from, 'date_to': date_to}


@require_perm('invoice', 'view')
def invoice_list(request):
    active_company = get_active_company(request)
    base_qs = Invoice.objects.filter(
        invoice_type=InvoiceType.HOTEL, company=active_company
    ).prefetch_related('reservations', 'service_items')

    qs, filters = _filter_invoice_qs(base_qs, request)
    q, status, date_from, date_to = filters['q'], filters['status'], filters['date_from'], filters['date_to']

    due_soon = request.GET.get('due_soon')
    if due_soon:
        threshold = date.today() + timedelta(days=7)
        qs = qs.filter(due_date__lte=threshold, due_date__gte=date.today())

    paginator = Paginator(qs, 10 if _is_mobile(request) else 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_invoices = list(page_obj)
    paid_map = fq.invoice_paid_map([inv.pk for inv in page_invoices])

    invoices = []
    for inv in page_invoices:
        remaining = inv.total_sar - paid_map.get(inv.pk, 0)
        invoices.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "customer_name": inv.customer_name,
            "issued_date": inv.issued_date.strftime("%d/%m/%Y") if inv.issued_date else None,
            "due_date": inv.due_date.strftime("%d/%m/%Y") if inv.due_date else None,
            "created_at": inv.created_at.strftime("%d/%m/%Y"),
            "total_sar": inv.total_sar,
            "remaining_sar": remaining,
            "status": (
                "overpaid" if remaining < 0
                else "paid" if remaining == 0
                else "partial" if remaining < inv.total_sar
                else "unpaid"
            ),
        })

    props = {
        "invoices": invoices,
        "total_count": paginator.count,
        "q": q,
        "status_filter": status,
        "date_from": date_from,
        "date_to": date_to,
        "pagination": pagination_props(page_obj),
    }
    if active_company == Company.KONOZ:
        props["remit_stats"] = _invoice_stats(base_qs, active_company)

    return inertia_render(request, "Invoice/List", props=props)


def _invoice_stats(invoice_qs, company):
    from ..finance import accounts as coa

    invoice_ids = list(invoice_qs.values_list('id', flat=True))
    total_tagihan = fq.total_charged(company, invoice_ids)
    terbayar_surabaya = fq.paid_into(coa.CASH_SBY, company, invoice_ids)
    terbayar_pusat = fq.paid_into(coa.CASH_PUSAT, company, invoice_ids)

    return {
        'total_tagihan': total_tagihan,
        'belum_terbayar': max(0, total_tagihan - terbayar_surabaya - terbayar_pusat),
        # mengendap boleh negatif: Surabaya bisa mengirim lebih dari yang pernah
        # diterima untuk invoice-invoice ini (kredit di pusat), lihat hw/ledger.py.
        'mengendap': fq.mengendap(company, invoice_ids),
        'terbayar_surabaya': terbayar_surabaya,
        'terbayar_pusat': terbayar_pusat,
    }


@require_perm('invoice', 'create')
def invoice_new(request):
    suggested_number = Invoice.generate_number(InvoiceType.HOTEL)
    active_company = get_active_company(request)

    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number", "")

        def _reject(errors):
            return inertia_render(request, "Invoice/Form", props={
                "edit": False,
                "invoice": None,
                "suggested_number": invoice_number or suggested_number,
                "cl_data": _cl_data_for_form(active_company),
                "clients": _client_options(active_company),
                "initial": _invoice_echo(request),
                "errors": errors,
            })

        if Invoice.objects.filter(invoice_number=invoice_number).exists():
            return _reject({"invoice_number": f"Invoice number '{invoice_number}' is already in use."})

        cl_ids = _billable_cl_ids(request, active_company)
        client = _resolve_client_from_post(request, active_company)
        # Hotel invoice butuh isi: minimal harus ada CL yang bisa ditagih ATAU
        # baris reservasi manual ATAU client yang dipilih langsung di form.
        # (Kiriman kosong → reject, jangan bikin invoice yatim.)
        if not cl_ids and not client and not _has_reservation_rows(request):
            return _reject({"reservations": "Pick at least one confirmation letter that isn't already on an invoice."})

        try:
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
                    invoice_type=InvoiceType.HOTEL,
                    invoice_number=invoice_number,
                    client=client,
                    issued_date=_parse_date(request.POST.get("issued_date")),
                    due_date=_parse_date(request.POST.get("due_date")),
                    currency="SAR",
                )
                # CL must be linked before _save_reservations/_save_hotel_payments run --
                # both call _billing_client(invoice), which resolves the client from
                # invoice.confirmation_letters. Linking after would leave the journal
                # charge lines client=None even when a CL was selected.
                ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

                _save_reservations(invoice, request)
                _save_hotel_payments(invoice, request)
        except (FinanceError, ValueError) as e:
            return _reject({"finance": str(e)})

        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Invoice Hotel', invoice.invoice_number, invoice.company)
        messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
        return redirect("invoice_detail", pk=invoice.pk)

    initial = None
    preselect_cl = ConfirmationLetter.objects.filter(
        pk=request.GET.get("cl"), company=active_company, invoice__isnull=True,
    ).first()
    if preselect_cl:
        initial = {"linked_cl_ids": [preselect_cl.pk]}

    return inertia_render(request, "Invoice/Form", props={
        "edit": False,
        "invoice": None,
        "suggested_number": suggested_number,
        "cl_data": _cl_data_for_form(active_company),
        "clients": _client_options(active_company),
        "initial": initial,
    })


@require_perm('invoice', 'view')
def invoice_detail(request, pk):
    filters = {'pk': pk, 'invoice_type': InvoiceType.HOTEL, 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
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
        "cl_pk": r["cl_pk"],
    } for r in res_ctx]

    payments = [{
        "id": p["pk"],
        "status": p["status"],
        "unallocated_sar": p["unallocated_sar"],
        "linked_number": p["ref"],
        "payment_date": p["payment_date"].strftime("%d/%m/%Y") if p["payment_date"] else None,
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
    invoice = get_object_or_404(Invoice, pk=pk, invoice_type=InvoiceType.HOTEL, company=active_company)

    if request.method == "POST":
        def _res_snapshot(inv):
            rows = [
                f"{r.hotel} {r.check_in}–{r.check_out} ({int(r.total_sar or 0)} SAR)"
                for r in inv.reservations.order_by('id')
            ]
            return ' | '.join(rows) if rows else '—'

        _before = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date', 'company'])
        _res_before = _res_snapshot(invoice)
        new_number = request.POST.get("invoice_number", "")

        def _reject(errors):
            return inertia_render(request, "Invoice/Form", props={
                "edit": True,
                "invoice": _serialize_hotel_invoice(invoice),
                "cl_data": _cl_data_for_form(active_company),
                "clients": _client_options(active_company),
                "initial": _invoice_echo(request),
                "errors": errors,
            })

        if Invoice.objects.filter(invoice_number=new_number).exclude(pk=invoice.pk).exists():
            return _reject({"invoice_number": f"Invoice number '{new_number}' is already in use."})

        cl_ids = _billable_cl_ids(request, active_company, invoice)
        # Hotel invoice butuh isi: CL yang bisa ditagih ATAU baris reservasi
        # manual ATAU client pilihan form — kiriman kosong jangan disimpan.
        if not cl_ids and not _resolve_client_from_post(request, active_company) and not _has_reservation_rows(request):
            return _reject({"reservations": "Pick at least one confirmation letter that isn't already on an invoice."})

        # invoice.company is deliberately left alone: the fetch above already
        # constrains it to active_company, so any value arriving in the POST
        # body could only ever move the record OUT of the caller's own scope.
        try:
            with transaction.atomic():
                client = _resolve_client_from_post(request, active_company)
                invoice.invoice_number = new_number
                invoice.client = client
                invoice.issued_date = _parse_date(request.POST.get("issued_date"))
                invoice.due_date = _parse_date(request.POST.get("due_date"))
                invoice.save()

                invoice.reservations.all().delete()

                # Relink CL selection before recreating reservations/payments -- see
                # the matching comment in invoice_new for why the order matters.
                ConfirmationLetter.objects.filter(invoice=invoice).update(invoice=None)
                ConfirmationLetter.objects.filter(pk__in=cl_ids).update(invoice=invoice)

                _save_reservations(invoice, request)
                _save_hotel_payments(invoice, request)
        except (FinanceError, ValueError) as e:
            # A finance failure (e.g. PeriodLockedError when a payment falls in a
            # closed period) must roll back cleanly and show the user a form error,
            # not a raw 500.
            return _reject({"finance": str(e)})
        _after = snapshot_fields(invoice, ['customer_name', 'invoice_number', 'issued_date', 'due_date', 'company'])
        _res_after = _res_snapshot(invoice)
        changes = track_changes(
            {**_before, 'reservations': _res_before},
            {**_after, 'reservations': _res_after},
            labels={'customer_name': 'Customer Name', 'invoice_number': 'Invoice No.', 'issued_date': 'Issued Date', 'due_date': 'Due Date', 'company': 'Company', 'reservations': 'Reservations'},
        )
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
    filters = {'pk': pk, 'invoice_type': InvoiceType.HOTEL, 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
    if request.method == "POST":
        num = invoice.invoice_number
        # System of record: invoice yang sudah menyentuh general ledger
        # (charge/payment) tidak boleh hilang dari riwayat keuangan.
        from ..models.journal import JournalLine
        if JournalLine.objects.filter(invoice=invoice).exists():
            messages.error(request, f'Invoice {num} tidak bisa dihapus karena sudah tercatat di jurnal keuangan.')
            return redirect('invoice_detail', pk=pk)
        try:
            invoice.delete()
        except Exception as exc:
            # A pending PaymentRecord (PROTECT) may still exist even when no
            # journal lines were written; surface that cleanly instead of a 500.
            from django.db.models.deletion import ProtectedError
            if isinstance(exc, ProtectedError):
                messages.error(
                    request,
                    f'Invoice {num} tidak bisa dihapus karena masih punya '
                    'PaymentRecord terkait. Batalkan/balik pembayarannya dulu.',
                )
                return redirect('invoice_detail', pk=pk)
            raise
        log_activity(request.user, ActivityLog.ACTION_DELETE, 'Invoice Hotel', num, invoice.company)
        messages.success(request, f"Invoice {num} deleted successfully.")
        return redirect("invoice_list")
    # Confirmation is handled client-side (React modal); GET just bounces back.
    return redirect("invoice_list")


@require_perm('invoice', 'export')
def invoice_pdf(request, pk):
    filters = {'pk': pk, 'invoice_type': InvoiceType.HOTEL, 'company': get_active_company(request)}
    invoice = get_object_or_404(Invoice, **filters)
    return _render_invoice_pdf(invoice)


@require_perm('invoice', 'export')
def invoice_list_pdf(request):
    active_company = get_active_company(request)
    base_qs = Invoice.objects.filter(invoice_type=InvoiceType.HOTEL, company=active_company).prefetch_related('reservations', 'service_items')
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
            "logo_rel_path": _logo_file_url(active_company),
            "company_label": dict(Company.choices).get(active_company, active_company),
        },
    )


@require_perm('invoice', 'export')
def invoice_export_csv(request):
    base_qs = Invoice.objects.filter(invoice_type=InvoiceType.HOTEL, company=get_active_company(request)).prefetch_related('reservations', 'service_items')
    qs, _ = _filter_invoice_qs(base_qs, request)
    headers = ['Invoice #', 'Company', 'Customer', 'Issued Date', 'Due Date', 'Total SAR', 'Paid SAR', 'Sisa SAR']
    rows = ([
        inv.invoice_number, inv.company, inv.customer_name,
        inv.issued_date or '', inv.due_date or '',
        inv.total_sar, inv.total_sar - inv.remaining_sar, inv.remaining_sar,
    ] for inv in qs)
    return csv_export_response('invoices_hotel.csv', headers, rows)


@require_perm('invoice', 'create')
def invoice_duplicate(request, pk):
    original = get_object_or_404(Invoice, pk=pk, invoice_type=InvoiceType.HOTEL, company=get_active_company(request))
    new_num = Invoice.generate_number(InvoiceType.HOTEL)
    today = date.today()
    try:
        with transaction.atomic():
            new_inv = Invoice.objects.create(
                company=original.company,
                invoice_type=InvoiceType.HOTEL,
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
    except Exception as e:  # IntegrityError dll — jangan tinggalkan invoice yatim tanpa reservasi
        logger.warning("Duplikasi invoice %s gagal: %s", original.pk, e)
        messages.error(request, f"Gagal menduplikasi invoice: {e}")
        return redirect("invoice_edit", pk=original.pk)
    messages.success(request, f"Invoice duplicated as {new_num} (from {original.invoice_number}).")
    return redirect("invoice_edit", pk=new_inv.pk)


def _save_reservations(invoice, request):
    """Full delete-then-recreate reservations, lalu posting.post_invoice_charge
    (idempotent-by-content: reverse charge lama + repost) supaya jurnal
    (DR Piutang / CR Pendapatan) selalu cocok dengan total reservasi."""
    from ..finance.posting import post_invoice_charge

    try:
        rows = json.loads(request.POST.get("reservations", "[]"))
    except (ValueError, TypeError):
        rows = []
    with transaction.atomic():
        for r in rows:
            total_sar = int(round(_to_float(r.get("reservation_total"))))
            Reservation.objects.create(
                invoice=invoice,
                reservation_number=(r.get("reservation_number") or "-").strip() or "-",
                hotel=(r.get("hotel") or "-").strip() or "-",
                check_in=_parse_date(r.get("check_in")),
                check_out=_parse_date(r.get("check_out")),
                total_sar=total_sar,
            )
        if not invoice.client_id and _billing_client(invoice):
            invoice.client = _billing_client(invoice)
            invoice.save(update_fields=['client', 'customer_name'])
        if invoice.client_id:
            post_invoice_charge(invoice, created_by=request.user)
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
        } for r in invoice.reservations.all()],
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


def _has_reservation_rows(request):
    """True jika body form memuat minimal satu baris reservasi manual ber-isi."""
    try:
        rows = json.loads(request.POST.get("reservations", "[]"))
    except (ValueError, TypeError):
        return False
    return any(_to_float(r.get("reservation_total")) for r in rows if isinstance(r, dict))


def _billable_cl_ids(request, company, invoice=None):
    """CL pks from the POST this invoice may bill: same company, and either not
    yet on any invoice or already on this one (edit). A hotel invoice can only
    be built from existing confirmation letters — there is no manual line."""
    ids = _parse_cl_ids(request)
    if not ids:
        return []
    qs = ConfirmationLetter.objects.filter(pk__in=ids, company=company)
    if invoice is not None:
        qs = qs.filter(Q(invoice__isnull=True) | Q(invoice=invoice))
    else:
        qs = qs.filter(invoice__isnull=True)
    return list(qs.values_list("pk", flat=True))


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
