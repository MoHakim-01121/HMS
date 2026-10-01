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


class Language(models.TextChoices):
    EN = 'en', 'English'
    ID = 'id', 'Indonesian'


class UserProfile(models.Model):
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    # Slug sebuah RoleDefinition. Peran dibuat saat runtime, jadi tanpa
    # `choices`; di PostgreSQL kolom ini FOREIGN KEY ke hw_roledefinition.slug
    # (migrasi 0136), di aplikasi dijaga permissions.is_valid_role().
    role   = models.CharField(max_length=32, default=Role.STAFF)
    # True = semua cabang; False = hanya cabang di UserBranchAccess.
    all_branches = models.BooleanField(default=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.EN)

    class Meta:
        verbose_name        = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return self.user.username

    @property
    def has_all_branches(self):
        return self.all_branches

    @property
    def branches(self):
        """Branch codes this profile may act in (all_branches → every active branch)."""
        from .branch import Branch
        qs = Branch.objects.filter(is_active=True)
        if not self.all_branches:
            qs = qs.filter(code__in=self.branch_access.values('branch_id'))
        return list(qs.values_list('code', flat=True))


class UserBranchAccess(models.Model):
    """Cabang yang boleh dipakai profil yang tidak punya akses semua cabang."""

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='branch_access')
    branch  = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='+')

    class Meta:
        verbose_name = 'User Branch Access'
        verbose_name_plural = 'User Branch Access'
        constraints = [
            models.UniqueConstraint(fields=['profile', 'branch'], name='user_branch_access_uniq'),
        ]

    def __str__(self):
        return f"{self.profile} → {self.branch_id}"
