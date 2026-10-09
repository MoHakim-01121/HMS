import { Link } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Every credit note issued, newest first. They are created from the invoice
// they reduce (Invoice detail → ⋯ → Credit note), not from here.
export default function CreditNotes({ credit_notes = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();

  const columns = [
    {
      header: t("Credit note"),
      className: "col-m-primary",
      render: (cn) => (
        <a className="col-bold col-nowrap" style={{ opacity: cn.status === "voided" ? 0.55 : 1 }} href={`/finance/credit-notes/${cn.id}/pdf/`} target="_blank" rel="noreferrer">
          {cn.number}
        </a>
      ),
    },
    { header: t("Date"), className: "col-m-meta col-nowrap", render: (cn) => cn.date },
    {
      header: t("Invoice"),
      className: "col-m-secondary",
      render: (cn) => (
        <>
          <Link href={cn.invoice_url} className="col-nowrap">{cn.invoice_number}</Link>
          <div style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>{cn.client}</div>
        </>
      ),
    },
    { header: t("Reason"), className: "col-m-meta", render: (cn) => cn.reason },
    {
      header: t("Amount (SAR)"),
      className: "col-m-amount text-right",
      render: (cn) => (
        <>
          <div className="col-nowrap">{cn.status === "voided" ? <s>{fmt(cn.amount_sar)}</s> : fmt(cn.amount_sar)}</div>
          {cn.to_deposit_sar > 0 && cn.status !== "voided" ? (
            <div style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>{t("{n} to deposit", { n: fmt(cn.to_deposit_sar) })}</div>
          ) : null}
        </>
      ),
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (cn) => cn.status === "voided"
        ? <StatusPill small tone="gray" label={t("Voided")} />
        : <StatusPill small tone="green" label={t("Active")} />,
    },
    perms.can("payments", "approve") && {
      header: "",
      className: "col-m-actions",
      render: (cn) => cn.status === "active" ? (
        <RowActions actions={[{ icon: "trash", label: t("Void"), variant: "red", onClick: () => openForm(`/finance/credit-notes/${cn.id}/void/`) }]} />
      ) : null,
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Credit Notes")}
        sub={t("Formal reductions of what an invoice bills. Create one from the invoice it reduces.")}
      />
      <div className="hms-list-card">
        {credit_notes.length > 0 ? (
          <Table columns={columns.filter(Boolean)} rows={credit_notes} rowKey={(cn) => cn.id} />
        ) : (
          <EmptyState iconName="file-text" title={t("No credit notes yet")} sub={t("Open an invoice and choose Credit note from its menu.")} />
        )}
      </div>
    </div>
  );
}
