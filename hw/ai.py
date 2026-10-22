import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from .models import ConfirmationLetter, Invoice

_API_URL     = "https://api.groq.com/openai/v1/chat/completions"
# Groq pensiunkan seri Llama untuk akun ini (404 model_not_found) sejak 2026.
# openai/gpt-oss-20b: kecil, cepat, masih tersedia. Lihat daftar aktif via
# GET https://api.groq.com/openai/v1/models.
_MODEL_SMALL = "openai/gpt-oss-20b"
_MODEL_CHAT  = "openai/gpt-oss-20b"
_logger      = logging.getLogger(__name__)


def _call_groq(messages: list, model: str = _MODEL_SMALL) -> str | None:
    api_key = getattr(settings, 'GROQ_API_KEY', None)
    if not api_key:
        return None

    payload = json.dumps({
        "model": model,
        "messages": messages,
        # gpt-oss memakai sebagian budget token untuk reasoning internal
        # (tak ikut ke content), jadi beri ruang lebih longgar dari 150.
        "max_tokens": 512,
        "reasoning_effort": "low",
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

_SIGNATURE = 'Konoz United Surabaya'

def _fmt_date_id(d):
    return f"{d.day:02d} {_MONTHS_ID[d.month]} {d.year}"



def generate_draft_message(invoice_type: str, invoice) -> str | None:
    # Impor lokal: hw.views.__init__ mengimpor modul ini, impor top-level
    # ke hw.views.* akan membuat siklus.
    from .views.invoice_billing import _billing_client

    def _fmt(n):
        return f"{int(round(n)):,}".replace(",", ".")

    client = _billing_client(invoice)
    name = client.name
    signature = _SIGNATURE
    lunas = invoice_type == 'invoice_lunas'

    detail_lines = []
    for r in invoice.reservations:
        detail_lines.append(f"- RSV : {r.reservation_number}")
        detail_lines.append(f"  Hotel: {r.hotel or '-'}")
    total = invoice.total_sar
    remaining = 0 if lunas else invoice.remaining_sar
    currency = 'SAR'
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
        today = timezone.now().date()
        days_late = (today - invoice.due_date).days
        parts.append("")
        parts.append(f"*Jatuh Tempo: {_fmt_date_id(invoice.due_date)}*")
        if days_late > 0:
            parts.append(
                f"Sudah lewat jatuh tempo ({days_late} hari). "
                f"Mohon segera lakukan pembayaran."
            )
        else:
            parts.append("Mohon lakukan pembayaran sebelum jatuh tempo.")

    # Rekening dari "Pay to" cabang penerbit (Bank Balances), bukan hardcode:
    # draft pesan dan detail invoice selalu menyebut rekening yang sama.
    accounts = list(invoice.pay_to_accounts()) if not lunas else []
    if accounts:
        parts += ["", "Informasi Pembayaran:"]
        for i, acc in enumerate(accounts):
            if i:
                parts.append("")
            parts += [f"Nama Bank : {acc.bank_name} ({acc.currency})",
                      f"No. Rekening : {acc.account_identifier}",
                      f"Atas Nama : {acc.account_name}"]

    parts += ["", "Terima kasih,", f"*{signature}*"]
    return "\n".join(parts)


CHAT_MODULES = ('invoice', 'cl')


def get_chat_reply(
    message: str,
    history: list | None = None,
    *,
    user,
    modules=CHAT_MODULES,
) -> str | None:
    """Answer from recent invoices and CLs of `user`'s branches.
    `modules` is what the user may view: data of any other module or branch is
    not even read, so it can reach neither the answer nor the model provider."""
    from .branch_scope import scope
    today = timezone.now().date()
    month = today.month
    year  = today.year

    invoices = list(scope(Invoice.objects.filter(invoice_type="hotel"), user).with_lines()
                    .order_by("-created_at")[:20]) if 'invoice' in modules else []
    cls      = list(scope(ConfirmationLetter.objects.all(), user).prefetch_related('rooms')
                    .order_by("-created_at")[:20]) if 'cl' in modules else []

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
    needs_cl = is_followup or any(k in msg_lower for k in [
        'cl', 'confirmation', 'letter', 'tamu', 'guest', 'check', 'kamar', 'room', 'reservasi'
    ])
    if not (needs_inv or needs_cl):
        needs_inv = needs_cl = True
    needs_inv = needs_inv and 'invoice' in modules
    needs_cl = needs_cl and 'cl' in modules

    summary = []
    if 'invoice' in modules:
        summary.append(
            f"Invoice Hotel: {len(invoices)} total | {inv_total:,.0f} SAR | Sisa: {inv_remaining:,.0f} SAR | {inv_unpaid} belum lunas\n"
            f"Bulan ini: {len(inv_this_month)} invoice | {inv_month_total:,.0f} SAR"
        )
    if 'cl' in modules:
        summary.append(f"Confirmation Letter: {len(cls)} total")

    system_parts = [
        f"Kamu adalah asisten HMS (Hotel Management System). Jawab berdasarkan data berikut.\n"
        f"Jawab dalam Bahasa Indonesia, singkat dan padat. "
        f"Gunakan bullet point (- item) untuk daftar biasa. "
        f"Untuk daftar invoice hotel gunakan: [inv: nomor | nama | total SAR | sisa SAR | Lunas/Belum lunas] satu per baris. "
        f"Jika ditanya data yang tidak ada di bawah, jawab bahwa pengguna tidak punya akses ke data itu. "
        f"Jangan ulangi info yang tidak perlu. Data milik: Konoz United. Hari ini: {today}.\n\n"
        f"=== RINGKASAN ===\n" + "\n".join(summary)
    ]

    if needs_inv:
        inv_lines = "\n".join(
            f"- {i.invoice_number} | {i.customer_name} | Total: {i.total_sar:,.0f} SAR | "
            f"Sisa: {i.remaining_sar:,.0f} SAR | {'Lunas' if i.remaining_sar == 0 else 'Belum lunas'} | "
            f"{i.issued_date or '-'}"
            for i in invoices
        )
        system_parts.append(f"\n\n=== INVOICE HOTEL ===\n{inv_lines}")

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
