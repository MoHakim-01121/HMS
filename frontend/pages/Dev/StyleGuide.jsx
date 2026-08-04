import { useState } from "react";
import { useTheme } from "../../layouts/useTheme.js";
import { Button } from "@/components/shadcn/ui/button.jsx";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadcn/ui/card.jsx";
import { Badge } from "@/components/shadcn/ui/badge.jsx";
import { Input } from "@/components/shadcn/ui/input.jsx";
import { useConfirm } from "@/components/shadcn/confirm-dialog.jsx";
import RowActions from "@/components/shadcn/row-actions.jsx";
import KebabMenu from "@/components/shadcn/kebab-menu.jsx";
import DraftModal from "@/components/shadcn/draft-modal.jsx";
import Toast, { showToast } from "@/components/shadcn/toast.jsx";
import SearchOverlay from "@/components/shadcn/search-overlay.jsx";
import FormPanel from "@/components/shadcn/form-panel.jsx";
import FormSection from "@/components/shadcn/form-section.jsx";
import FormField from "@/components/shadcn/form-field.jsx";
import Combobox from "@/components/shadcn/combobox.jsx";
import FormActions from "@/components/shadcn/form-actions.jsx";
import DetailCard from "@/components/shadcn/detail-card.jsx";
import DetailGrid from "@/components/shadcn/detail-grid.jsx";
import DetailAmount from "@/components/shadcn/detail-amount.jsx";
import DetailTable from "@/components/shadcn/detail-table.jsx";
import Section from "@/components/shadcn/section.jsx";
import StatusPill from "@/components/shadcn/status-pill.jsx";
import ItemRow from "@/components/shadcn/item-row.jsx";
import FooterSummary, { FooterFigure, FooterTotal } from "@/components/shadcn/footer-summary.jsx";
import Table from "@/components/shadcn/table.jsx";
import ActionSheet from "@/components/shadcn/action-sheet.jsx";

const SWATCHES = [
  { name: "background", var: "--background" },
  { name: "foreground", var: "--foreground" },
  { name: "primary", var: "--primary" },
  { name: "primary-foreground", var: "--primary-foreground" },
  { name: "secondary", var: "--secondary" },
  { name: "muted", var: "--muted" },
  { name: "muted-foreground", var: "--muted-foreground" },
  { name: "destructive", var: "--destructive" },
  { name: "border", var: "--border" },
];

function Swatch({ name, value }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 40, height: 40, borderRadius: 8, background: value, border: "1px solid var(--border)", flexShrink: 0 }} />
      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{name}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted-foreground)" }}>{value}</div>
      </div>
    </div>
  );
}

