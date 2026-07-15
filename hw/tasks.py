from .models import BillingLog, RecapLog, ReminderLog
from .services.fonnte import send_wa, send_wa_file


def send_recap_task(target_type, target, label, message, cl_count):
    """Background task: send one recap WA message and log the result.

    Runs out-of-process via django-q2's qcluster worker (see Q_CLUSTER in
    settings) so a slow/unresponsive Fonnte API no longer blocks a gunicorn
    thread for every target in the recap loop.
    """
    try:
        result = send_wa(target, message)
        status = 'SENT' if result.get('status') else 'FAILED'
        error = result.get('reason', '') if not result.get('status') else ''
    except Exception as exc:
        status, error = 'FAILED', str(exc)
    RecapLog.objects.create(
        target_type=target_type, target=target,
        cl_count=cl_count, message=message,
        status=status, triggered_by='MANUAL', error=error,
    )


def send_reminder_group_task(cl_ids, reminder_type, phone, message):
    """Background task: send one grouped reminder WA message, log the result for every CL in the group."""
    try:
        result = send_wa(phone, message)
        status = 'SENT' if result.get('status') else 'FAILED'
        error = result.get('reason', '') if not result.get('status') else ''
    except Exception as exc:
        status, error = 'FAILED', str(exc)
    for cl_id in cl_ids:
        ReminderLog.objects.create(
            cl_id=cl_id, reminder_type=reminder_type,
            phone=phone, status=status, error=error,
        )


def send_billing_task(invoice_id, target, message, with_pdf=False):
    """Background task: send one billing WA message (optionally with the
    invoice PDF attached as a document + caption) and log the result."""
    try:
        if with_pdf:
            # Impor lokal: hw.views menarik banyak modul; worker hanya butuh
            # renderer saat benar-benar mengirim PDF.
            from .models import Invoice
            from .views.pdf import _render_invoice_pdf, _render_services_pdf
            invoice = Invoice.objects.get(pk=invoice_id)
            render = _render_invoice_pdf if invoice.invoice_type == 'hotel' else _render_services_pdf
            pdf_bytes = render(invoice).content
            result = send_wa_file(target, message, pdf_bytes, f"{invoice.invoice_number}.pdf")
        else:
            result = send_wa(target, message)
        status = 'SENT' if result.get('status') else 'FAILED'
        error = result.get('reason', '') if not result.get('status') else ''
    except Exception as exc:
        status, error = 'FAILED', str(exc)
    BillingLog.objects.create(
        invoice_id=invoice_id, target=target,
        message=message, status=status, error=error,
    )
