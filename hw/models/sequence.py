"""DocumentSequence — satu baris counter per jenis nomor dokumen.

Penomoran lama mengambil max()+1 sambil mengunci SEMUA baris berprefiks sama,
dan kuncinya lepas sebelum dokumen di-INSERT — dua request bisa mendapat nomor
yang sama. Di sini seluruh penomoran satu jenis dokumen bertumpu pada satu
baris yang dikunci FOR UPDATE di dalam transaksi yang juga meng-INSERT
dokumennya (lihat `hw.numbering`).
"""
from django.db import models


class DocumentSequence(models.Model):
    # Kunci bebas: 'CL', 'INV', 'PAY', 'JE-SEQ', atau per periode seperti
    # 'CN-202609' untuk nomor yang berulang tiap bulan.
    key = models.CharField(max_length=40, primary_key=True)
    last_value = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = 'Document Sequence'
        verbose_name_plural = 'Document Sequences'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(last_value__gte=0),
                name='document_sequence_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.key} = {self.last_value}"
