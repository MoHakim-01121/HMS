import csv
from datetime import date, datetime

import magic

from django.http import HttpResponse
from django.utils.http import content_disposition_header

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
    # content_disposition_header menambah filename*=utf-8'' bila nama file
    # bukan ASCII (mis. nama client Arab), yang tidak bisa ditulis apa adanya.
    response['Content-Disposition'] = content_disposition_header(False, filename)
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


def money_account_choices(branch=None, branches=None, *, staff=False, balances=False):
    """[{value, label, branch, currency, kind}] for a receiving/paying-account
    picker — value is "cash:<id>" or "bank:<id>", parsed back by
    resolve_money_account(). Shared by payment_views and expense_views.
    `branch` keeps one branch's accounts, `branches` those of several.
    Staff advances ("staff:<id>") only with `staff`; `balances` adds what
    each account holds now, in its own currency, from the cash book."""
    from ..models.bank import MoneyAccount
    qs = MoneyAccount.objects.filter(is_active=True)
    if not staff:
        qs = qs.exclude(kind=MoneyAccount.KIND_STAFF)
    if branch:
        qs = qs.filter(branch_id=branch)
    if branches is not None:
        qs = qs.filter(branch_id__in=branches)
    # Kas dulu, lalu bank — urutan yang sama seperti sebelum digabung.
    order = {MoneyAccount.KIND_CASH: 0, MoneyAccount.KIND_BANK: 1, MoneyAccount.KIND_STAFF: 2}
    accounts = sorted(qs.select_related('holder', 'branch'), key=lambda a: (order[a.kind], a.bank_name, a.name, a.pk))
    held = {}
    if balances:
        from ..finance.staff_advance import balances as cash_book
        held = cash_book(accounts)
    rows = []
    for a in accounts:
        row = {'value': a.token, 'label': str(a), 'branch': a.branch_id, 'branch_name': a.branch.name,
               'currency': a.currency, 'kind': a.kind}
        if a.kind == MoneyAccount.KIND_BANK:
            row['number'] = a.account_identifier
        if a.kind == MoneyAccount.KIND_STAFF:
            row['holder'] = a.holder_id
        if balances:
            row['balance'] = held.get(a.pk, 0)
        rows.append(row)
    return rows


def resolve_money_account(value, *, staff=False):
    """"cash:<id>" / "bank:<id>" (and "staff:<id>" with `staff`) -> MoneyAccount, or None.

    Only active accounts resolve — the same set money_account_choices offers,
    so a hand-crafted value can't book money into a deactivated account.
    Every caller is a create path (record payment/expense, new statement)."""
    from ..models.bank import MoneyAccount
    if not value or ':' not in value:
        return None
    kind, _, pk = value.partition(':')
    kinds = (MoneyAccount.KIND_BANK, MoneyAccount.KIND_CASH) + ((MoneyAccount.KIND_STAFF,) if staff else ())
    if not pk.isdigit() or kind not in kinds:
        return None
    return MoneyAccount.objects.filter(pk=pk, kind=kind, is_active=True).first()


def _client_options(user):
    """Active clients of the user's branches as [{id, name, city}] options
    for form dropdowns."""
    from ..branch_scope import scope
    from ..models import Client
    return list(
        scope(Client.objects.filter(is_active=True), user)
        .order_by('name').values('id', 'name', 'city')
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
    if getattr(line, 'invoice_line_id', None):
        il = line.invoice_line
        return il.confirmation_letter.confirmation_number if il.confirmation_letter_id else f"Service #{il.line_no}"
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


def request_data(request):
    """POST body as a dict-like, whether the client sent form data or JSON
    (Inertia's useForm posts JSON unless forceFormData is set)."""
    import json
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body or b'{}')
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST


def list_period(request, field_from=None, field_to=None):
    """The period a list page shows, from ?month=YYYY-MM | ?year=YYYY|all.

    Defaults to the current month. A filter range (?from=&to=) wins over the
    month ("Used instead of the month above" on the list pages). Returns
    (date_from, date_to, props) where props echo the state for MonthNav;
    date_from/date_to None mean unbounded."""
    import calendar
    from datetime import date as _date
    g = request.GET
    rng_from, rng_to = _parse_date(g.get('from', '')), _parse_date(g.get('to', ''))
    month, year = g.get('month', ''), g.get('year', '')
    today = _date.today()
    props = {'month': '', 'year': '', 'from': g.get('from', ''), 'to': g.get('to', '')}
    if rng_from or rng_to:
        props['year'] = 'all'
        return rng_from, rng_to, props
    if year == 'all':
        props['year'] = 'all'
        return None, None, props
    if year.isdigit() and len(year) == 4 and not month:
        y = int(year)
        props['year'] = year
        return _date(y, 1, 1), _date(y, 12, 31), props
    try:
        y, m = (int(x) for x in month.split('-'))
        first = _date(y, m, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    props['month'] = first.strftime('%Y-%m')
    return first, last, props


def list_per_page(request, default=10):
    try:
        n = int(request.GET.get('per', default))
    except (TypeError, ValueError):
        n = default
    return n if n in (10, 25, 50) else default


def csv_list(request, key, allowed=None):
    """?key=a,b → ['a', 'b'] (only allowed values when given)."""
    vals = [v for v in request.GET.get(key, '').split(',') if v]
    return [v for v in vals if v in allowed] if allowed is not None else vals


def prev_month_range(date_from):
    """First and last day of the month before date_from's month."""
    import calendar
    first = (date_from.replace(day=1) - __import__('datetime').timedelta(days=1)).replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def pct_delta(cur, prev):
    """'+12%' / '-5%' / None when there is no base."""
    if not prev:
        return None
    d = round((cur - prev) * 100 / prev)
    return f"{'+' if d >= 0 else ''}{d}%"


def num_delta(cur, prev):
    d = cur - prev
    return f"{'+' if d >= 0 else ''}{d}"
