import logging
import threading
from contextlib import contextmanager

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ActivityLog, Room, UserProfile, log_activity

logger = logging.getLogger(__name__)
_state = threading.local()


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    log_activity(user, ActivityLog.ACTION_LOGIN)


@contextmanager
def invoice_sync_suspended():
    """Tunda penyesuaian invoice selama blok ini.

    Mengedit CL menulis ulang semua kamarnya; tanpa ini charge invoice
    di-reverse dan diposting ulang sekali per kamar. Pemanggil wajib memanggil
    sync_invoice_for_cl() sendiri setelah blok selesai."""
    previous = getattr(_state, 'suspended', False)
    _state.suspended = True
    try:
        yield
    finally:
        _state.suspended = previous


def sync_invoice_for_cl(cl, user=None):
    """CL berubah → invoice yang menagihnya ikut berubah.

    Baris invoice tidak menyimpan nilai (dibaca dari CL), jadi yang perlu
    disesuaikan hanya jurnalnya: post_invoice_charge idempotent-by-content,
    me-reverse charge lama dan memposting yang baru bila nilainya berubah,
    sekaligus mencatat InvoiceRevision."""
    from .finance.posting import post_invoice_charge
    from .models.invoice import InvoiceRevision

    line = cl.invoice_line
    if line is None:
        return None
    entry = post_invoice_charge(line.invoice, created_by=user, reason=InvoiceRevision.REASON_CL_CHANGE)
    logger.info("ledger: invoice %s follows CL %s", line.invoice_id, cl.confirmation_number)
    return entry


@receiver(post_save, sender=Room)
@receiver(post_delete, sender=Room)
def _room_total_changed(sender, instance, **kwargs):
    if getattr(_state, 'suspended', False):
        return
    sync_invoice_for_cl(instance.cl)
