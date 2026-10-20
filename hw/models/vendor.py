"""Vendor — pemasok yang dibayar lewat pengeluaran (Expense), skema target §3.1.

Vendor menjadi tabel master supaya pengeluaran ke vendor yang sama menunjuk
baris yang sama, bukan teks bebas.
"""
from django.db import models

from .client import client_name_key


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    # Bentuk pembanding nama (sama seperti Client.name_key) — cegah vendor dobel.
    name_key = models.CharField(max_length=200, unique=True, editable=False)
    contact = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name_key = client_name_key(self.name)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'name' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'name_key'}
        super().save(*args, **kwargs)
