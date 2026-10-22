"""HQ settlement domain (Master Architecture v2.0 §33–39, §80).

DITAMBAHKAN di atas `Remittance`/`RemittanceLine` yang sudah ada
(hw/models/remittance.py) — tidak menggantikannya. `Remittance` tetap
mewakili transfer fisik (kirim); jalur lama `Remittance.received_amount_sar`
+ `post_remittance_receive()` (satu tanda terima lump-sum) tetap berjalan
untuk remittance yang sudah dikelola begitu. `RemittanceSettlement` adalah
jalur BARU (dipakai lewat `hw.finance.settlement_service`) untuk remittance
yang diterima BERTAHAP — satu transfer bisa punya banyak settlement.

Catatan audit 2026-09-14: `HQObligation`/`RemittanceAllocation` (kewajiban
cabang yang diselesaikan per-settlement) sempat ada di sini tapi dihapus —
tidak pernah tersambung ke event nyata manapun (RemittanceLine/Reservation),
0 baris data, dan `create_obligation()`/`allocate_settlement()` hanya
dipanggil dari form manual yang tak pernah dipakai. Lihat migration 0102.
"""
from django.db import models


class LiveSettlementManager(models.Manager):
    """Penerimaan yang berlaku (yang dibatalkan tidak dihitung di mana pun)."""

    def get_queryset(self):
        return super().get_queryset().filter(voided_at__isnull=True)


class RemittanceSettlement(models.Model):
    """Satu tanda terima aktual di pusat untuk sebagian/seluruh sebuah Remittance.

    Nominal DITERIMA (bukan yang diharapkan) adalah source of truth — lihat
    v2.0 §36. Satu Remittance boleh punya banyak baris ini (kirim bertahap
    diterima, atau satu kiriman dipecah beberapa tanda terima)."""

    remittance         = models.ForeignKey('Remittance', on_delete=models.PROTECT, related_name='settlements')
    received_amount_sar = models.PositiveIntegerField()
    received_date       = models.DateField()
    reference            = models.CharField(max_length=200, blank=True)
    note                 = models.TextField(blank=True)
    created_by           = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at            = models.DateTimeField(auto_now_add=True)
    # Penerimaan yang salah catat dibatalkan, tidak dihapus: jurnalnya (dan
    # pembaliknya) tetap menunjuk dokumen ini.
    voided_at             = models.DateTimeField(null=True, blank=True)

    objects = LiveSettlementManager()
    all_objects = models.Manager()  # noqa: DJ012 -- a manager, not a field

    class Meta:
        base_manager_name = 'all_objects'
        ordering = ['received_date', 'id']
        verbose_name = 'Remittance Settlement'
        verbose_name_plural = 'Remittance Settlements'

    def __str__(self):
        return f"Settlement {self.remittance.remittance_number} {self.received_amount_sar:,} SAR"
