import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import ExportMenu from "../../components/shadcn/export-menu.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { listVisit } from "../../utils/listVisit.js";

const visit = (params) => listVisit("/services/", params);

export default function List({ invoices, total_count, q, pagination }) {
  const { t } = useI18n();
  const { query, setQuery } = useDebouncedSearch(q, (qq) => visit({ q: qq }));
  const [confirm, confirmDialog] = useConfirm();
  const openForm = useFormModal();
  const perms = usePerms();
  const del = (e, pk, num) => { e.stopPropagation(); confirm({ title: t("Delete invoice"), message: t("Delete invoice {number}?", { number: num }), onConfirm: () => router.post(`/services/${pk}/delete/`) }); };
  const qs = `?q=${encodeURIComponent(q || "")}`;

  const columns = [
    { header: t("Invoice #"), className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
    { header: t("Currency"), className: "col-m-badge", render: (inv) => <StatusPill tone="gray" label={inv.currency} small /> },
    { header: t("Customer"), className: "col-m-secondary", render: (inv) => inv.customer_name },
    {
      header: t("Issued"),
      className: "col-muted col-nowrap col-m-meta",
      render: (inv) => (
        <>
          <span className="m-hide">{inv.issued_date || "—"}</span>
          {inv.issued_date && <span className="m-only">{t("issued")} {inv.issued_date}</span>}
        </>
      ),
    },
    { header: t("Created"), className: "col-dim col-nowrap col-m-hide", render: (inv) => inv.created_at },
    {
      header: t("Total"),
      className: "col-num col-nowrap col-m-amount",
      render: (inv) => <span className="col-bold">{fmt(inv.total)} {inv.currency}</span>,
    },
    {
      header: "",
      className: "col-m-actions",
      render: (inv) => (
        <RowActions actions={[
          { icon: "pdf", label: t("Download PDF"), href: `/services/${inv.id}/pdf/`, variant: "green", external: true },
          perms.can("services", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/services/${inv.id}/edit/`) },
          perms.can("services", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, inv.id, inv.invoice_number) },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack />
      <PageHeader
        title={t("Invoice Services")}
        sub={t("{count} invoices saved", { count: total_count })}
        actions={
          <>
            <ExportMenu
              items={[
                { href: `/services/export/csv/${qs}`, label: "CSV", icon: "invoice" },
                { href: `/services/export/pdf/${qs}`, label: "PDF", icon: "cl", external: true },
              ]}
            />
            {perms.can("services", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/services/new/")} onPointerEnter={() => openForm.prefetch("/services/new/")} onFocus={() => openForm.prefetch("/services/new/")}>{t("+ Create New")}</Button>
            )}
          </>
        }
      />

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search customer or invoice number…" />
      </div>

      <ListCard
        columns={columns}
        rows={invoices}
        rowKey={(inv) => inv.id}
        onRowClick={(inv) => router.visit(`/services/${inv.id}/`)}
        empty={{
          icon: "invoice",
          title: "No invoices yet",
          sub: "Use the Create New button in the top right",
          filteredTitle: "No results",
          filteredSub: "Try adjusting your search filters",
        }}
        hasFilter={!!q}
        pagination={pagination}
        unit={t("invoices")}
        onPage={(p) => visit({ q: query, page: p })}
      />
      {confirmDialog}
    </div>
  );
}