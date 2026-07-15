from .models import BillingLog, RecapLog, ReminderLog
from .services.fonnte import send_wa


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


def send_billing_task(invoice_id, target, message):
    """Background task: send one billing WA message and log the result."""
    try:
        result = send_wa(target, message)
        status = 'SENT' if result.get('status') else 'FAILED'
        error = result.get('reason', '') if not result.get('status') else ''
    except Exception as exc:
        status, error = 'FAILED', str(exc)
    BillingLog.objects.create(
        invoice_id=invoice_id, target=target,
        message=message, status=status, error=error,
    )
