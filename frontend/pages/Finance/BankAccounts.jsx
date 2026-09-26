import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { listVisit } from "../../utils/listVisit.js";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function BankAccounts({ accounts = [], branch_choices = [], branch_names = {}, branch_filter = "" }) {
  const { t } = useI18n();
  const [branch, setBranch] = useState(branch_filter || "all");
  const openForm = useFormModal();
  // Accounts are managed here (add / edit / deactivate); "Show on invoice"
  // marks the ones listed as "Pay to" on the branch's invoices.
  const canManage = usePerms().can("statements", "edit");

  const onBranchChange = (v) => {
    setBranch(v);
    listVisit("/finance/bank-accounts/", v === "all" ? {} : { branch: v });
  };

  const columns = [
    {
      header: t("Account"),
      className: "col-m-primary",
      render: (a) => (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap", opacity: a.is_active ? 1 : 0.55 }}>
          <span className="col-bold col-nowrap">{a.name}</span>
          {a.account_identifier ? <span className="col-nowrap" style={{ color: "var(--muted-foreground)", fontVariantNumeric: "tabular-nums" }}>{a.account_identifier}</span> : null}
          {a.show_on_invoice && a.is_active ? <StatusPill small tone="green" label={t("On invoice")} /> : null}
          {!a.is_active ? <StatusPill small tone="gray" label={t("Inactive")} /> : null}
        </span>
      ),
    },
    {
      header: t("Type"),
      className: "col-m-badge",
      render: (a) => <StatusPill tone={a.kind === "bank" ? "blue" : "gray"} label={a.kind === "bank" ? t("Bank") : t("Cash")} />,
    },
    {
      header: t("Branch"),
      className: "col-m-meta",
      render: (a) => branch_names[a.branch] || a.branch || "—",
    },
    {
      header: t("Currency"),
      className: "col-m-meta",
      render: (a) => a.currency,
    },
    {
      header: t("Book Balance"),
      className: "col-m-amount text-right",
      render: (a) => (
        <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-end" }}>
          {/* The journal is SAR-only, so the book balance is always SAR even
              for an IDR/USD account. */}
          <span className="col-nowrap" style={a.book_balance < 0 ? { color: "var(--red)" } : undefined}>
            {a.book_balance?.toLocaleString("en-US")} SAR
          </span>
          {a.ledger_shared ? (
            <span className="col-nowrap" style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>
              {t("shared ledger {code}", { code: a.ledger_account })}
            </span>
          ) : null}
        </span>
      ),
    },
    canManage && {
      header: "",
      className: "col-m-actions",
      render: (a) =>
        a.kind === "bank" ? (
          <RowActions actions={[
            { icon: "edit", label: t("Edit"), onClick: () => openForm(`/finance/bank-accounts/${a.id}/edit/`) },
          ]} />
        ) : null,
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Bank Balances")}
        sub={t("Book balance per account, derived from the journal — not a stored figure.")}
        actions={canManage ? (
          <Button size="lg" onClick={() => openForm(`/finance/bank-accounts/new/${branch !== "all" ? `?branch=${branch}` : ""}`)}>
            + {t("Add Bank Account")}
          </Button>
        ) : null}
      />

      <div className="filter-bar">
        <Select value={branch} onValueChange={onBranchChange}>
          <SelectTrigger className="w-44" style={{ height: 40 }}>
            <SelectValue placeholder={t("All Branches")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("All Branches")}</SelectItem>
            {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="hms-list-card">
        {accounts.length > 0 ? (
          <Table
            columns={columns.filter(Boolean)}
            rows={accounts}
            rowKey={(a) => `${a.kind}-${a.id}`}
            onRowClick={(a) => router.visit(`/finance/bank-accounts/${a.kind}/${a.id}/`)}
          />
        ) : (
          <EmptyState iconName="wallet" title={t("No accounts found")} sub={t("No bank or cash accounts are set up yet.")} />
        )}
      </div>
    </div>
  );
}
