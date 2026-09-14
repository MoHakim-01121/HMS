import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { listVisit } from "../../utils/listVisit.js";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function BankAccounts({ accounts = [], branch_choices = [], branch_filter = "" }) {
  const { t } = useI18n();
  const [branch, setBranch] = useState(branch_filter || "all");

  const onBranchChange = (v) => {
    setBranch(v);
    listVisit("/finance/bank-accounts/", v === "all" ? {} : { branch: v });
  };

  const columns = [
    {
      header: t("Account"),
      className: "col-m-primary",
      render: (a) => <span className="col-bold col-nowrap">{a.name}</span>,
    },
    {
      header: t("Type"),
      className: "col-m-badge",
      render: (a) => <StatusPill tone={a.kind === "bank" ? "blue" : "gray"} label={a.kind === "bank" ? t("Bank") : t("Cash")} />,
    },
    {
      header: t("Branch"),
      className: "col-m-meta",
      render: (a) => a.branch || "—",
    },
    {
      header: t("Currency"),
      className: "col-m-meta",
      render: (a) => a.currency,
    },
    {
      header: t("Book Balance"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (a) => (
        <span className="col-nowrap" style={a.book_balance < 0 ? { color: "var(--red)" } : undefined}>
          {a.book_balance?.toLocaleString()} {a.currency}
        </span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Bank Balances")}
        sub={t("Book balance per account, derived from the journal — not a stored figure.")}
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
            columns={columns}
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
