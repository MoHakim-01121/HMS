import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { Icon } from "../../components/icons.jsx";
import { listVisit } from "../../utils/listVisit.js";
import {
  Dialog, DialogCloseButton, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDMY } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const CSS = `
.exp-lines { display:flex; flex-direction:column; gap:8px; }
.exp-line-row { display:grid; grid-template-columns: 1fr 1fr 140px 32px; gap:8px; align-items:start; }
@media (max-width: 640px) { .exp-line-row { grid-template-columns: 1fr; } }
.exp-line-svc { grid-column: 1 / -1; }
.exp-line-del { display:flex; align-items:center; justify-content:center; height:36px; color:var(--muted-foreground); }
.exp-line-del:hover { color:var(--red); }
.exp-add-row { font-size:13px; font-weight:600; color:var(--primary); align-self:flex-start; padding:4px 0; }
`;

const STATUS_TONE = {
  draft: "gray",
  posted: "blue",
  partially_paid: "yellow",
  paid: "green",
  voided: "gray",
};

const CURRENCIES = ["SAR", "IDR", "USD"];
const EMPTY_LINE = { category: "", description: "", amount: "", service_line: "" };
// Category whose lines are a vendor cost for one sold Services line.
const SVC_VENDOR = "SVC-VENDOR";

