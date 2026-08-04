import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { REM_TABLE_CSS, REM_FORM_CSS } from "./remittanceStyles.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function Edit({ rem, lines = [], reservasi = [] }) {
  const { t } = useI18n();
  const [amounts, setAmounts] = useState(
    Object.fromEntries(lines.map((l) => [l.line_id, String(Math.round(l.amount_sar || 0))]))
  );
  const [removedIds, setRemovedIds] = useState([]);
  const [added, setAdded] = useState({});
  const [removeProof, setRemoveProof] = useState(false);
  const form = useForm({
    date: rem.date || "",
    receipt_reference: rem.receipt_reference || "",
    status: rem.status || "pending",
    note: rem.note || "",
    proof: null,
    remove_proof: "",
    lines: "[]",
  });

  const keptLines = useMemo(() => lines.filter((l) => !removedIds.includes(l.line_id)), [lines, removedIds]);
  const total = useMemo(() => {
    const kept = keptLines.reduce((sum, l) => sum + (parseFloat(amounts[l.line_id]) || 0), 0);
    const extra = Object.values(added).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);
    return kept + extra;
  }, [keptLines, amounts, added]);

  const setAmount = (id, v) => setAmounts((prev) => ({ ...prev, [id]: v }));
  const setAdd = (ln, v) => setAdded((prev) => ({ ...prev, [ln]: v }));
  const removeLine = (id) => setRemovedIds((prev) => [...prev, id]);
  const undoRemove = (id) => setRemovedIds((prev) => prev.filter((x) => x !== id));

  const submit = (e) => {
    e.preventDefault();
    const payload = [
      ...keptLines.map((l) => ({ line_id: l.line_id, amount_sar: parseFloat(amounts[l.line_id]) || 0 })),
      ...reservasi
        .map((r) => ({
          linked_number: r.linked_number,
          invoice_id: r.invoice_id,
          amount_sar: parseFloat(added[r.linked_number]) || 0,
        }))
        .filter((l) => l.amount_sar > 0),
    ];
    form.transform((d) => ({
      ...d,
      remove_proof: removeProof ? "1" : "",
      lines: JSON.stringify(payload),
    }));
    form.post(`/remittance/${rem.id}/edit/`, { forceFormData: true });
  };

  return (
    <div className="page rem-form shadcn-root">
      <style>{REM_TABLE_CSS + REM_FORM_CSS}</style>
      <PageBack href={`/remittance/${rem.id}/`} />
      <FormHeader kicker={t("Remittance")} title={t("Edit {number}", { number: rem.remittance_number })} />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          {rem.status === "received" && (
            <div className="rem-received-note">
              {t("This transfer has been marked")}{" "}<strong>{t("Received")}</strong>{" "}{t("by HQ. Changes here will alter already-confirmed records.")}
            </div>
          )}

          <FormSection label={t("Transfer Info")}>
            <div className="fg-4" style={{ marginBottom: 12 }}>
              <FormField
                label={t("Transfer Date")} name="date" type="date" required
                value={form.data.date} onChange={(v) => form.setData("date", v)}
              />
              <FormField
                label={t("Receipt Reference")} name="receipt_reference"
                value={form.data.receipt_reference} onChange={(v) => form.setData("receipt_reference", v)}
                placeholder={t("Receipt code from HQ")}
              />
              <FormField label={t("Status")} name="status">
                <Select value={form.data.status} onValueChange={(v) => form.setData("status", v)}>
                  <SelectTrigger id="status" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">{t("Pending")}</SelectItem>
                    <SelectItem value="received">{t("Received")}</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
              <FormField
                label={t("Note")} name="note"
                value={form.data.note} onChange={(v) => form.setData("note", v)}
                placeholder={t("e.g. BCA Transfer 01/06")}
              />
            </div>
            <FormField name="proof" label={t("Receipt")}>
              <Input
                id="proof" name="proof" type="file" accept="image/*,.pdf"
                onChange={(e) => form.setData("proof", e.target.files[0] || null)}
              />
            </FormField>
            {rem.proof_url && !removeProof && (
              <div style={{ marginTop: 6, display: "flex", gap: 10, fontSize: 12 }}>
                <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ color: "var(--foreground)", textDecoration: "underline" }}>{t("View receipt")} ↗</a>
                <button type="button" onClick={() => setRemoveProof(true)} style={{ background: "none", border: "none", fontSize: 12, color: "var(--destructive)", cursor: "pointer", padding: 0 }}>{t("Remove")}</button>
              </div>
            )}
            {removeProof && (
              <div style={{ marginTop: 6, fontSize: 12, color: "var(--destructive)" }}>
                {t("Receipt will be removed on save.")} <button type="button" onClick={() => setRemoveProof(false)} style={{ background: "none", border: "none", fontSize: 12, color: "var(--foreground)", textDecoration: "underline", cursor: "pointer", padding: 0 }}>{t("Undo")}</button>
              </div>
            )}
          </FormSection>

          <FormSection label={t("Reservations")}>
            {lines.length > 0 ? (
              <>
                <div className="table-wrap" style={{ overflowX: "auto" }}>
                  <table className="rem-table">
                    <thead>
                      <tr>
                        <th>{t("Res#")}</th>
                        <th>{t("Invoice")}</th>
                        <th>{t("Client")}</th>
                        <th className="r">{t("Amount (SAR)")}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((line) => {
                        const removed = removedIds.includes(line.line_id);
                        return (
                          <tr key={line.line_id} style={removed ? { opacity: 0.45 } : undefined}>
                            <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700, textDecoration: removed ? "line-through" : "none" }}>{line.linked_number}</td>
                            <td>
                              {line.invoice ? (
                                <a href={`/invoice/${line.invoice.pk}/`} target="_blank" rel="noreferrer"
                                  style={{ color: "var(--foreground)", textDecoration: "none", fontSize: 12 }}>{line.invoice.invoice_number}</a>
                              ) : "—"}
                            </td>
                            <td style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{line.invoice?.customer_name || "—"}</td>
                            <td>
                              <input type="number" className="rem-input" min="0" step="1" disabled={removed}
                                value={amounts[line.line_id] ?? ""}
                                onChange={(e) => setAmount(line.line_id, e.target.value)} />
                            </td>
                            <td style={{ textAlign: "right" }}>
                              {removed ? (
                                <button type="button" onClick={() => undoRemove(line.line_id)} className="rem-linkbtn">{t("Undo")}</button>
                              ) : (
                                <button type="button" onClick={() => removeLine(line.line_id)} className="rem-linkbtn danger" title={t("Remove from this transfer")}>{t("Remove")}</button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="empty" style={{ padding: 40 }}>
                <div className="empty-title">{t("No reservations")}</div>
              </div>
            )}
          </FormSection>

          <FormSection label={t("Add Reservation")} sub={t("Idle payments not yet included in this transfer")}>
            {reservasi.length > 0 ? (
              <div className="table-wrap" style={{ overflowX: "auto" }}>
                <table className="rem-table">
                  <thead>
                    <tr>
                      <th>{t("Res#")}</th>
                      <th>{t("Invoice")}</th>
                      <th>{t("Client")}</th>
                      <th>{t("Check-in")}</th>
                      <th className="r">{t("Idle (SAR)")}</th>
                      <th className="r">{t("Add (SAR)")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reservasi.map((r) => (
                      <tr key={r.linked_number}>
                        <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{r.linked_number}</td>
                        <td>
                          {r.invoice_id ? (
                            <a href={`/invoice/${r.invoice_id}/`} target="_blank" rel="noreferrer"
                              style={{ color: "var(--foreground)", textDecoration: "none", fontSize: 12 }}>{r.invoice_number}</a>
                          ) : "—"}
                        </td>
                        <td style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{r.customer_name || "—"}</td>
                        <td style={{ fontSize: 12 }}>{r.check_in || "—"}</td>
                        <td className="r" style={{ fontFamily: "var(--font-mono)" }}>{fmt(r.mengendap)}</td>
                        <td>
                          <input type="number" className="rem-input" min="0" step="1" max={r.mengendap}
                            placeholder="0"
                            value={added[r.linked_number] ?? ""}
                            onChange={(e) => setAdd(r.linked_number, e.target.value)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty" style={{ padding: 28 }}>
                <div className="empty-title">{t("Nothing left to add")}</div>
                <div className="empty-sub">{t("All idle payments are already covered")}</div>
              </div>
            )}
          </FormSection>

          <div className="rem-total-bar">
            <span className="rem-total-label">{t("Total transfer")}</span>
            <span className="rem-total-val">{fmt(total)} SAR</span>
          </div>

          <FormActions
            cancelHref={`/remittance/${rem.id}/`}
            submitLabel={form.processing ? t("Saving…") : t("Save")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}
