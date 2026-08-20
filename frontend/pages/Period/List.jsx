import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  open: "green",
  soft_close: "yellow",
  closed: "orange",
  locked: "gray",
};

export default function List({ periods = [] }) {
  const { t } = useI18n();
  const [createDialog, setCreateDialog] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());

  const createPeriods = () => {
    router.post("/finance/periods/create/", { year });
    setCreateDialog(false);
  };

  const columns = [
    {
      header: t("Period"),
      render: (p) => (
        <a href={`/finance/periods/${p.id}/`} className="text-blue-600 hover:underline font-medium">
          {p.name}
        </a>
      ),
    },
    {
      header: t("Date Range"),
      render: (p) => `${p.date_from} — ${p.date_to}`,
    },
    {
      header: t("Status"),
      render: (p) => <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />,
    },
    {
      header: t("Journal Entries"),
      align: "right",
      render: (p) => <span className="font-mono">{p.journal_count}</span>,
    },
    {
      header: t("Payments"),
      align: "right",
      render: (p) => <span className="font-mono">{p.payment_count}</span>,
    },
    {
      header: "",
      className: "w-10",
      render: (p) => (
        <RowActions
          actions={[
            { label: t("Detail"), href: `/finance/periods/${p.id}/` },
            ...(p.is_postable ? [
              { label: t("Close"), onClick: () => { if (confirm(t("Close this period?"))) router.post(`/finance/periods/${p.id}/close/`); } },
            ] : []),
            ...(p.status === "closed" ? [
              { label: t("Lock"), onClick: () => { if (confirm(t("Lock this period? This is irreversible."))) router.post(`/finance/periods/${p.id}/lock/`); }, destructive: true },
            ] : []),
          ]}
        />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Financial Periods")}</div>
          <div className="page-sub">{t("Manage accounting periods and locking.")}</div>
        </div>
        <div className="page-actions">
          <a href="/finance/payments/" className="btn btn-secondary btn-sm">{t("Payments")}</a>
          <button className="btn btn-primary btn-sm" onClick={() => setCreateDialog(true)}>{t("Create Periods")}</button>
        </div>
      </div>

      <div className="card">
        {periods.length > 0 ? (
          <Table columns={columns} rows={periods} rowKey={(p) => p.id} />
        ) : (
          <div className="empty">
            <div className="empty-title">{t("No periods found")}</div>
            <div className="empty-sub">{t("Click 'Create Periods' to generate monthly periods for a year.")}</div>
          </div>
        )}
      </div>

      {/* Create Periods Dialog */}
      {createDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setCreateDialog(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Create Financial Periods")}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground mb-4">
              {t("Create 12 monthly periods for the selected year.")}
            </p>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">{t("Year")}:</label>
              <Input
                type="number"
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value) || new Date().getFullYear())}
                className="w-24"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={createPeriods}>{t("Create")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
