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
    """Sync Reservation.total_sar with the current CL total_price, and record
    the delta as a revision Charge so the ledger doesn't drift out of sync
    with the cache every time a room's price/quantity changes."""
    from datetime import date
    from .models import Reservation, Charge, ChargeReason
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
        Charge.objects.create(
            company=cl.company, client=cl.client, invoice_id=cl.invoice_id, date=date.today(),
            amount_sar=new_total - old_total, reservation=reservation, reason=ChargeReason.REVISION,
            description=f'Sinkron dari CL {cl.confirmation_number} (perubahan kamar)',
        )
    logger.info(
        "ledger: revision charge %s SAR for reservation %s (CL %s, invoice %s)",
        new_total - old_total, reservation.pk, cl.confirmation_number, cl.invoice_id,
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
