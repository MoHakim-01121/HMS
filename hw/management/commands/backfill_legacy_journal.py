"""Backfill sejarah: data legacy → jurnal.

Setelah finance redesign di-deploy, jurnal mulai kosong. Command ini membangun
riwayat penuh dari sistem lama (hw_invoice/hw_payment/hw_remittance/
hw_cancellationpenalty) sehingga queries & client statement menampilkan angka
yang benar untuk periode sebelum deploy.

Semantik idempoten — aman dijalankan ulang:
- charge invoice   → idempotent-by-content (posting.post_invoice_charge)
- pembayaran       → PaymentRecord.reference = "backfill:<pk>"; di-skip bila ada
- remittance       → di-skip bila entry TYPE_REMITTANCE hidup sudah ada
- penalty          → di-skip bila entry TYPE_PENALTY hidup sudah ada

Pembayaran ditulis sebagai PaymentRecord (status ALLOCATED, sumber truth baru)
+ journal entry ber-reference PaymentRecord — konsisten dengan desain append-only.

Pemakaian:
    python manage.py backfill_legacy_journal            # dry-run (laporan saja)
    python manage.py backfill_legacy_journal --commit   # eksekusi
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from hw.finance.accounts import seed_chart_of_accounts
from hw.finance.posting import (
    post_invoice_charge,
    post_payment,
    post_penalty_charge,
    post_penalty_payment,
    post_remittance_receive,
    post_remittance_send,
)
from hw.finance_helpers import create_payment_record
from hw.models import (
    CancellationPenalty,
    FinancialPeriod,
    Invoice,
    InvoiceType,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
    PaymentRecord,
    Remittance,
    Reservation,
)

SYSTEM_USERNAME = "system.backfill"
BACKFILL_PREFIX = "backfill"
_ONE_DAY = timedelta(days=1)


def _live_entries(source_type, source_id, entry_type):
    reversed_ids = JournalEntry.objects.filter(
        reverses__isnull=False,
    ).values_list("reverses_id", flat=True)
    return JournalEntry.objects.filter(
        reference_type=source_type,
        reference_id=source_id,
        entry_type=entry_type,
        is_reversal=False,
    ).exclude(pk__in=reversed_ids)


class Command(BaseCommand):
    help = "Backfill riwayat lama (Invoice/Payment/Remittance/Penalty) ke jurnal."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit", action="store_true",
            help="Eksekusi tulis ke DB. Tanpa flag = dry-run (laporan saja).",
        )

    def handle(self, *args, **options):
        self.commit = bool(options["commit"])
        self.stdout.write(self.style.WARNING(
            f"Mode: {'COMMIT' if self.commit else 'DRY-RUN — tidak ada yang ditulis'}"
        ))

        self.user = None
        self.stats = {"invoice": 0, "payment": 0, "remittance": 0, "penalty": 0}
        self.totals = {"invoice": 0, "payment": 0, "remittance": 0, "penalty": 0}
        self.existing = []
        self.skip_unresolved = []
        self.skip_noamount = []
        self.created_periods = []

        invoices = list(
            Invoice.objects.prefetch_related("reservations", "service_items")
            .order_by("issued_date", "pk")
        )
        payments = list(
            Payment.objects.select_related("cl__client", "invoice")
            .order_by("payment_date", "pk")
        )
        remittances = list(
            Remittance.objects.prefetch_related("lines").order_by("date", "pk")
        )
        penalties = list(
            CancellationPenalty.objects.select_related("cl__client")
            .order_by("cancellation_date", "pk")
        )

        all_dates = [
            *(i.issued_date or i.created_at.date() for i in invoices),
            *(p.payment_date for p in payments if p.payment_date),
            *(r.date for r in remittances if r.date),
            *(p.cancellation_date for p in penalties if p.cancellation_date),
        ]
        span = (min(all_dates), max(all_dates)) if all_dates else None

        def _run_all():
            self.resolve = self._resolve_invoice_clients()
            if span:
                self._ensure_periods(*span)
            self._run_invoices(invoices)
            self._run_payments(payments)
            self._run_remittances(remittances)
            self._run_penalties(penalties)

        if self.commit:
            # Semua efek tulis (chart of accounts, system user, resolusi
            # Invoice.client, periode, jurnal) dalam satu transaksi -- kalau
            # ada yang gagal, tidak ada sisa parsial.
            with transaction.atomic():
                seed_chart_of_accounts()
                self.user = self._ensure_system_user()
                _run_all()
                for inv in invoices:
                    if _live_entries("Invoice", inv.pk, JournalEntry.TYPE_CHARGE).exists():
                        inv.sync_status()
        else:
            _run_all()

        self._report()

    # ── Persiapan ──────────────────────────────────────────────

    def _resolve_invoice_clients(self):
        """{invoice.pk: client atau None} via aturan _billing_client.

        Di mode commit, `invoice.client_id` yang ter-resolve di-persist (memperbaiki
        NULL pada data lama) agar post_invoice_charge mendapat dimensi client.
        """
        from hw.views.invoice_billing import _billing_client

        out = {}
        for inv in Invoice.objects.prefetch_related("confirmation_letters__client"):
            out[inv.pk] = _billing_client(inv)
        if self.commit:
            objs = []
            for inv in Invoice.objects.filter(pk__in=list(out)):
                client = out[inv.pk]
                if client is not None and inv.client_id != client.pk:
                    inv.client_id = client.pk
                    objs.append(inv)
            if objs:
                Invoice.objects.bulk_update(objs, ["client_id"])
        return out

    def _ensure_system_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=SYSTEM_USERNAME,
            defaults={
                "first_name": "System",
                "last_name": "Backfill",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            self.stdout.write(f"  System user dibuat: {SYSTEM_USERNAME}")
        return user

    def _ensure_periods(self, min_date, max_date):
        """Pastikan FinancialPeriod bulanan untuk rentang [min_date, max_date]."""
        needed = []
        y, m = min_date.year, min_date.month
        while (y, m) <= (max_date.year, max_date.month):
            name = f"{y}-{m:02d}"
            if not FinancialPeriod.objects.filter(name=name).exists():
                if m == 12:
                    date_to = date(y + 1, 1, 1)
                else:
                    date_to = date(y, m + 1, 1)
                needed.append({
                    "name": name,
                    "date_from": date(y, m, 1),
                    "date_to": date_to - _ONE_DAY,
                })
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1

        self.created_periods = [p["name"] for p in needed]
        if not needed:
            self.stdout.write("  Periode: semua sudah ada")
            return

        self.stdout.write(
            f"  Periode kurang ({len(needed)}): "
            + ", ".join(p["name"] for p in needed)
        )
        if self.commit:
            for p in needed:
                FinancialPeriod.objects.get_or_create(
                    name=p["name"],
                    defaults={
                        "date_from": p["date_from"],
                        "date_to": p["date_to"],
                        "status": FinancialPeriod.STATUS_OPEN,
                    },
                )

    # ── Fase ───────────────────────────────────────────────────

    def _run_invoices(self, invoices):
        for inv in invoices:
            client = self.resolve.get(inv.pk)
            if client is None:
                self.skip_unresolved.append(
                    f"invoice {inv.invoice_number} (client tidak resolve dari CL)"
                )
                continue
            amt = sum(int(r.total_sar or 0) for r in inv.reservations.all())
            amt += sum((s.qty or 0) * (s.price or 0) for s in inv.service_items.all())
            if amt <= 0:
                self.skip_noamount.append(f"invoice {inv.invoice_number}")
                continue

            self.totals["invoice"] += amt
            if self.commit:
                post_invoice_charge(
                    inv, created_by=self.user,
                    entry_date=inv.issued_date or inv.created_at.date(),
                )
            self.stats["invoice"] += 1

    def _run_payments(self, payments):
        for pay in payments:
            if PaymentRecord.objects.filter(
                reference=f"{BACKFILL_PREFIX}:{pay.pk}"
            ).exists():
                self.existing.append(f"payment #{pay.pk}")
                continue

            amount_sar = pay.amount_sar
            if amount_sar <= 0:
                self.skip_noamount.append(
                    f"payment #{pay.pk} untuk {pay.invoice.invoice_number}"
                )
                continue

            client = (pay.cl.client if pay.cl_id and pay.cl and pay.cl.client_id
                      else self.resolve.get(pay.invoice_id))
            if client is None:
                self.skip_unresolved.append(
                    f"payment #{pay.pk} (invoice {pay.invoice.invoice_number}, "
                    "client tidak resolve)"
                )
                continue

            # Validasi yang menentukan skip harus jalan di dry-run juga supaya
            # laporan preview cocok dengan apa yang commit sebenarnya lakukan.
            payment_date = pay.payment_date or (pay.invoice.issued_date if pay.invoice else None)
            if payment_date is None:
                self.skip_unresolved.append(f"payment #{pay.pk} tanpa tanggal")
                continue

            received_in = (
                "pusat" if (pay.method or "").strip().lower() == "direct" else "sby"
            )
            self.totals["payment"] += amount_sar

            if self.commit:
                reservation = service_item = None
                if pay.invoice:
                    res_by_number = {
                        r.reservation_number: r for r in pay.invoice.reservations.all()
                    }
                    reservation = res_by_number.get(pay.linked_number)
                    if reservation is None and pay.invoice.invoice_type != InvoiceType.HOTEL:
                        try:
                            service_item = next(
                                (s for s in pay.invoice.service_items.all()
                                 if s.service_number == int(pay.linked_number)),
                                None,
                            )
                        except (TypeError, ValueError):
                            service_item = None

                pr = create_payment_record(
                    invoice=pay.invoice,
                    client=client,
                    payment_date=payment_date,
                    amount=pay.amount or 0,
                    currency=pay.currency or "SAR",
                    exchange_rate=float(pay.exchange_rate or 1),
                    method=pay.method or "",
                    reference=f"{BACKFILL_PREFIX}:{pay.pk}",
                    note=pay.note or "",
                    created_by=self.user,
                    reservation=reservation,
                    service_item=service_item,
                    received_in=received_in,
                )
                post_payment(pr, created_by=self.user)
                pr.status = PaymentRecord.STATUS_ALLOCATED
                pr.save(update_fields=["status"])
            self.stats["payment"] += 1

    def _run_remittances(self, remittances):
        res_by_number = {}
        for r in Reservation.objects.select_related("invoice").all():
            res_by_number.setdefault(r.reservation_number, r)

        for rmt in remittances:
            lines = list(rmt.lines.all())
            total = sum(int(l.amount_sar or 0) for l in lines)
            if total <= 0:
                self.skip_noamount.append(f"remittance {rmt.remittance_number}")
                continue
            if rmt.date is None:
                self.skip_unresolved.append(f"remittance {rmt.remittance_number} tanpa tanggal")
                continue

            if _live_entries("Remittance", rmt.pk, JournalEntry.TYPE_REMITTANCE).exists():
                self.existing.append(f"remittance {rmt.remittance_number}")
                continue

            self.totals["remittance"] += total
            if self.commit:
                for l in lines:
                    res = res_by_number.get(l.linked_number)
                    # client sisi-kirim: pakai resolusi _billing_client yang sama
                    # dengan sisi pembayaran, bukan Invoice.client mentah yang
                    # sering NULL di data lama.
                    client = self.resolve.get(res.invoice_id) if res else None
                    post_remittance_send(
                        rmt,
                        from_location="sby",
                        amount_sar=int(l.amount_sar or 0),
                        created_by=self.user,
                        entry_date=rmt.date,
                        reservation=res,
                        invoice=res.invoice if res else None,
                        client=client,
                    )
                if rmt.status == Remittance.STATUS_RECEIVED:
                    post_remittance_receive(
                        rmt,
                        expected_sar=total,
                        received_sar=total,
                        created_by=self.user,
                        entry_date=rmt.date,
                    )
            self.stats["remittance"] += 1

    def _run_penalties(self, penalties):
        for pen in penalties:
            amount = pen.penalty_amount_sar
            if amount <= 0:
                self.skip_noamount.append(f"penalty {pen.penalty_number}")
                continue
            client = pen.cl.client if pen.cl_id and pen.cl and pen.cl.client_id else None
            if client is None:
                self.skip_unresolved.append(
                    f"penalty {pen.penalty_number} (client tidak resolve)"
                )
                continue

            if _live_entries(
                "CancellationPenalty", pen.pk, JournalEntry.TYPE_PENALTY
            ).exists():
                self.existing.append(f"penalty {pen.penalty_number}")
                continue

            self.totals["penalty"] += amount
            if self.commit:
                post_penalty_charge(
                    pen, created_by=self.user,
                    entry_date=pen.cancellation_date,
                )
                if pen.is_paid:
                    received_in = (
                        "pusat" if (pen.payment_method or "").lower() == "direct"
                        else "sby"
                    )
                    post_penalty_payment(
                        pen, created_by=self.user,
                        received_in=received_in,
                        entry_date=pen.payment_date,
                    )
            self.stats["penalty"] += 1

    # ── Laporan ────────────────────────────────────────────────

    def _report(self):
        s = self.stats
        t = self.totals

        self.stdout.write("")
        self.stdout.write("== Ringkasan ==")
        self.stdout.write(f"  Charge invoice : {s['invoice']:>4} entri   total {t['invoice']:,} SAR")
        self.stdout.write(f"  Pembayaran     : {s['payment']:>4} entri   total {t['payment']:,} SAR")
        self.stdout.write(f"  Remittance     : {s['remittance']:>4} entri   total {t['remittance']:,} SAR")
        self.stdout.write(f"  Penalty        : {s['penalty']:>4} entri   total {t['penalty']:,} SAR")

        if self.skip_unresolved:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"  Di-SKIP (client tidak resolve, {len(self.skip_unresolved)}): "
                + "; ".join(self.skip_unresolved[:12])
            ))
        if self.skip_noamount:
            self.stdout.write(self.style.WARNING(
                f"  Di-SKIP (tanpa nilai, {len(self.skip_noamount)}): "
                + "; ".join(self.skip_noamount[:12])
            ))
        if self.existing:
            self.stdout.write(self.style.SUCCESS(
                f"  Sudah ada (idempoten, {len(self.existing)}): "
                + "; ".join(self.existing[:12])
            ))
        if self.created_periods:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"  Periode historis dibuat ({len(self.created_periods)}) dengan status OPEN: "
                + ", ".join(self.created_periods)
                + ". Tinjau & tutup lewat menu Periode setelah rekonsiliasi."
            ))

        if not self.commit:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Dry-run — tidak ada yang ditulis. Jalankan dengan --commit untuk mengeksekusi."
            ))
            return

        totals = {
            row["account"]: (row["d"] or 0) - (row["c"] or 0)
            for row in JournalLine.objects
            .values("account").annotate(d=Sum("debit"), c=Sum("credit"))
        }
        self.stdout.write("")
        self.stdout.write("== Saldo per akun (dari jurnal) ==")
        for acc in LedgerAccount.objects.order_by("code"):
            bal = totals.get(acc.code, 0)
            if bal:
                self.stdout.write(f"  {acc.code:<22} {bal:>12,}")

        entries = list(
            JournalEntry.objects.prefetch_related("lines").order_by("seq")
        )
        if entries:
            self.stdout.write("")
            self.stdout.write(
                f"  Total journal entries: {len(entries)} "
                f"(seq terakhir {entries[-1].seq})"
            )
        unbalanced = [e for e in entries if not e.is_balanced]
        self.stdout.write(self.style.SUCCESS(
            f"  Unbalanced entries: {len(unbalanced)}"
        ) if not unbalanced else self.style.ERROR(
            f"  Unbalanced entries: {len(unbalanced)} — {[e.entry_number for e in unbalanced]}"
        ))
        self.stdout.write(self.style.SUCCESS("  Selesai."))