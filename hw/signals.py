from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ActivityLog, Room, UserProfile, log_activity


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    log_activity(user, ActivityLog.ACTION_LOGIN)


def _sync_reservation_total(cl):
    """Sync Reservation.total_sar with the current CL total_price."""
    from .models import Reservation
    if cl.invoice_id:
        Reservation.objects.filter(
            invoice_id=cl.invoice_id,
            reservation_number=cl.confirmation_number,
        ).update(total_sar=int(round(cl.total_price)))


@receiver(post_save, sender=Room)
@receiver(post_delete, sender=Room)
def _room_total_changed(sender, instance, **kwargs):
    _sync_reservation_total(instance.cl)
