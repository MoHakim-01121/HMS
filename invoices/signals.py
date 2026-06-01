from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ActivityLog, UserProfile, log_activity


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    log_activity(user, ActivityLog.ACTION_LOGIN)
