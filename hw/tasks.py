"""Background tasks — WA sends via django-q2.

Send-then-log was historically not atomic: a crash between the external send
and the DB log row caused a silently-missing log entry, and transient Fonnte
failures failed permanently with no retry. ``_send_with_retry`` retries
transient failures with a short backoff.

Note: no content-based idempotency key is applied here. Re-sending an
identical reminder/billing is an intentional application feature (see
SendReminderGroupViewTest), so re-delivery protection belongs at the broker
level (django-q2 ORM broker does not auto-redeliver), not at the task level.
"""
import time

from .models import BillingLog, RecapLog, ReminderLog
from .services.fonnte import send_wa, send_wa_file

_RETRIES = 3
_BACKOFF_SECONDS = [2, 5, 10]


def _send_with_retry(fn):
    """Call ``fn`` up to ``_RETRIES`` times on transient network failures."""
    last_exc = None
    for attempt in range(_RETRIES):
        try:
            return fn()
        except Exception as exc:  # network timeouts, dropped connections, proxy 5xx
            last_exc = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_SECONDS[attempt])
    # All retries exhausted — report the underlying cause so the log row shows
    # the real error (ops) rather than a generic wrapper.
    return {"status": False, "reason": str(last_exc)}


def send_recap_task(target_type, target, label, message, cl_count):
    """Background task: send one recap WA message and log the result.

    Runs out-of-process via django-q2's qcluster worker (see Q_CLUSTER in
    settings) so a slow/unresponsive Fonnte API no longer blocks a gunicorn
    thread for every target in the recap loop.
    """
    result = _send_with_retry(lambda: send_wa(target, message))
    status = "SENT" if result.get("status") else "FAILED"
    error = "" if result.get("status") else (result.get("reason", "") or "unknown error")
    RecapLog.objects.create(
        target_type=target_type, target=target,
        cl_count=cl_count, message=message,
        status=status, triggered_by="MANUAL", error=error,
    )


def send_reminder_group_task(cl_ids, reminder_type, phone, message):
    """Background task: send one grouped reminder WA message, log the result for every CL in the group."""
    result = _send_with_retry(lambda: send_wa(phone, message))
    status = "SENT" if result.get("status") else "FAILED"
    error = "" if result.get("status") else (result.get("reason", "") or "unknown error")
    for cl_id in cl_ids:
        ReminderLog.objects.create(
            cl_id=cl_id, reminder_type=reminder_type,
            phone=phone, status=status, error=error,
        )


def send_billing_task(invoice_id, target, message, with_pdf=False):
    """Background task: send one billing WA message (optionally with the
    invoice PDF attached as a document + caption) and log the result."""
    try:
        from .models import Invoice
        inv = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        # Invoice vanished between scheduling and dispatch — nothing to send.
        BillingLog.objects.create(
            invoice_id=invoice_id, target=target,
            message=message, status="FAILED",
            error="Invoice tidak ditemukan saat task dijalankan",
        )
        return

    def _do_send():
        # Impor lokal: hw.views menarik banyak modul; worker hanya butuh
        # renderer saat benar-benar mengirim PDF.
        from .views.pdf import _render_invoice_pdf, _render_services_pdf
        render = _render_invoice_pdf if inv.invoice_type == "hotel" else _render_services_pdf
        pdf_bytes = render(inv).content
        return send_wa_file(target, message, pdf_bytes, f"{inv.invoice_number}.pdf")

    if with_pdf:
        result = _send_with_retry(_do_send)
    else:
        result = _send_with_retry(lambda: send_wa(target, message))
    status = "SENT" if result.get("status") else "FAILED"
    error = "" if result.get("status") else (result.get("reason", "") or "unknown error")
    BillingLog.objects.create(
        invoice_id=invoice_id, target=target,
        message=message, status=status, error=error,
    )