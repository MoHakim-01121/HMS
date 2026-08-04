import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

function visit(params) {
  router.get("/services/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ invoices, total_count, q, pagination }) {
  const [query, setQuery] = useState(q || "");
  const [exportOpen, setExportOpen] = useState(false);
  const debounce = useRef(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const [confirm, confirmDialog] = useConfirm();
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const del = (e, pk, num) => { e.stopPropagation(); confirm({ title: t("Delete invoice"), message: t("Delete invoice {number}?", { number: num }), onConfirm: () => router.post(`/services/${pk}/delete/`) }); };
  const qs = `?q=${encodeURIComponent(q || "")}`;

  return (
    <div className="page shadcn-root">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Invoice Services")}</div>
          <div className="page-sub">{t("{count} invoices saved", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>{t("Export")} ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/services/export/csv/${qs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/services/export/pdf/${qs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
              </div>
            )}
          </div>
          {perms.can("services", "create") && (
            <button type="button" onClick={() => openForm("/services/new/")} onPointerEnter={() => openForm.prefetch("/services/new/")} onFocus={() => openForm.prefetch("/services/new/")} className="btn btn-primary">{t("+ Create New")}</button>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search customer or invoice number…")} onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
      </div>

      <div className="card">
        {invoices.length ? (
          <>
            <Table
              columns={[
                { header: t("Invoice #"), className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
                { header: t("Currency"), className: "col-m-badge", render: (inv) => <span className="badge badge-gray">{inv.currency}</span> },
                { header: t("Customer"), className: "col-m-secondary", render: (inv) => inv.customer_name },
                {
                  header: t("Issued"),
                  className: "col-muted col-nowrap col-m-meta",
                  render: (inv) => (
                    <>
                      <span className="m-hide">{inv.issued_date || "—"}</span>
                      {inv.issued_date && <span className="m-only">{t("issued")} {inv.issued_date}</span>}
                      <span className="m-only" style={{ color: "var(--text-3)" }}>{inv.created_at}</span>
                    </>
                  ),
                },
                { header: t("Created"), className: "col-dim col-nowrap col-m-hide", render: (inv) => inv.created_at },
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
              ]}
              rows={invoices}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => router.visit(`/services/${inv.id}/`)}
            />

            <Pagination pagination={pagination} unit={t("invoices")} onPage={(p) => visit({ q: query, page: p })} />
          </>
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {q ? (
              <><div className="empty-title">{t("No results")}</div><div className="empty-sub">{t("Try adjusting your search filters")}</div></>
            ) : (
              <><div className="empty-title">{t("No invoices yet")}</div><div className="empty-sub">{t("Use the Create New button in the top right")}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
