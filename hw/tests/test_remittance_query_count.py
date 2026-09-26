"""Halaman Remittance tidak boleh N+1: jumlah query harus tetap sama walau
jumlah transfer/penerimaan/client bertambah (daftar tidak dipaginasi dan KPI
tab Transfer dihitung ulang tiap kali dibuka)."""
from datetime import date

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from hw.models import Client
from hw.tests.test_remittance_allocation import AllocationBase

PAGES = ('/remittance/', '/remittance/?tab=tracking', '/remittance/?tab=recap', '/remittance/new/')


class RemittanceQueryCountTest(AllocationBase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_superuser('qc', password='pw12345')
        self.client.force_login(admin)
        self._seq = 1

    def _add_transfers(self, n):
        for _ in range(n):
            self._seq += 1
            rem = self._transfer(9_600_000, 4800, date(2026, 9, 10), number=f'RMT-QC-{self._seq}')
            self._receive(1000, date(2026, 9, 12), None, rem=rem)
            Client.objects.create(name=f'Client QC {self._seq}')

    def _counts(self):
        out = {}
        for url in PAGES:
            self.client.get(url)  # warm-up: cache-miss queries would mask growth
            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            out[url] = len(ctx.captured_queries)
        return out

    def test_query_count_does_not_grow_with_transfers(self):
        self._add_transfers(2)
        few = self._counts()
        self._add_transfers(6)
        many = self._counts()
        self.assertEqual(few, many)
