import { router } from "@inertiajs/react";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { Pill } from "../../components/shadcn/list-a.jsx";
import { fmt } from "../../utils/format.js";

// The monthly recap of transfers to HQ (the Remittance page's Recap view).
const RECAP_PILL = {
  received: { tone: "green", label: "Received" },
  partial: { tone: "info-o", label: "Partially received" },
  pending: { tone: "amber", label: "Pending" },
};

export default function RecapPanel({ monthly, t }) {
  if (!monthly || !monthly.length) {
    return <EmptyState iconName="invoice" title={t("No remittances yet")} sub={t("Nothing recorded")} />;
  }
  return (
    <div className="flex flex-col gap-[18px]">
      {monthly.map((m) => (
        <div key={m.period}>
          <div className="flex items-baseline justify-between gap-3 px-0.5 pb-2 max-[600px]:flex-col max-[600px]:items-start max-[600px]:gap-0.5">
            <span className="text-[14px] font-semibold text-foreground">{m.label}</span>
            <span className="text-[12px] text-muted-foreground tabular-nums">
              {t("Sent")} {fmt(m.total_sent)} · {t("Received")} {fmt(m.total_received)}
              {m.total_outstanding ? ` · ${t("In transit")} ${fmt(m.total_outstanding)}` : ""}
              {m.total_difference ? ` · ${t("Difference")} ${fmt(m.total_difference)}` : ""} SAR
              <a className="ml-2.5 font-semibold text-foreground no-underline hover:underline" href={`/remittance/export/pdf/?month=${m.period}`} target="_blank" rel="noreferrer">PDF</a>
            </span>
          </div>
          <Table
              framed
              columns={[
                { header: t("Remittance No"), mobile: "primary", render: (x) => x.remittance_number },
                {
                  header: t("Status"),
                  mobile: "badge",
                  render: (x) => <Pill tone={RECAP_PILL[x.state].tone}>{t(RECAP_PILL[x.state].label)}</Pill>,
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
                      <span className="mr-1.5 hidden text-[10px] font-bold tracking-[.5px] text-muted-foreground uppercase max-[600px]:inline-flex">{t("Received")}</span>
                      {x.received ? `${fmt(x.received)} SAR` : "—"}
                      {x.difference ? <span className="block text-[11px] font-normal text-muted-foreground">{t("difference")} {fmt(x.difference)}</span> : null}
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

