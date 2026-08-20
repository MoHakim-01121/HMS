import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  open: "badge-green",
  soft_close: "badge-yellow",
  closed: "badge-orange",
  locked: "badge-gray",
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
      render: (p) => (
        <span className={`badge ${STATUS_TONE[p.status] || "badge-gray"}`}>
          {p.status_display}
        </span>
      ),
    },
    {
      header: t("Journal Entries"),
      className: "text-right",
      render: (p) => p.journal_count,
    },
    {
      header: t("Payments"),
      className: "text-right",
      render: (p) => p.payment_count,
    },
    {
      header: "",
      className: "w-10",
      render: (p) => (
        <RowActions
          items={[
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
      <PageBack href="/" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{t("Financial Periods")}</h1>
          <p className="text-muted-foreground text-sm">{t("Manage accounting periods and locking.")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setCreateDialog(true)}>{t("Create Periods")}</Button>
          <a href="/finance/payments/">
            <Button variant="outline" size="sm">{t("Payments")}</Button>
          </a>
        </div>
      </div>

      <Table columns={columns} rows={periods} rowKey="id" />

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
              <label className="text-sm">{t("Year")}:</label>
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