// Static reference only (tokens, type, non-portaled Button/Badge/Input) — safe
// to show light and dark side by side since none of this escapes via a
// React portal, so each panel's own `data-theme` correctly cascades to it.
function Panel({ theme }) {
  const [text, setText] = useState("");
  return (
    <div data-theme={theme} className="shadcn-root" style={{ background: "var(--background)", color: "var(--foreground)", padding: 32, borderRadius: 16, flex: 1, minWidth: 0 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)", marginBottom: 16 }}>
        {theme} mode
      </div>

      <h2 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 600, marginBottom: 24 }}>
        Aa — Fira Sans / Fira Code
      </h2>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 24 }}>
        {SWATCHES.map((s) => (
          <Swatch key={s.name} name={s.name} value={`var(${s.var})`} />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Sample card</CardTitle>
        </CardHeader>
        <CardContent style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="destructive">Destructive</Button>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="destructive">Destructive</Badge>
          </div>
          <Input placeholder="Sample input…" value={text} onChange={(e) => setText(e.target.value)} />
        </CardContent>
      </Card>
    </div>
  );
}

export default function StyleGuide() {
  const { theme, toggle } = useTheme();
  const [confirm, confirmDialog] = useConfirm();
  const [searchOpen, setSearchOpen] = useState(false);
  const [plainField, setPlainField] = useState("");
  const [comboText, setComboText] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div style={{ padding: 24, minHeight: "100vh", background: "#111" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, color: "#fff" }}>
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>
          Static swatches below always show both themes side by side. The Overlays card follows the real toggle — dialogs/dropdowns render via a portal to &lt;body&gt;, so they always follow whichever theme is actually active on &lt;html&gt;, exactly like production.
        </span>
        <button
          type="button"
          onClick={toggle}
          style={{ flexShrink: 0, marginLeft: 16, padding: "6px 12px", borderRadius: 8, border: "1px solid #444", background: "#222", color: "#fff", cursor: "pointer" }}
        >
          Toggle theme (currently {theme})
        </button>
      </div>

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Panel theme="light" />
        <Panel theme="dark" />
      </div>

      <div data-theme={theme} className="shadcn-root" style={{ background: "var(--background)", color: "var(--foreground)", padding: 32, borderRadius: 16, marginTop: 24 }}>
        <Card>
          <CardHeader>
            <CardTitle>Overlays ({theme} — follows the toggle above)</CardTitle>
          </CardHeader>
          <CardContent style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <Button
                variant="destructive"
                onClick={() => confirm({
                  title: "Delete item",
                  message: "Delete this sample item?",
                  onConfirm: () => showToast("Deleted", "success"),
                })}
              >
                Delete
              </Button>
              <Button
                variant="outline"
                onClick={() => window.dispatchEvent(new CustomEvent("open-draft", {
                  detail: { type: "invoice", pk: 0, waSend: { client_wa: "6281234567890", has_wa: true } },
                }))}
              >
                Draft
              </Button>
              <Button variant="outline" onClick={() => showToast("Contoh notifikasi", "success")}>
                Show toast
              </Button>
              <Button variant="outline" onClick={() => setSearchOpen(true)}>
                Search
              </Button>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
              <span style={{ fontSize: 13 }}>Sample row</span>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <RowActions actions={[
                  { icon: "edit", label: "Edit", onClick: () => showToast("Edit clicked") },
                  { icon: "trash", label: "Delete", variant: "red", onClick: () => confirm({ message: "Delete row?", onConfirm: () => showToast("Row deleted") }) },
                ]} />
                <KebabMenu items={[
                  { label: "View", onClick: () => showToast("View clicked") },
                  { label: "Remove", danger: true, onClick: () => showToast("Removed", "error") },
                ]} />
              </div>
            </div>
            {confirmDialog}
          </CardContent>
        </Card>

        <Card style={{ marginTop: 16 }}>
          <CardHeader>
            <CardTitle>Form</CardTitle>
          </CardHeader>
          <CardContent>
            <FormPanel>
              <FormSection label="Sample section" sub="(optional hint text)">
                <FormField
                  label="Plain field"
                  name="sg-plain"
                  value={plainField}
                  onChange={setPlainField}
                  placeholder="Type something…"
                  hint="Regular text input"
                />
                <FormField label="Combobox field" name="sg-combo" hint="Type freely or pick a suggestion">
                  <Combobox
                    name="sg-combo"
                    value={comboText}
                    onTextChange={setComboText}
                    onSelect={(o) => setComboText(o.name)}
                    options={[
                      { id: 1, name: "PT. Anugerah Wisata" },
                      { id: 2, name: "PT. Grup Command" },
                      { id: 3, name: "Ahmad Rahman" },
                    ]}
                    getSub={(o) => `id ${o.id}`}
                    placeholder="Search or type a name…"
                  />
                </FormField>
              </FormSection>
              <FormActions cancelHref="#" submitLabel="Save" processing={false} />
            </FormPanel>
          </CardContent>
        </Card>

        <Card style={{ marginTop: 16 }}>
          <CardHeader>
            <CardTitle>Detail page</CardTitle>
          </CardHeader>
          <CardContent style={{ padding: 0 }}>
            {/* Mini invoice detail: the whole hms-dv-* family in the same
                arrangement the real pages use (21st.dev Project Detail View +
                Invoice History Table). */}
            <div style={{ padding: 20 }}>
              <DetailCard
                crumbs={[{ label: "Invoices", href: "#" }]}
                kicker="INV-2026-0042"
                title="PT. Anugerah Wisata"
                sub="Hotel invoice · issued 12 Jul 2026"
                pill={{ label: "Partial", tone: "yellow" }}
                actions={<><a className="hms-dv-act" href="#">PDF</a><button type="button" className="hms-dv-act">Edit</button></>}
                menuItems={[{ label: "Delete", danger: true }]}
              >
                <DetailGrid
                  rows={[
                    { label: "Invoice no", value: "INV-2026-0042", icon: "invoice" },
                    { label: "Issued", value: "12 Jul 2026", icon: "calendar" },
                    { label: "Reservations", value: "2 reservations", icon: "hotels" },
                    { label: "Notes", value: "Deposit paid, remaining due before check-in.", icon: "file-text", span2: true },
                  ]}
                  right={<DetailAmount label="Amount Due" value="4,500" currency="SAR" tone="red" note="Due in 3 days" noteTone="yellow" />}
                />
                <Section label="Payments" icon="wallet" count={2} right="SAR">
                  <DetailTable
                    columns={[
                      { header: "Method", strong: true, render: (r) => r.method },
                      { header: "Date", render: (r) => r.date },
                      { header: "Status", render: (r) => <StatusPill small label={r.status} tone={r.status === "Cleared" ? "green" : "yellow"} /> },
                      { header: "Amount", align: "right", strong: true, render: (r) => r.amount },
                    ]}
                    rows={[
                      { method: "Bank Transfer", date: "12 Jul 2026", status: "Cleared", amount: "2,000" },
                      { method: "Cash", date: "18 Jul 2026", status: "Pending", amount: "1,000" },
                    ]}
                    footer={[{ label: "Total received", value: "3,000 SAR", total: true, tone: "green" }]}
                  />
                </Section>
                <Section label="Rooms" icon="hotels">
                  <ItemRow small name="Double" sub="3 rooms × 400/night" amount="3,600" />
                </Section>
                <FooterSummary
                  left={<FooterFigure label="Paid" value="3,000 SAR" tone="green" sub="2 payments received" />}
                  right={<FooterTotal label="Total Amount" value="7,500" currency="SAR" />}
                />
              </DetailCard>
            </div>
          </CardContent>
        </Card>

        <Card style={{ marginTop: 16 }}>
          <CardHeader>
            <CardTitle>Table & Sheet</CardTitle>
          </CardHeader>
          <CardContent style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Table
              columns={[
                { header: "Name", render: (r) => r.name },
                { header: "Status", render: (r) => <Badge variant={r.status === "Paid" ? "default" : "destructive"}>{r.status}</Badge> },
                { header: "Amount", render: (r) => r.amount },
              ]}
              rows={[
                { id: 1, name: "PT. Anugerah Wisata", status: "Paid", amount: "2,000,000" },
                { id: 2, name: "PT. Grup Command", status: "Unpaid", amount: "4,500,000" },
              ]}
              rowKey={(r) => r.id}
              onRowClick={(r) => showToast(`Clicked ${r.name}`)}
              bulkActions={[
                { label: "Export", onClick: (rows, clear) => { showToast(`Export ${rows.length} row(s)`); clear(); } },
                { label: "Delete", variant: "destructive", onClick: (rows, clear) => confirm({ message: `Delete ${rows.length} row(s)?`, onConfirm: () => { showToast("Deleted", "success"); clear(); } }) },
              ]}
            />
            <div>
              <Button variant="outline" onClick={() => setSheetOpen(true)}>Open sheet</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ActionSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title="Row actions"
        actions={[
          { icon: "edit", label: "Edit", onClick: () => showToast("Edit clicked") },
          { icon: "trash", label: "Delete", variant: "red", onClick: () => showToast("Deleted", "success") },
        ]}
      />
      <DraftModal />
      <Toast />
    </div>
  );
}

StyleGuide.layout = (page) => page;
