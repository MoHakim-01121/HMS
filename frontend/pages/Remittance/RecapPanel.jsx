import { router } from "@inertiajs/react";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { fmt } from "../../utils/format.js";

// The monthly recap of transfers to HQ (the Remittance page's Recap view).
const RECAP_PILL = {
  received: { tone: "green", label: "Received" },
  partial: { tone: "blue", label: "Partially received" },
  pending: { tone: "yellow", label: "Pending" },
};

export default function RecapPanel({ monthly, t }) {
  if (!monthly || !monthly.length) {
    return <EmptyState iconName="invoice" title={t("No remittances yet")} sub={t("Nothing recorded")} />;
  }
  return (
    <div className="recap-list">
      {monthly.map((m) => (
        <div key={m.period} className="recap-group">
          <div className="recap-group-head">
            <span className="recap-group-label">{m.label}</span>
            <span className="recap-group-stats">
              {t("Sent")} {fmt(m.total_sent)} · {t("Received")} {fmt(m.total_received)}
              {m.total_outstanding ? ` · ${t("In transit")} ${fmt(m.total_outstanding)}` : ""}
              {m.total_difference ? ` · ${t("Difference")} ${fmt(m.total_difference)}` : ""} SAR
              <a className="recap-pdf" href={`/remittance/export/pdf/?month=${m.period}`} target="_blank" rel="noreferrer">PDF</a>
            </span>
          </div>
          <Table
              framed
              columns={[
                { header: t("Remittance No"), mobile: "primary", render: (x) => x.remittance_number },
                {
                  header: t("Status"),
                  mobile: "badge",
                  render: (x) => <StatusPill tone={RECAP_PILL[x.state].tone} label={t(RECAP_PILL[x.state].label)} />,
                },
                { header: t("Date"), mobile: "hide", render: (x) => x.date },
                { header: t("Lines"), mobile: "hide", render: (x) => x.lines_count },
                { header: t("Sent"), mobile: "hide", className: "tabular-nums", render: (x) => fmt(x.sent) },
                {
                  header: t("Received"),
                  mobile: "amount",
                  className: "tabular-nums",
                  render: (x) => (
                    <>
                      <span className="m-only recap-m-label">{t("Received")}</span>
                      {x.received ? `${fmt(x.received)} SAR` : "—"}
                      {x.difference ? <span className="recap-diff">{t("difference")} {fmt(x.difference)}</span> : null}
                    </>
                  ),
                },
                {
                  header: "",
                  mobile: "actions",
                  render: (x) => (
                    <RowActions
                      actions={[
                        { icon: "pdf", label: "PDF", href: `/remittance/${x.id}/pdf/`, variant: "green", external: true },
                        { icon: "arrow-up-right", label: t("Open"), href: `/remittance/${x.id}/`, variant: "green" },
                      ]}
                    />
                  ),
                },
              ]}
              rows={m.remittances}
              rowKey={(x) => x.id}
              onRowClick={(x) => router.visit(`/remittance/${x.id}/`)}
            />
        </div>
      ))}
    </div>
  );
}


export const RECAP_CSS = `
.recap-pdf { margin-left: 10px; font-weight: 600; color: var(--foreground); text-decoration: none; }
.recap-pdf:hover { text-decoration: underline; }
.recap-m-label { margin-right: 6px; font-size: 10px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: var(--muted-foreground); }
.recap-diff { display: block; font-size: 11px; font-weight: 400; color: var(--muted-foreground); }
`;
