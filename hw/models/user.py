from django.contrib.auth.models import User
from django.db import models


class Role(models.TextChoices):
    """The four seeded roles.

    Roles are editable rows now (see ``hw.models.role.RoleDefinition``), so this
    is no longer the full list — it names the built-ins that code refers to by
    slug (seeding, the staff default, the admin break-glass). Never use it to
    validate a submitted role; use ``permissions.is_valid_role()``.
    """
    ADMIN   = 'admin',   'Administrator'
    MANAGER = 'manager', 'Manager'
    STAFF   = 'staff',   'Staff'
    VIEWER  = 'viewer',  'Viewer'


class BranchAccess(models.TextChoices):
    """Sentinel untuk akses semua cabang. Nilai lain = satu Branch.code (mis. 'sby')."""
    ALL = 'all', 'All branches'


class Language(models.TextChoices):
    EN = 'en', 'English'
    ID = 'id', 'Indonesian'


class UserProfile(models.Model):
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    # No `choices`: custom roles are created at runtime, so the valid set lives
    # in RoleDefinition and is enforced by the views, not by the field.
    role   = models.CharField(max_length=32, default=Role.STAFF)
    # 'all' = semua cabang; selain itu satu Branch.code.
    branch_access = models.CharField(max_length=10, default=BranchAccess.ALL)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.EN)

    class Meta:
        verbose_name        = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return self.user.username

    @property
    def has_all_branches(self):
        return self.branch_access == BranchAccess.ALL

    @property
    def branches(self):
        """Branch codes this profile may act in ('all' → every active branch)."""
        from .branch import Branch
        qs = Branch.objects.filter(is_active=True)
        if not self.has_all_branches:
            qs = qs.filter(code=self.branch_access)
        return list(qs.values_list('code', flat=True))
