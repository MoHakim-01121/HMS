import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from .models import ConfirmationLetter, Invoice
from .models.confirmation import ReservationStatus

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
        today = timezone.localdate()
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


def _invoice_totals(user, today):
    from .branch_scope import scope
    invoices = list(scope(Invoice.objects.filter(invoice_type="hotel").exclude(status=Invoice.STATUS_VOID), user)
                    .with_lines())
    unpaid = [i for i in invoices if i.remaining_sar > 0]
    overdue = [i for i in unpaid if i.due_date and i.due_date < today]
    this_month = [i for i in invoices
                  if (timezone.localtime(i.created_at).year, timezone.localtime(i.created_at).month) == (today.year, today.month)]
    return (
        f"Invoice Hotel: {len(invoices)} invoice | {sum(i.total_sar for i in invoices):,.0f} SAR\n"
        f"Belum lunas: {len(unpaid)} invoice | sisa {sum(i.remaining_sar for i in unpaid):,.0f} SAR\n"
        f"Lewat jatuh tempo: {len(overdue)} invoice | sisa {sum(i.remaining_sar for i in overdue):,.0f} SAR\n"
        f"Dibuat bulan ini: {len(this_month)} invoice | {sum(i.total_sar for i in this_month):,.0f} SAR"
    )


def _cl_totals(user, today):
    from .branch_scope import scope
    live = scope(ConfirmationLetter.objects.exclude(reservation_status=ReservationStatus.CANCELLED), user)
    by_status = live.order_by().values_list('reservation_status').annotate(n=Count('pk'))
    return (
        f"Confirmation Letter aktif: {live.count()} CL ("
        + ", ".join(f"{status}: {n}" for status, n in sorted(by_status)) + ")\n"
        f"Check-in hari ini: {live.filter(check_in=today).count()} CL\n"
        f"Check-in 7 hari ke depan: {live.filter(check_in__gte=today, check_in__lte=today + timedelta(days=7)).count()} CL\n"
        f"Sedang menginap: {live.filter(check_in__lt=today, check_out__gt=today).count()} CL"
    )


def get_chat_reply(
    message: str,
    history: list | None = None,
    *,
    user,
    modules=CHAT_MODULES,
) -> str | None:
    """Answer from totals of `user`'s branches. Only counts and sums leave for
    the model provider, never a client, guest, hotel or document number.
    `modules` is what the user may view: data of any other module or branch is
    not even read."""
    today = timezone.localdate()

    totals = []
    if 'invoice' in modules:
        totals.append(_invoice_totals(user, today))
    if 'cl' in modules:
        totals.append(_cl_totals(user, today))

    system_context = (
        "Kamu adalah asisten KonozOps (sistem manajemen internal Konoz United). Jawab berdasarkan data berikut.\n"
        "Jawab dalam Bahasa Indonesia, singkat dan padat. "
        "Gunakan bullet point (- item) untuk daftar biasa. "
        "Kamu hanya punya angka total, tanpa nama klien, nama tamu, hotel, atau nomor dokumen. "
        "Jika ditanya rincian seperti itu, jawab bahwa rincian ada di halaman daftar Invoice atau CL. "
        "Jika ditanya data lain yang tidak ada di bawah, jawab bahwa data itu tidak tersedia untukmu. "
        f"Jangan ulangi info yang tidak perlu. Data milik: Konoz United. Hari ini: {today}.\n\n"
        "=== TOTAL ===\n" + "\n".join(totals)
    )

    messages = [
        {"role": "system", "content": system_context},
        *(history or []),
        {"role": "user", "content": message},
    ]
    return _call_groq(messages, model=_MODEL_CHAT)
