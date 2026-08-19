from django.db import models

from .choices import Company


def _pricelist_path(instance, filename):
    return f"landing/pricelist/{instance.pk or 'new'}/{filename}"


def _team_photo_path(instance, filename):
    return f"landing/team/{instance.pk or 'new'}/{filename}"


class TeamMember(models.Model):
    """One person shown in the public landing page's Our Team section."""

    company  = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    name     = models.CharField(max_length=120)
    position = models.CharField(max_length=120, blank=True)
    wa       = models.CharField(max_length=30, blank=True,
                                help_text='Nomor WhatsApp, mis. 6281234567890')
    photo    = models.ImageField(upload_to=_team_photo_path, blank=True)
    order    = models.PositiveIntegerField(default=0,
                                           help_text='Urutan tampil di halaman publik')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['order', 'id']
        verbose_name        = 'Anggota Tim'
        verbose_name_plural = 'Anggota Tim'

    def __str__(self):
        return self.name


class Pricelist(models.Model):
    """An uploaded pricelist file shown to agencies on the public site."""

    company   = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)
    title     = models.CharField(max_length=120)
    file      = models.FileField(upload_to=_pricelist_path)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-updated_at']
        verbose_name        = 'Pricelist'
        verbose_name_plural = 'Pricelist'

    def __str__(self):
        return self.title
