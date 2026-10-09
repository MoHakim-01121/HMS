import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const STATUS_TONE = {
  open: "green",
  soft_close: "yellow",
  closed: "orange",
  locked: "gray",
};

export default function List({ periods = [], seasons = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canManage = perms.can("periods", "edit");
  const [confirm, confirmDialog] = useConfirm();
  const [createDialog, setCreateDialog] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());
  const [season, setSeason] = useState(null); // {id?, name, date_from, date_to} while the dialog is open

  const saveSeason = () => {
    const { id, ...data } = season;
    router.post(id ? `/finance/seasons/${id}/edit/` : "/finance/seasons/create/", data, {
      // A refused season comes back as an error flash: keep the dialog and its input.
      onSuccess: (page) => { if (!page.props.flash?.error) setSeason(null); },
    });
  };
  // Calendar months a season spans — the periods it closes by.
  const monthsIn = (s) => {
    const [fy, fm] = s.date_from.split("-").map(Number);
    const [ty, tm] = s.date_to.split("-").map(Number);
    return (ty - fy) * 12 + (tm - fm) + 1;
  };

  const seasonColumns = [
    {
      header: t("Season"),
      className: "col-m-primary",
      render: (s) => <span className="col-bold col-nowrap">{s.name}</span>,
    },
    {
      header: t("Date Range"),
      className: "col-m-secondary",
      render: (s) => `${fmtDate(s.date_from)} — ${fmtDate(s.date_to)}`,
    },
    {
      header: t("Months"),
      className: "col-m-hide",
      render: (s) => <span className="font-mono">{monthsIn(s)}</span>,
    },
    {
      header: "",
      className: "col-m-actions",
      render: (s) => canManage ? (
        <RowActions
          actions={[
            { label: t("Edit"), onClick: () => setSeason({ ...s }) },
            { label: t("Delete"), destructive: true, onClick: () => confirm({ title: t("Delete Season"), message: t("Delete this season? Its monthly periods and journal entries stay as they are."), onConfirm: () => router.post(`/finance/seasons/${s.id}/delete/`) }) },
          ]}
        />
      ) : null,
    },
  ];

  const createPeriods = () => {
    router.post("/finance/periods/create/", { year });
    setCreateDialog(false);
  };

  const columns = [
    {
      header: t("Period"),
      className: "col-m-primary",
      render: (p) => <span className="col-bold col-nowrap">{p.name}</span>,
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (p) => <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />,
    },
    {
      header: t("Date Range"),
      className: "col-m-secondary",
      render: (p) => `${p.date_from} — ${p.date_to}`,
    },
    {
      header: t("Journal Entries"),
      className: "col-m-hide",
      render: (p) => <span className="font-mono">{p.journal_count}</span>,
    },
    {
      header: t("Payments"),
      className: "col-m-hide",
      render: (p) => <span className="font-mono">{p.payment_count}</span>,
    },
    {
      header: "",
      className: "col-m-actions",
      render: (p) => (
        <RowActions
          actions={[
            ...(canManage && p.is_postable ? [
              { label: t("Close"), onClick: () => confirm({ title: t("Close Period"), message: t("Close this period?"), onConfirm: () => router.post(`/finance/periods/${p.id}/close/`) }) },
            ] : []),
            ...(canManage && p.status === "closed" ? [
              { label: t("Lock"), destructive: true, onClick: () => confirm({ title: t("Lock Period"), message: t("Lock this period? This is irreversible."), onConfirm: () => router.post(`/finance/periods/${p.id}/lock/`) }) },
            ] : []),
          ]}
        />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Financial Periods")}
        sub={t("Manage accounting periods and locking.")}
        actions={
          canManage && (
            <>
              <Button type="button" variant="outline" size="lg" onClick={() => setCreateDialog(true)}>+ {t("Create Periods")}</Button>
              <Button type="button" size="lg" onClick={() => setSeason({ name: "", date_from: "", date_to: "" })}>+ {t("New Season")}</Button>
            </>
          )
        }
      />

      <div className="hms-list-card" style={{ marginBottom: 24 }}>
        <div style={{ padding: "16px 16px 8px" }}>
          <div className="col-bold">{t("Umrah Seasons")}</div>
          <div className="text-sm text-muted-foreground">{t("A season groups its months for reporting. The books still close month by month.")}</div>
        </div>
        {seasons.length > 0 ? (
          <Table columns={seasonColumns} rows={seasons} rowKey={(s) => s.id} />
        ) : (
          <EmptyState iconName="calendar" title={t("No seasons yet")} sub={t("Add a season with its start and end date to read reports for the whole season.")} />
        )}
      </div>

      <div className="hms-list-card">
        {periods.length > 0 ? (
          <Table
            columns={columns}
            rows={periods}
            rowKey={(p) => p.id}
            onRowClick={(p) => router.visit(`/finance/periods/${p.id}/`)}
          />
        ) : (
          <EmptyState iconName="wallet" title="No periods found" sub="Click 'Create Periods' to generate monthly periods for a year." />
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
      {season && (
        <Dialog open onOpenChange={(v) => { if (!v) setSeason(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{season.id ? t("Edit Season") : t("New Season")}</DialogTitle>
            </DialogHeader>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => { e.preventDefault(); saveSeason(); }}
            >
              <FormField label={t("Name")} name="season_name" required autoFocus
                value={season.name} placeholder={t("e.g. Season 1448H")}
                onChange={(v) => setSeason((s) => ({ ...s, name: v }))} />
              <div className="grid grid-cols-2 gap-3">
                <FormField label={t("Start")} name="season_from" type="date" required
                  value={season.date_from} onChange={(v) => setSeason((s) => ({ ...s, date_from: v }))} />
                <FormField label={t("End")} name="season_to" type="date" required min={season.date_from || undefined}
                  value={season.date_to} onChange={(v) => setSeason((s) => ({ ...s, date_to: v }))} />
              </div>
              <p className="text-sm text-muted-foreground">{t("Monthly periods missing in this range are created for you.")}</p>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSeason(null)}>{t("Cancel")}</Button>
                <Button type="submit" disabled={!season.name.trim() || !season.date_from || !season.date_to}>{t("Save")}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
      {confirmDialog}
    </div>
  );
}
