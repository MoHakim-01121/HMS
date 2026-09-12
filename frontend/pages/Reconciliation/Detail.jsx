import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

export default function Detail({ statement = {} }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("remittance", "edit");
  const [picks, setPicks] = useState({});
  const [forceLine, setForceLine] = useState({});

  const doMatch = (line) => {
    const txId = picks[line.id];
    if (!txId) return;
    router.post(`/finance/reconciliation/lines/${line.id}/match/`, {
      transaction_id: txId, force: forceLine[line.id] ? '1' : '',
    });
  };

  const doUnmatch = (line) => {
    router.post(`/finance/reconciliation/lines/${line.id}/unmatch/`);
  };

  const columns = [
    { header: t("Date"), render: (l) => l.line_date },
    { header: t("Description"), render: (l) => l.description || l.reference || "—" },
    {
      header: t("Amount (SAR)"), align: "right",
      render: (l) => (
        <span style={{ color: l.direction === "in" ? "var(--green)" : "var(--red)" }}>
          {l.direction === "in" ? "+" : "-"}{l.amount_sar?.toLocaleString()}
        </span>
      ),
    },
    {
      header: t("Match"),
      render: (l) => {
        if (l.matched_transaction) {
          return (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <StatusPill tone="green" label={t("Matched")} />
              <span className="text-xs text-muted-foreground">
                {l.matched_transaction.source_type} #{l.matched_transaction.source_id}
              </span>
              {canEdit && (
                <button className="hms-dv-act" style={{ color: "var(--red)" }} onClick={() => doUnmatch(l)}>
                  {t("Unmatch")}
                </button>
              )}
            </div>
          );
        }
        if (!canEdit) return <StatusPill tone="yellow" label={t("Unmatched")} />;
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Select value={picks[l.id] || ""} onValueChange={(v) => setPicks({ ...picks, [l.id]: v })}>
              <SelectTrigger className="w-56"><SelectValue placeholder={t("Select transaction...")} /></SelectTrigger>
              <SelectContent>
                {l.candidates.length === 0 ? (
                  <div style={{ padding: "6px 12px", fontSize: 12, color: "var(--muted-foreground)" }}>{t("No candidates")}</div>
                ) : l.candidates.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.source_type} #{c.source_id} — {c.direction === "in" ? "+" : "-"}{c.amount_sar?.toLocaleString()} ({c.transaction_date})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
              <Checkbox checked={!!forceLine[l.id]} onCheckedChange={(v) => setForceLine({ ...forceLine, [l.id]: !!v })} />
              {t("Force match")}
            </label>
            <Button size="sm" disabled={!picks[l.id]} onClick={() => doMatch(l)}>{t("Match")}</Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack href="/finance/reconciliation/" label={t("Back")} />

      <PageHeader
        title={statement.account_label}
        sub={t("{start} to {end}", { start: statement.period_start, end: statement.period_end })}
      />

      <div className="hms-kpi-row">
        <KpiCard label={t("Book Balance")} value={statement.book_balance_sar?.toLocaleString()} />
        <KpiCard label={t("Statement Closing")} value={statement.closing_balance_sar?.toLocaleString()} />
        <KpiCard label={t("Difference")} value={statement.difference_sar?.toLocaleString()} tone={statement.difference_sar !== 0 ? "yellow" : "green"} />
        <KpiCard label={t("Matched Lines")} value={`${statement.lines_matched}/${statement.lines_total}`} />
      </div>

      <div className="hms-list-card">
        <DetailTable columns={columns} rows={statement.lines || []} rowKey={(l) => l.id} />
      </div>
    </div>
  );
}
