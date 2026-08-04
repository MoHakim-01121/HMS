"""Editable role definitions.

RBAC shipped with a hardcoded matrix in ``hw/permissions.py``. That constant is
now only a seed and a fallback: the matrix every request is actually checked
against lives in this table, so an administrator can add a role or re-tick a
permission from the UI without a deploy.

The split is deliberate:

* **In code** — ``MODULES`` and ``ACTIONS``. These are structural. A module only
  exists because views declare ``@require_perm`` for it, so inventing one in the
  UI would hand out a permission nothing checks.
* **In the database** — which role gets which module/action. That is
  configuration, and configuration belongs to the people running the business.

The ``admin`` role is the one exception: it is force-granted everything in
``permissions.role_matrix()`` and refuses edits, so no amount of clicking can
lock the last administrator out of the screen that would undo it.
"""
from django.core.cache import cache
from django.db import models

# Bumped in the key rather than deleted wholesale so a stale value from an old
# deploy can never be read back as current.
MATRIX_CACHE_KEY = 'hw:role_matrix:v1'

# The slug that is always full-access and never editable. Kept here (not in
# permissions.py) so the model can answer `locked` without an import cycle.
ADMIN_SLUG = 'admin'


def invalidate_matrix_cache():
    cache.delete(MATRIX_CACHE_KEY)


class RoleDefinitionQuerySet(models.QuerySet):
    def as_matrix(self):
        """{slug: {module: [actions]}} — lists, not sets, so it pickles small."""
        return {
            r.slug: {m: sorted(a) for m, a in (r.permissions or {}).items() if a}
            for r in self
        }


class RoleDefinition(models.Model):
    """One row per role. ``permissions`` is {module: [action, ...]}."""

    slug = models.SlugField(max_length=32, unique=True)
    label = models.CharField(max_length=64)
    description = models.CharField(max_length=200, blank=True)
    permissions = models.JSONField(default=dict, blank=True)

    # Django admin access is not derivable from the HMS matrix (the two systems
    # guard different things), so it is an explicit switch per role.
    grants_django_staff = models.BooleanField(
        default=False,
        help_text="Members of this role also get Django admin (is_staff).",
    )

    # Seeded roles cannot be deleted: other code and old ActivityLog rows refer
    # to their slugs by name. Custom roles are free game.
    is_system = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=100)

    objects = RoleDefinitionQuerySet.as_manager()

    class Meta:
        ordering = ('order', 'label')
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.label

    @property
    def locked(self):
        """The break-glass role: shown read-only, never editable or deletable."""
        return self.slug == ADMIN_SLUG

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_matrix_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        invalidate_matrix_cache()
        return result
