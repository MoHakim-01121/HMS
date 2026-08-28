import logging

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ActivityLog, Client, Room, UserProfile, log_activity

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    log_activity(user, ActivityLog.ACTION_LOGIN)


def _sync_reservation_total(cl):
    """Sync Reservation.total_sar dengan CL.total_price, lalu re-post charge
    jurnal invoice (posting.post_invoice_charge idempotent-by-content:
    reverse charge lama + repost dengan total baru)."""
    from .models import Reservation
    if not cl.invoice_id:
        return
    reservation = Reservation.objects.filter(
        invoice_id=cl.invoice_id,
        reservation_number=cl.confirmation_number,
    ).first()
    if not reservation:
        return
    old_total = reservation.total_sar
    new_total = int(round(cl.total_price))
    if new_total == old_total:
        return
    with transaction.atomic():
        reservation.total_sar = new_total
        reservation.save(update_fields=['total_sar'])
        invoice = reservation.invoice
        if invoice.client_id:
            from .finance.posting import post_invoice_charge
            post_invoice_charge(invoice, created_by=None)
    logger.info(
        "ledger: reposted invoice %s charge after reservation %s changed to %s SAR",
        cl.invoice_id, reservation.pk, new_total,
    )


@receiver(post_save, sender=Room)
@receiver(post_delete, sender=Room)
def _room_total_changed(sender, instance, **kwargs):
    _sync_reservation_total(instance.cl)


@receiver(post_save, sender=Client)
def _sync_client_display_name(sender, instance, **kwargs):
    """Keep CL.guest_name / Invoice.customer_name mirroring the client's
    display name (brand, falling back to the registered name) so every CL
    and invoice for a client reads identically instead of drifting apart
    the moment a brand gets added or edited after the fact."""
    from .models import ConfirmationLetter, Invoice
    display_name = instance.brand or instance.name

    ConfirmationLetter.objects.filter(client=instance).exclude(guest_name=display_name).update(guest_name=display_name)

    linked_invoice_ids = set(
        ConfirmationLetter.objects.filter(client=instance, invoice__isnull=False)
        .values_list('invoice_id', flat=True)
    )
    # An invoice whose CLs span more than one client is ambiguous -- same
    # rule invoice_billing._billing_client() uses -- so leave its customer_name alone.
    unambiguous_ids = [
        inv_id for inv_id in linked_invoice_ids
        if set(ConfirmationLetter.objects.filter(invoice_id=inv_id).values_list('client_id', flat=True)) == {instance.pk}
    ]
    if unambiguous_ids:
        Invoice.objects.filter(pk__in=unambiguous_ids).exclude(customer_name=display_name).update(customer_name=display_name)
