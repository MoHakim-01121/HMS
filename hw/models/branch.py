"""Branch — dimensi organisasi KONOZ (bukan tenant, bukan legal entity).

KONOZ adalah satu organisasi bisnis tunggal; `Branch` hanya menandai konteks
operasional sebuah fakta bisnis (pemilik reservasi, kas penerima, beban, dll).
Cabang aktif saat ini: Surabaya. Jakarta/Pusat sudah di-seed untuk kesiapan.

Lihat docs/superpowers/plans/2026-09-10-konoz-hms-master-architecture-gap-analysis.md
(FASE A). `Company` masih ada sebagai shim dan akan dihapus di fase cleanup.
"""
from django.db import models


class Branch(models.Model):
    # Kode pendek jadi PK — dipakai sebagai nilai di UserProfile.branch_access
    # dan enak dibaca di admin/URL. Selaras dengan string cabang lama
    # (PaymentRecord.received_in: sby/jkt/pusat).
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=100)
    # Pusat (head office) tetap cabang biasa; penanda ini dipakai aturan
    # "Pusat hanya menerima SAR" dan "setoran menuju Pusat". Tepat satu baris.
    is_hq = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        constraints = [
            models.UniqueConstraint(
                fields=['is_hq'], condition=models.Q(is_hq=True), name='branch_single_hq',
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"
