import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

export default function Tracking({ clients, total_sisa_kirim }) {
  const { t } = useI18n();

  return (
    <div className="page shadcn-root">
      <PageBack href="/remittance/" />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Remittance Tracking")}</div>
          <div className="page-sub">{t("Per client and reservation: sent to HQ, remaining idle funds, and which RMT covered them")}</div>
        </div>
        <div className="page-actions">
          <a href="/remittance/" className="btn btn-secondary" style={{ height: 32, padding: "0 12px", fontSize: 13 }}>{t("Remittances")}</a>
        </div>
      </div>

      <div className="hms-kpi-row cols-3">
        <KpiCard
          label={t("Still at Surabaya")}
          value={fmt(total_sisa_kirim)}
          unit="SAR"
          icon="clock"
          tone={total_sisa_kirim > 0 ? "yellow" : "green"}
          foot={t("not yet covered by any remittance")}
        />
      </div>

      {clients.length ? clients.map((c) => (
        <div className="card" key={c.client_name} style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{c.client_name}</span>
              <span style={{ fontSize: 12, color: "var(--text-3)", marginLeft: 8 }}>
                {t("{n} reservations", { n: c.reservations.length })}
              </span>
            </div>
            <div style={{ display: "flex", gap: 16, fontSize: 12 }}>
              <span>{t("Sent")}: <b className="mono">{fmt(c.total_dikirim)} SAR</b></span>
              <span>{t("Idle")}: <b className="mono" style={{ color: c.total_mengendap > 0 ? "var(--yellow)" : undefined }}>{fmt(c.total_mengendap)} SAR</b></span>
            </div>
          </div>

          <Table
            columns={[
              {
                header: t("Res#"),
                className: "col-m-primary col-nowrap",
                render: (r) => (
                  <>
                    <span className="mono" style={{ fontWeight: 700, fontSize: 12 }}>{r.linked_number}</span>
                    <span className="sub">{r.invoice_number}</span>
                  </>
                ),
              },
              {
                header: t("Hotel"),
                headerClassName: "col-m-hide",
                render: (r) => r.hotel,
              },
              { header: t("Check-in"), align: "right", render: (r) => r.check_in || "—" },
              { header: t("Total"), align: "right", render: (r) => fmt(r.total_sar) },
              { header: t("Paid SBY"), align: "right", render: (r) => fmt(r.terbayar_sby) },
              { header: t("Direct"), align: "right", render: (r) => (r.terbayar_direct ? fmt(r.terbayar_direct) : "—") },
              {
                header: t("Sent to HQ"),
                align: "right",
                strong: true,
                render: (r) => fmt(r.sudah_dikirim),
              },
              {
                header: t("Remaining"),
                align: "right",
                render: (r) =>
                  r.sisa_kirim > 0
                    ? <span style={{ color: "var(--yellow)", fontWeight: 700 }}>{fmt(r.sisa_kirim)}</span>
                    : r.mengendap < 0
                      ? <span style={{ color: "var(--muted-foreground)" }} title={t("HQ sent more than received for this reservation")}>{fmt(r.mengendap)}</span>
                      : "0",
              },
              {
                header: t("RMT"),
                render: (r) =>
                  r.rmts.length ? (
                    <span style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {r.rmts.map((h) => (
                        <a key={`${r.linked_number}-${h.rmt_id}-${h.amount_sar}`}
                          href={`/remittance/${h.rmt_id}/`}
                          onClick={(e) => { e.stopPropagation(); router.visit(`/remittance/${h.rmt_id}/`); }}
                          title={`${h.date || ""} · ${fmt(h.amount_sar)} SAR · ${h.status}`}
                          className={`badge ${h.status === "received" ? "badge-green" : "badge-yellow"}`}
                          style={{ textDecoration: "none", fontSize: 11 }}>
                          {h.number} · {fmt(h.amount_sar)}
                        </a>
                      ))}
                    </span>
                  ) : (
                    <span style={{ color: "var(--muted-foreground)", fontSize: 12 }}>{t("Not sent yet")}</span>
                  ),
              },
            ]}
            rows={c.reservations}
            rowKey={(r) => r.linked_number}
          />
        </div>
      )) : (
        <div className="card">
          <EmptyState iconName="invoice" title="Nothing to track" sub="No active reservations yet" />
        </div>
      )}
    </div>
  );
}
