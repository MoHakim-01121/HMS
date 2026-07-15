import json
import logging
import urllib.error
import urllib.request
from datetime import date

from django.conf import settings

from .models import ConfirmationLetter, Invoice

_API_URL     = "https://api.groq.com/openai/v1/chat/completions"
_MODEL_SMALL = "llama-3.1-8b-instant"
_MODEL_CHAT  = "llama-3.1-8b-instant"
_logger      = logging.getLogger(__name__)


def _call_groq(messages: list, model: str = _MODEL_SMALL) -> str | None:
    api_key = getattr(settings, 'GROQ_API_KEY', None)
    if not api_key:
        return None

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(
        _API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        _logger.error("Groq API error %s: %s", e.code, body)
        return None
    except Exception as e:
        _logger.error("Groq API error: %s", e)
        return None


def _user(prompt: str) -> list:
    """Shorthand: wrap a single prompt as a user message."""
    return [{"role": "user", "content": prompt}]


_MONTHS_ID = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
              'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

_SIGNATURES = {'konoz': 'Konoz United Surabaya', 'ijabah': 'Ijabah'}


def _fmt_date_id(d):
    return f"{d.day:02d} {_MONTHS_ID[d.month]} {d.year}"



def generate_draft_message(invoice_type: str, invoice) -> str | None:
    # Impor lokal: hw.views.__init__ mengimpor modul ini, impor top-level
    # ke hw.views.* akan membuat siklus.
    from .views.context import _build_visa_services_context
    from .views.helpers import _billing_client

    def _fmt(n):
        return f"{int(round(n)):,}".replace(",", ".")

    client = _billing_client(invoice)
    name = client.name if client else invoice.customer_name
    signature = _SIGNATURES.get(invoice.company, invoice.get_company_display())
    lunas = invoice_type in ('invoice_lunas', 'services_lunas')

    if invoice_type in ('invoice', 'invoice_lunas'):
        detail_lines = []
        for r in invoice.reservations.all():
            detail_lines.append(f"- RSV : {r.reservation_number}")
            detail_lines.append(f"  Hotel: {r.hotel or '-'}")
        total = invoice.total_sar
        remaining = 0 if lunas else invoice.remaining_sar
        currency = 'SAR'
    else:
        services = _build_visa_services_context(invoice)
        detail_lines = [f"- Layanan: {s['product']} x{s['qty']}" for s in services]
        total = sum(s['total'] for s in services)
        remaining = 0 if lunas else sum(s['remaining'] for s in services)
        currency = invoice.currency
    paid = total - remaining

    if lunas:
        intro = (f"Pembayaran Invoice {invoice.invoice_number} telah kami terima. "
                 f"Invoice Anda telah *LUNAS*.")
    else:
        intro = f"Invoice {invoice.invoice_number} Anda telah diterbitkan."

    parts = [
        f"Assalamualaikum Wr Wb team {name},",
        intro,
        "",
        "Detail tagihan:",
        *detail_lines,
        "",
        f"Total: {_fmt(total)} {currency}",
        f"Terbayar: {_fmt(paid)} {currency}",
        f"Sisa: {_fmt(remaining)} {currency}",
    ]

    if not lunas and invoice.due_date:
        days_late = (date.today() - invoice.due_date).days
        parts.append("")
        parts.append(f"*Jatuh Tempo: {_fmt_date_id(invoice.due_date)}*")
        if days_late > 0:
            parts.append(
                f"Sudah lewat jatuh tempo ({days_late} hari). "
                f"Mohon segera lakukan pembayaran."
            )
        else:
            parts.append("Mohon lakukan pembayaran sebelum jatuh tempo.")

    parts += ["", "Terima kasih,", f"*{signature}*"]
    return "\n".join(parts)


def get_chat_reply(
    message: str,
    company: str | None = None,
    history: list | None = None,
) -> str | None:
    today = date.today()
    month = today.month
    year  = today.year

    inv_qs = Invoice.objects.filter(invoice_type="hotel").prefetch_related('reservations', 'payments')
    svc_qs = Invoice.objects.filter(invoice_type="visa").prefetch_related('service_items', 'payments')
    cl_qs  = ConfirmationLetter.objects.all().prefetch_related('rooms')
    if company:
        inv_qs = inv_qs.filter(company=company)
        svc_qs = svc_qs.filter(company=company)
        cl_qs  = cl_qs.filter(company=company)

    invoices = list(inv_qs.order_by("-created_at")[:20])
    services = list(svc_qs.order_by("-created_at")[:20])
    cls      = list(cl_qs.order_by("-created_at")[:20])

    inv_total       = sum(i.total_sar for i in invoices)
    inv_remaining   = sum(i.remaining_sar for i in invoices)
    inv_unpaid      = sum(1 for i in invoices if i.remaining_sar > 0)
    inv_this_month  = [i for i in invoices if i.created_at.month == month and i.created_at.year == year]
    inv_month_total = sum(i.total_sar for i in inv_this_month)

    # Keyword detection — only include detail sections that are relevant
    msg_lower = message.lower()
    is_followup = bool(history)
    needs_inv = is_followup or any(k in msg_lower for k in [
        'invoice', 'inv', 'bayar', 'lunas', 'tagih', 'sisa', 'hotel', 'total', 'belum'
    ])
    needs_svc = is_followup or any(k in msg_lower for k in [
        'service', 'svc', 'visa', 'layanan'
    ])
    needs_cl = is_followup or any(k in msg_lower for k in [
        'cl', 'confirmation', 'letter', 'tamu', 'guest', 'check', 'kamar', 'room', 'reservasi'
    ])
    if not (needs_inv or needs_svc or needs_cl):
        needs_inv = needs_svc = needs_cl = True

    company_label = {"konoz": "Konoz United", "ijabah": "Ijabah"}.get(company, company) if company else "semua perusahaan"

    system_parts = [
        f"Kamu adalah asisten HMS (Hotel Management System). Jawab berdasarkan data berikut.\n"
        f"Jawab dalam Bahasa Indonesia, singkat dan padat. "
        f"Gunakan bullet point (- item) untuk daftar biasa. "
        f"Untuk daftar invoice hotel gunakan: [inv: nomor | nama | total SAR | sisa SAR | Lunas/Belum lunas] satu per baris. "
        f"Jangan ulangi info yang tidak perlu. Data milik: {company_label}. Hari ini: {today}.\n\n"
        f"=== RINGKASAN ===\n"
        f"Invoice Hotel: {len(invoices)} total | {inv_total:,.0f} SAR | Sisa: {inv_remaining:,.0f} SAR | {inv_unpaid} belum lunas\n"
        f"Bulan ini: {len(inv_this_month)} invoice | {inv_month_total:,.0f} SAR\n"
        f"Invoice Services: {len(services)} total\n"
        f"Confirmation Letter: {len(cls)} total"
    ]

    if needs_inv:
        inv_lines = "\n".join(
            f"- {i.invoice_number} | {i.customer_name} | Total: {i.total_sar:,.0f} SAR | "
            f"Sisa: {i.remaining_sar:,.0f} SAR | {'Lunas' if i.remaining_sar == 0 else 'Belum lunas'} | "
            f"{i.issued_date or '-'}"
            for i in invoices
        )
        system_parts.append(f"\n\n=== INVOICE HOTEL ===\n{inv_lines}")

    if needs_svc:
        svc_lines = "\n".join(
            f"- {i.invoice_number} | {i.customer_name} | {i.currency} | {i.issued_date or '-'}"
            for i in services
        )
        system_parts.append(f"\n\n=== INVOICE SERVICES ===\n{svc_lines}")

    if needs_cl:
        cl_lines = "\n".join(
            f"- {c.confirmation_number} | {c.guest_name} | {c.hotel_name} | "
            f"CI: {c.check_in or '-'} CO: {c.check_out or '-'} | {c.total_price:,.0f} SAR | {c.reservation_status}"
            for c in cls
        )
        system_parts.append(f"\n\n=== CONFIRMATION LETTER ===\n{cl_lines}")

    system_context = "".join(system_parts)

    messages = [
        {"role": "system", "content": system_context},
        *(history or []),
        {"role": "user", "content": message},
    ]
    return _call_groq(messages, model=_MODEL_CHAT)
