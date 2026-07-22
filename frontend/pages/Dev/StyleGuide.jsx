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
import DetailHero from "@/components/shadcn/detail-hero.jsx";
import FloatCard from "@/components/shadcn/float-card.jsx";
import Section from "@/components/shadcn/section.jsx";
import ItemRow from "@/components/shadcn/item-row.jsx";
import FooterSummary from "@/components/shadcn/footer-summary.jsx";

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
    <div data-theme={theme} style={{ background: "var(--background)", color: "var(--foreground)", padding: 32, borderRadius: 16, flex: 1, minWidth: 0 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)", marginBottom: 16 }}>
        {theme} mode
      </div>

      <h2 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 600, marginBottom: 24 }}>
        Aa — Playfair Display / IBM Plex Mono
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

      <div data-theme={theme} style={{ background: "var(--background)", color: "var(--foreground)", padding: 32, borderRadius: 16, marginTop: 24 }}>
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
            <div style={{ padding: 20 }}>
              <DetailHero
                kicker="Invoice"
                title="INV-2026-0042"
                sub="PT. Anugerah Wisata"
                pill={{ label: "Unpaid", tone: "red" }}
                menuItems={[{ label: "Edit" }, { label: "Download PDF" }]}
              />
              <FloatCard
                right={
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 11, color: "var(--muted-foreground)" }}>Outstanding</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: "var(--destructive)" }}>4,500,000</div>
                  </div>
                }
              >
                <div style={{ fontSize: 11, color: "var(--muted-foreground)" }}>Contact</div>
                <div style={{ fontWeight: 600 }}>Ahmad Rahman</div>
              </FloatCard>
              <Section label="Payments" right="Amount">
                <ItemRow name="Bank Transfer" sub="12 Jul 2026" amount="2,000,000" small />
                <ItemRow name="Cash" sub="15 Jul 2026" amount="1,000,000" small amountColor="green" />
              </Section>
              <FooterSummary
                left={<span style={{ fontSize: 13, color: "var(--muted-foreground)" }}>2 payments</span>}
                right={<div style={{ fontSize: 20, fontWeight: 700 }}>3,000,000 SAR</div>}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
      <DraftModal />
      <Toast />
    </div>
  );
}

StyleGuide.layout = (page) => page;
