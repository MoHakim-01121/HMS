from django.contrib.auth.models import User
from django.db import models


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN  = 'login',  'Login'
        CREATE = 'create', 'Dibuat'
        EDIT   = 'edit',   'Diedit'
        DELETE = 'delete', 'Dihapus'
        PDF    = 'pdf',    'Export PDF'

    ACTION_LOGIN  = Action.LOGIN
    ACTION_CREATE = Action.CREATE
    ACTION_EDIT   = Action.EDIT
    ACTION_DELETE = Action.DELETE
    ACTION_PDF    = Action.PDF

    # Log tetap ada setelah akunnya dihapus; nama pelaku disimpan sebagai snapshot.
    user       = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='activity_logs')
    actor_username = models.CharField(max_length=150)
    action     = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=50, blank=True)
    object_ref = models.CharField(max_length=200, blank=True)
    changes    = models.JSONField(default=list, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-timestamp']
        verbose_name        = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=['login', 'create', 'edit', 'delete', 'pdf']),
                name='activity_log_action_valid',
            ),
        ]

    def __str__(self):
        return f"{self.actor_username} {self.action} {self.object_ref}"

    @property
    def actor_display(self):
        """Nama lengkap pelaku bila akunnya masih ada, selain itu username snapshot."""
        if self.user_id and self.user:
            return self.user.get_full_name() or self.user.username
        return self.actor_username


def log_activity(user, action, model_name='', object_ref='', changes=None):
    ActivityLog.objects.create(
        user=user, actor_username=user.get_username(), action=action, model_name=model_name,
        object_ref=object_ref, changes=changes or [],
    )