export default function List({
  expenses = [], branch_choices = [], category_choices = [], status_choices = [],
  account_choices = [], stats = {}, pagination = null, branch_filter = "", status_filter = "",
  vendor_choices = [], service_line_choices = [],
}) {
  const { t } = useI18n();
  const perms = usePerms();
  const canCreate = perms.can("expenses", "create");
  const canExport = perms.can("expenses", "export");

  // Branches the user records expenses for (never head office). With only one,
  // it is filled in and no branch picker or filter is shown.
  const soleBranch = branch_choices.length === 1 ? branch_choices[0].value : "";
  const pickBranch = branch_choices.length > 1;
  const [branchFilter, setBranchFilter] = useState(branch_filter || "all");
  const [statusFilter, setStatusFilter] = useState(status_filter || "all");
  const [newOpen, setNewOpen] = useState(false);
  const [form, setForm] = useState({
    branch: soleBranch, expense_date: new Date().toISOString().split("T")[0],
    vendor: "", description: "", currency: "SAR", exchange_rate: "1", note: "",
    pay_now: false, pay_now_account: "", pay_now_reference: "",
  });
  const [lines, setLines] = useState([{ ...EMPTY_LINE }]);

  const applyFilters = (next) => {
    const q = {};
    const b = next.branch ?? branchFilter;
    const s = next.status ?? statusFilter;
    if (b !== "all") q.branch = b;
    if (s !== "all") q.status = s;
    listVisit("/finance/expenses/", q);
  };

  const updateLine = (i, key, val) => {
    setLines(lines.map((l, idx) => (idx === i ? { ...l, [key]: val } : l)));
  };
  const addLine = () => setLines([...lines, { ...EMPTY_LINE }]);
  const removeLine = (i) => setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ ...EMPTY_LINE }]);

  const total = lines.reduce((sum, l) => sum + (Number(l.amount) || 0), 0);

  const resetForm = () => {
    setForm({
      branch: soleBranch, expense_date: new Date().toISOString().split("T")[0],
      vendor: "", description: "", currency: "SAR", exchange_rate: "1", note: "",
      pay_now: false, pay_now_account: "", pay_now_reference: "",
    });
    setLines([{ ...EMPTY_LINE }]);
  };

  const submit = () => {
    const validLines = lines
      .filter((l) => l.category && Number(l.amount) > 0)
      .map((l) => ({ ...l, service_line: l.category === SVC_VENDOR ? l.service_line : "" }));
    if (!form.branch || validLines.length === 0) return;
    if (validLines.some((l) => l.category === SVC_VENDOR && !l.service_line)) return;
    router.post("/finance/expenses/record/", {
      branch: form.branch,
      expense_date: form.expense_date,
      vendor: form.vendor,
      description: form.description,
      currency: form.currency,
      exchange_rate: form.exchange_rate,
      note: form.note,
      lines: JSON.stringify(validLines),
      ...(form.pay_now && form.pay_now_account ? {
        pay_now_account: form.pay_now_account,
        pay_now_reference: form.pay_now_reference,
      } : {}),
    }, {
      onSuccess: () => { setNewOpen(false); resetForm(); },
    });
  };

  const accountsForBranch = account_choices.filter((a) => !form.branch || a.branch === form.branch);

  const columns = [
    {
      header: t("Expense #"),
      className: "col-m-primary",
      render: (e) => <span className="col-bold col-nowrap">{e.expense_number}</span>,
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (e) => <StatusPill tone={STATUS_TONE[e.status] || "gray"} label={e.status_display} />,
    },
    // One branch only: every row is that branch, so no column for it.
    pickBranch && {
      header: t("Branch"),
      className: "col-m-meta",
      render: (e) => e.branch_name || "—",
    },
    {
      header: t("Vendor"),
      className: "col-m-secondary",
      style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 },
      render: (e) => e.vendor || e.description || "—",
    },
    {
      header: t("Date"),
      className: "col-m-meta col-nowrap",
      render: (e) => fmtDMY(e.expense_date) || "—",
    },
    {
      header: t("Total"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (e) => (
        <>
          <span className="col-nowrap">{e.total_amount_sar?.toLocaleString("en-US")} SAR</span>
          {e.outstanding_sar > 0 && (
            <span style={{ display: "block", marginTop: 2, fontSize: 11, fontWeight: 600, color: "var(--yellow)", whiteSpace: "nowrap" }}>
              {e.outstanding_sar?.toLocaleString("en-US")} {t("outstanding")}
            </span>
          )}
        </>
      ),
    },
    {
      header: "",
      className: "col-m-actions",
      render: (e) => (
        <RowActions actions={[
          { icon: "arrow-right", label: t("View"), href: `/finance/expenses/${e.id}/` },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Expenses")}
        sub={t("Track branch operating costs and their payment status.")}
        actions={
          <>
            {canExport && (
              <Button asChild variant="outline" size="lg">
                <a href="/finance/expenses/export/csv/" target="_blank" rel="noreferrer">{t("Export CSV")}</a>
              </Button>
            )}
            {canCreate && (
              <Button size="lg" onClick={() => setNewOpen(true)}>+ {t("New Expense")}</Button>
            )}
          </>
        }
      />

      <div className="hms-kpi-row">
        <KpiCard label={t("Total Expenses")} value={stats.total || 0} icon="invoice" />
        <KpiCard label={t("Total Amount")} value={(stats.total_sar || 0).toLocaleString("en-US")} icon="wallet" />
        <KpiCard label={t("Outstanding")} value={(stats.outstanding_sar || 0).toLocaleString("en-US")} icon="alert" tone={(stats.outstanding_sar || 0) > 0 ? "yellow" : undefined} />
        <KpiCard label={t("Unpaid")} value={stats.unpaid_count || 0} icon="clock" />
      </div>

      <div className="filter-bar">
        {pickBranch && (
          <Select value={branchFilter} onValueChange={(v) => { setBranchFilter(v); applyFilters({ branch: v }); }}>
            <SelectTrigger className="w-44" style={{ height: 40 }}>
              <SelectValue placeholder={t("All Branches")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("All Branches")}</SelectItem>
              {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); applyFilters({ status: v }); }}>
          <SelectTrigger className="w-44" style={{ height: 40 }}>
            <SelectValue placeholder={t("All Status")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("All Status")}</SelectItem>
            {status_choices.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="hms-list-card">
        {expenses.length > 0 ? (
          <>
            <Table
              columns={columns.filter(Boolean)}
              rows={expenses}
              rowKey={(e) => e.id}
              onRowClick={(e) => router.visit(`/finance/expenses/${e.id}/`)}
            />
            <Pagination
              pagination={pagination}
              unit={t("expenses")}
              onPage={(p) => listVisit("/finance/expenses/", {
                ...(branchFilter !== "all" ? { branch: branchFilter } : {}),
                ...(statusFilter !== "all" ? { status: statusFilter } : {}),
                page: p,
              })}
            />
          </>
        ) : (
          <EmptyState iconName="invoice" title={t("No expenses found")} sub={t("No expense records match your filters.")} />
        )}
      </div>

      {newOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setNewOpen(false); }}>
          <DialogContent className="sm:max-w-3xl form-modal-content" showCloseButton={false}>
            <style>{CSS}</style>
            <div className="hms-modal-head">
              <DialogTitle className="hms-modal-title">{t("New Expense")}</DialogTitle>
              <DialogCloseButton />
            </div>

            <div className="hms-modal-body">
              <form onSubmit={(e) => { e.preventDefault(); submit(); }} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                <FormSection label={t("Expense Details")}>
                  <div className="fg-3">
                    {pickBranch && (
                      <FormField label={t("Branch")} name="branch" required>
                        <Select value={form.branch} onValueChange={(v) => setForm({ ...form, branch: v, pay_now_account: "" })}>
                          <SelectTrigger className="w-full"><SelectValue placeholder={t("Select branch...")} /></SelectTrigger>
                          <SelectContent>
                            {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </FormField>
                    )}
                    <FormField label={t("Date")} name="expense_date" type="date" required
                      value={form.expense_date} onChange={(v) => setForm({ ...form, expense_date: v })} />
                    <FormField label={t("Vendor")} name="vendor">
                      <Input id="vendor" list="exp-vendor-choices" value={form.vendor}
                        onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
                      <datalist id="exp-vendor-choices">
                        {vendor_choices.map((v) => <option key={v} value={v} />)}
                      </datalist>
                    </FormField>
                    <FormField label={t("Description")} name="description"
                      value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
                    <FormField label={t("Currency")} name="currency">
                      <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v, exchange_rate: v === "SAR" ? "1" : form.exchange_rate })}>
                        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                    {form.currency !== "SAR" && (
                      <FormField label={t("Exchange Rate")} name="exchange_rate" type="number" step="0.0001" required
                        value={form.exchange_rate} onChange={(v) => setForm({ ...form, exchange_rate: v })} />
                    )}
                  </div>
                </FormSection>

                <FormSection label={t("Lines")}>
                  <div className="exp-lines">
                    {lines.map((l, i) => (
                      <div key={i} className="exp-line-row">
                        <Select value={l.category} onValueChange={(v) => updateLine(i, "category", v)}>
                          <SelectTrigger className="w-full"><SelectValue placeholder={t("Category...")} /></SelectTrigger>
                          <SelectContent>
                            {category_choices.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                        <Input placeholder={t("Description")} value={l.description}
                          onChange={(e) => updateLine(i, "description", e.target.value)} />
                        <Input type="number" placeholder="0" value={l.amount}
                          onChange={(e) => updateLine(i, "amount", e.target.value)} />
                        <button type="button" className="exp-line-del" onClick={() => removeLine(i)} aria-label={t("Remove line")}>
                          <Icon name="trash" size={14} />
                        </button>
                        {l.category === SVC_VENDOR && (
                          <div className="exp-line-svc">
                            <Select value={l.service_line} onValueChange={(v) => updateLine(i, "service_line", v)}>
                              <SelectTrigger className="w-full"><SelectValue placeholder={t("Services line sold by this branch...")} /></SelectTrigger>
                              <SelectContent>
                                {service_line_choices
                                  .filter((s) => !form.branch || s.branch === form.branch)
                                  .map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                      </div>
                    ))}
                    <button type="button" className="exp-add-row" onClick={addLine}>{t("+ Add line")}</button>
                  </div>
                  <div style={{ textAlign: "right", marginTop: 8, fontSize: 13, fontWeight: 600 }}>
                    {t("Total")}: {total.toLocaleString("en-US")} {form.currency}
                  </div>
                </FormSection>

                <FormSection label={t("Payment")}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <Checkbox checked={form.pay_now} onCheckedChange={(v) => setForm({ ...form, pay_now: !!v })} />
                    <span style={{ fontSize: 13 }}>{t("Pay now (immediately settle in full)")}</span>
                  </label>
                  {form.pay_now && (
                    <div className="fg-3" style={{ marginTop: 12 }}>
                      <FormField label={t("Paid from")} name="pay_now_account" required>
                        <Select value={form.pay_now_account} onValueChange={(v) => setForm({ ...form, pay_now_account: v })}>
                          <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                          <SelectContent>
                            {accountsForBranch.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </FormField>
                      <FormField label={t("Reference")} name="pay_now_reference"
                        value={form.pay_now_reference} onChange={(v) => setForm({ ...form, pay_now_reference: v })} />
                    </div>
                  )}
                </FormSection>

                <FormField label={t("Note")} name="note">
                  <Textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
                </FormField>
              </form>
            </div>

            <DialogFooter className="pay-footer">
              <Button variant="outline" onClick={() => setNewOpen(false)}>{t("Cancel")}</Button>
              <Button onClick={submit} disabled={!form.branch || total <= 0}>{t("Save Expense")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
