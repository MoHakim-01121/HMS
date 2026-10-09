import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Transfer & Penukaran Valas: money moved between our own accounts in one
// branch, in the same currency or exchanged (USD from a client sold for IDR).
// Recorded as two cash-book rows; an exchange also moves the SAR value in
// the ledger.
export default function Exchanges({ exchanges = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();

  const voidEx = (ex) => confirm({
    title: t("Void Transfer"),
    message: t("Void {number}? Both cash-book rows stop counting; the record stays for audit.", { number: ex.exchange_number }),
    confirmLabel: "Void",
    onConfirm: () => router.post(`/finance/exchanges/${ex.id}/void/`),
  });

  const columns = [
    {
      header: t("Transfer #"),
      className: "col-m-primary",
      render: (ex) => <span className="col-bold col-nowrap" style={{ opacity: ex.status === "voided" ? 0.55 : 1 }}>{ex.exchange_number}</span>,
    },
    { header: t("Date"), className: "col-m-meta col-nowrap", render: (ex) => ex.exchange_date },
    {
      header: t("From"),
      className: "col-m-secondary",
      render: (ex) => (
        <>
          <div className="col-nowrap">{fmt(ex.amount_out)} {ex.from_currency}</div>
          <div style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>{ex.from_label}</div>
        </>
      ),
    },
    {
      header: t("To"),
      className: "col-m-secondary",
      render: (ex) => (
        <>
          <div className="col-nowrap">{fmt(ex.amount_in)} {ex.to_currency}</div>
          <div style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>{ex.to_label}</div>
        </>
      ),
    },
    {
      header: t("Rate"),
      className: "col-m-amount text-right",
      render: (ex) => ex.from_currency === ex.to_currency ? <span style={{ color: "var(--muted-foreground)" }}>—</span> : <span className="col-nowrap">{ex.rate.toLocaleString("en-US", { maximumFractionDigits: 4 })} {ex.to_currency}/{ex.from_currency}</span>,
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (ex) => ex.status === "voided"
        ? <StatusPill small tone="gray" label={t("Voided")} />
        : <StatusPill small tone="green" label={t("Active")} />,
    },
    perms.can("payments", "delete") && {
      header: "",
      className: "col-m-actions",
      render: (ex) => ex.status === "active" ? (
        <RowActions actions={[{ icon: "trash", label: t("Void"), variant: "red", onClick: () => voidEx(ex) }]} />
      ) : null,
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Transfer & Exchange")}
        sub={t("Money moved between our own accounts in one branch — same currency, or exchanged, e.g. a client's USD sold for IDR.")}
        actions={perms.can("payments", "create") ? (
          <Button size="lg" onClick={() => openForm("/finance/exchanges/new/")}>+ {t("New Transfer")}</Button>
        ) : null}
      />
      <div className="hms-list-card">
        {exchanges.length > 0 ? (
          <Table columns={columns.filter(Boolean)} rows={exchanges} rowKey={(ex) => ex.id} />
        ) : (
          <EmptyState iconName="globe" title={t("No transfers yet")} sub={t("Record one when money moves between your accounts or is exchanged.")} />
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
