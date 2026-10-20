import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Expense categories every branch picks from. Each has its own ledger
// account, so it shows as its own line in the Trial Balance. A category that
// was used is deactivated, never deleted: old expenses still point to it.
export default function ExpenseCategories({ categories = [] }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(null); // {code?, name}

  const save = () => {
    const url = editing.code
      ? `/finance/expenses/categories/${editing.code}/edit/`
      : "/finance/expenses/categories/new/";
    router.post(url, { name: editing.name }, { onSuccess: () => setEditing(null) });
  };
  const toggle = (c) => router.post(`/finance/expenses/categories/${c.code}/edit/`, { is_active: c.is_active ? "0" : "1" });

  const columns = [
    { header: t("Category"), className: "col-m-primary", render: (c) => <span className="col-bold">{c.name}</span> },
    { header: t("Ledger account"), className: "col-m-meta", render: (c) => <span className="font-mono text-xs">{c.ledger_account}</span> },
    { header: t("Used"), className: "col-m-meta text-right", render: (c) => c.used },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (c) => <StatusPill tone={c.is_active ? "green" : "gray"} label={c.is_active ? t("Active") : t("Inactive")} />,
    },
    {
      header: "",
      className: "col-m-actions",
      render: (c) => (
        <RowActions actions={[
          { icon: "edit", label: t("Rename"), onClick: () => setEditing({ code: c.code, name: c.name }) },
          { icon: "power", label: c.is_active ? t("Deactivate") : t("Activate"), onClick: () => toggle(c) },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack href="/finance/expenses/" label={t("Back")} />
      <PageHeader
        title={t("Expense Categories")}
        sub={t("Each category has its own ledger account, so it shows as its own line in the Trial Balance.")}
        actions={<Button size="lg" onClick={() => setEditing({ name: "" })}>+ {t("New category")}</Button>}
      />
      <div className="hms-list-card">
        <Table columns={columns} rows={categories} rowKey={(c) => c.code} />
      </div>

      {editing && (
        <Dialog open onOpenChange={(v) => { if (!v) setEditing(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{editing.code ? t("Rename category") : t("New category")}</DialogTitle>
            </DialogHeader>
            <FormField label={t("Name")} name="name" required autoFocus
              value={editing.name} onChange={(v) => setEditing({ ...editing, name: v })}
              hint={editing.code ? t("The ledger account is renamed with it.") : t("A ledger account is created for it.")} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditing(null)}>{t("Cancel")}</Button>
              <Button onClick={save} disabled={!editing.name.trim()}>{t("Save")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
