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

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action     = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=50, blank=True)
    object_ref = models.CharField(max_length=200, blank=True)
    company    = models.CharField(max_length=20, blank=True)
    changes    = models.JSONField(default=list, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-timestamp']
        verbose_name        = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"{self.user.username} {self.action} {self.object_ref}"


def log_activity(user, action, model_name='', object_ref='', company='', changes=None):
    ActivityLog.objects.create(
        user=user, action=action, model_name=model_name,
        object_ref=object_ref, company=company, changes=changes or [],
    )
