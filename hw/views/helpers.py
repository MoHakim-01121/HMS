import csv
from datetime import date, datetime

import magic

from django.http import HttpResponse

PROOF_MAX_SIZE = 10 * 1024 * 1024  # 10 MB, matches attachment_upload
PROOF_ALLOWED_MIME = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
}


def validate_proof_file(f):
    """Reject a payment/remittance/refund proof upload that's oversized or
    isn't actually an image/PDF -- content is sniffed the same way
    attachment_upload does it, rather than trusting the client-supplied
    content-type. Returns an error message, or None if the file is fine."""
    if f.size > PROOF_MAX_SIZE:
        return "File too large (max 10 MB)."
    header = f.read(2048)
    f.seek(0)
    if magic.from_buffer(header, mime=True) not in PROOF_ALLOWED_MIME:
        return "File type not allowed. Use PDF or image (JPG/PNG/GIF/WEBP)."
    return None


def _is_mobile(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    return any(t in ua for t in ('mobi', 'android', 'iphone', 'ipod', 'windows phone'))


def _page_range_display(page_obj):
    current = page_obj.number
    last = page_obj.paginator.num_pages
    result = []
    for i in range(1, last + 1):
        if i == 1 or i == last or abs(i - current) <= 2:
            result.append(i)
        elif result and result[-1] is not None:
            result.append(None)
    return result



def _render_list_pdf(request, qs, template, filename, extra_ctx=None):
    from datetime import datetime as _dt
    from django.conf import settings
    from django.template.loader import render_to_string
    from weasyprint import HTML
    q = request.GET.get('q', '').strip()
    ctx = {
        "q": q,
        "now": _dt.now(),
    }
    if extra_ctx:
        ctx.update(extra_ctx)
    html = render_to_string(template, ctx)
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def _parse_search_tokens(q):
    """Split a list-page search box value into OR-ed tokens ("a, b" = a OR b)."""
    if ',' not in q:
        return [q[:100]]
    return [t.strip()[:100] for t in q.split(',') if t.strip()]


def _parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(val, default=0.0):
    try:
        if isinstance(val, str):
            val = val.replace(',', '').strip()
        return float(val) if val not in (None, '') else default
    except (ValueError, TypeError):
        return default


def pagination_props(page_obj):
    """Standard Inertia props describing a Paginator page."""
    return {
        "number": page_obj.number,
        "num_pages": page_obj.paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
        "has_other_pages": page_obj.has_other_pages(),
        "range": _page_range_display(page_obj),
        "start_index": page_obj.start_index(),
        "end_index": page_obj.end_index(),
        "count": page_obj.paginator.count,
    }


def period_label(date_from=None, date_to=None):
    """Human-readable label for an optional from/to date range."""
    if date_from and date_to:
        return f"{date_from.strftime('%d %b %Y')} — {date_to.strftime('%d %b %Y')}"
    if date_from:
        return f"Sejak {date_from.strftime('%d %b %Y')}"
    if date_to:
        return f"Sampai {date_to.strftime('%d %b %Y')}"
    return 'Semua transaksi'


def money_account_choices(branch=None):
    """[{value, label, branch, currency}] for a receiving/paying-account
    picker — value is "cash:<id>" or "bank:<id>", parsed back by
    resolve_money_account(). Shared by payment_views and expense_views."""
    from ..models.bank import BankAccount, CashAccount
    cash_qs = CashAccount.objects.filter(is_active=True).select_related('branch')
    bank_qs = BankAccount.objects.filter(is_active=True).select_related('branch')
    if branch:
        cash_qs = cash_qs.filter(branch_id=branch)
        bank_qs = bank_qs.filter(branch_id=branch)
    choices = []
    for a in cash_qs:
        choices.append({'value': f'cash:{a.pk}', 'label': f'{a.name} ({a.currency})', 'branch': a.branch_id, 'currency': a.currency})
    for a in bank_qs:
        choices.append({'value': f'bank:{a.pk}', 'label': str(a), 'branch': a.branch_id, 'currency': a.currency})
    return choices


def resolve_money_account(value):
    """"cash:<id>" / "bank:<id>" -> (bank_account, cash_account).

    Only active accounts resolve — the same set money_account_choices offers,
    so a hand-crafted value can't book money into a deactivated account.
    Every caller is a create path (record payment/expense, new statement)."""
    from ..models.bank import BankAccount, CashAccount
    if not value or ':' not in value:
        return None, None
    kind, _, pk = value.partition(':')
    if kind == 'cash':
        return None, CashAccount.objects.filter(pk=pk, is_active=True).first()
    if kind == 'bank':
        return BankAccount.objects.filter(pk=pk, is_active=True).first(), None
    return None, None


def _client_options():
    """Active clients as [{id, name}] options for form dropdowns."""
    from ..models import Client
    return list(
        Client.objects.filter(is_active=True)
        .order_by('name').values('id', 'name')
    )


def serialize_journal_entry(entry, **extra):
    """Base dict for a JournalEntry used across finance/payment/period views.

    Always includes the common 6 fields; callers pass optional extras
    (total_debit, total_credit, is_balanced, etc.) via keyword arguments.
    """
    base = {
        'id': entry.pk,
        'entry_number': entry.entry_number,
        'entry_type': entry.entry_type,
        'entry_type_display': entry.get_entry_type_display(),
        'description': entry.description,
        'entry_date': entry.entry_date.isoformat(),
    }
    if extra:
        base.update(extra)
    return base


def journal_line_dimension(line):
    """Resolve a JournalLine's FK references into a human-readable label.

    Returns the first matching dimension (client, invoice, reservation,
    service, or penalty) rather than concatenating all, matching the
    original per-line display convention.
    """
    if getattr(line, 'client_id', None):
        return line.client.name
    if getattr(line, 'invoice_id', None):
        return line.invoice.invoice_number
    if getattr(line, 'reservation_id', None):
        return line.reservation.reservation_number
    if getattr(line, 'service_item_id', None):
        return f"Service #{line.service_item_id}"
    if getattr(line, 'penalty_id', None):
        return line.penalty.penalty_number
    return ''


# ── CSV Export ────────────────────────────────────────────────────────


def csv_export_response(filename, headers, rows, encoding='utf-8', bom=True):
    """Create a CSV download response with standard writer boilerplate.

    Parameters
    ----------
    filename : str
        Output filename (e.g. ``'invoices.csv'``).
    headers : list[str]
        Column headers.
    rows : iterable[list|tuple]
        One row per item.
    encoding : str
        Charset (default ``utf-8``).  ``utf-8-sig`` is the Excel-friendly
        variant; combine it with ``bom=False`` so the charset itself emits
        the byte-order mark instead of us writing it twice.
    bom : bool
        Whether to prepend a UTF-8 byte-order mark (default ``True``).
    """
    response = HttpResponse(content_type=f'text/csv; charset={encoding}')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    if bom and encoding.lower() != 'utf-8-sig':
        response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


# ── Change Tracking ──────────────────────────────────────────────────


def snapshot_fields(obj, fields):
    """Return a dict of ``{field: value}`` for the given field names.

    ``date``/``datetime`` values are serialized to strings so the resulting
    snapshot is JSON-serializable (matching how the activity log stores it).
    """
    snapshot = {}
    for f in fields:
        value = getattr(obj, f, None)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        snapshot[f] = value
    return snapshot


def track_changes(before, after, labels=None):
    """Compare two field snapshots and return a list of changes.

    Parameters
    ----------
    before : dict
        Snapshot before the edit (from ``snapshot_fields``).
    after : dict
        Snapshot after the edit.
    labels : dict, optional
        Human-readable labels, e.g. ``{'name': 'Name'}``.

    Returns
    -------
    list[dict]
        ``[{'label': str, 'before': ..., 'after': ...}, ...]``
    """
    labels = labels or {}
    changes = []
    for key in before:
        if before[key] != after[key]:
            changes.append({
                'label': labels.get(key, key),
                'before': before[key],
                'after': after[key],
            })
    return changes


# ── Due-Soon Alert ───────────────────────────────────────────────────


def due_soon_alert(due_date, remaining=0):
    """Check if a due date is approaching or overdue.

    Parameters
    ----------
    due_date : datetime.date or None
    remaining : int
        Outstanding amount — alert is suppressed when fully paid.

    Returns
    -------
    dict or None
        ``{'type': 'red'|'yellow', 'msg': str}`` or ``None``.
    """
    if not due_date or remaining <= 0:
        return None

    days = (due_date - date.today()).days

    if days < 0:
        return {'type': 'red', 'msg': f'Payment is {abs(days)} day(s) overdue.'}
    if days == 0:
        return {'type': 'red', 'msg': 'Due today!'}
    if days <= 7:
        return {'type': 'yellow', 'msg': f'Due in {days} day(s).'}
    return None
