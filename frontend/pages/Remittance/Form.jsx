import { useContext, useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { FormModalContext } from "../../components/shadcn/form-modal.jsx";
import { REM_TABLE_CSS, REM_FORM_CSS } from "./remittanceStyles.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function Form({ reservasi = [], today, error }) {
  const { t } = useI18n();
  const modalCtx = useContext(FormModalContext);
  const [amounts, setAmounts] = useState({});
  const form = useForm({
    date: today || "",
    receipt_reference: "",
    note: "",
    proof: null,
    lines: "[]",
  });

  const hasRows = reservasi.length > 0;
  const total = useMemo(
    () => Object.values(amounts).reduce((sum, v) => sum + (parseFloat(v) || 0), 0),
    [amounts]
  );

  const setAmount = (ln, v) => setAmounts((prev) => ({ ...prev, [ln]: v }));

  const isiSemua = () => {
    const next = {};
    for (const r of reservasi) if (r.mengendap > 0) next[r.linked_number] = r.mengendap;
    setAmounts(next);
  };

  const submit = (e) => {
    e.preventDefault();
    const lines = reservasi
      .filter((r) => r.mengendap > 0)
      .map((r) => ({
        linked_number: r.linked_number,
        invoice_id: r.invoice_id,
        amount_sar: parseFloat(amounts[r.linked_number]) || 0,
      }))
      .filter((l) => l.amount_sar > 0);
    form.transform((d) => ({ ...d, lines: JSON.stringify(lines) }));
    form.post("/remittance/new/", { forceFormData: true });
  };

  return (
    <div className="page rem-form shadcn-root">
      <style>{REM_TABLE_CSS + REM_FORM_CSS + CSS}</style>

      <PageBack href="/remittance/" />
      <FormHeader kicker={t("Remittance")} title={t("Send to HQ")} sub={t("Summary of idle payments to send")} />

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Transfer Info")}>
            <div className="fg-4">
              <FormField
                label={t("Transfer Date")} name="date" type="date" required
                value={form.data.date} onChange={(v) => form.setData("date", v)}
              />
              <FormField
                label={t("Receipt Reference")} name="receipt_reference"
                value={form.data.receipt_reference} onChange={(v) => form.setData("receipt_reference", v)}
                placeholder={t("Receipt code from HQ")}
              />
              <FormField
                label={t("Note")} name="note"
                value={form.data.note} onChange={(v) => form.setData("note", v)}
                placeholder={t("Transfer BCA 01/06")}
              />
              <FormField
                name="proof"
                label={<>{t("Receipt")} <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, fontFamily: "inherit", color: "var(--muted-foreground)" }}>{t("(optional)")}</span></>}
              >
                <Input
                  id="proof" name="proof" type="file" accept="image/*,.pdf"
                  onChange={(e) => form.setData("proof", e.target.files[0] || null)}
                />
              </FormField>
            </div>
          </FormSection>

          <FormSection
            label={t("Reservations")}
            action={hasRows && <Button type="button" variant="ghost" size="sm" onClick={isiSemua}>{t("Fill All")}</Button>}
          >
            {hasRows ? (
              <>
                <div className="table-wrap" style={{ overflowX: "auto" }}>
                  <table className="rem-table">
                    <thead>
                      <tr>
                        <th>{t("Res#")}</th>
                        <th>{t("Invoice")}</th>
                        <th>{t("Client")}</th>
                        <th className="r">{t("Check-in")}</th>
                        <th className="r">{t("Check-out")}</th>
                        <th className="r">{t("Total")}</th>
                        <th className="r">{t("Paid")}</th>
                        <th className="r">{t("Already Sent")}</th>
                        <th className="r">{t("Idle")}</th>
                        <th className="r">{t("Send Now")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reservasi.map((res) => {
                        const lunas = res.mengendap <= 0 && res.sudah_dikirim >= res.total_sar;
                        return (
                          <tr key={res.linked_number} className={res.mengendap > 0 ? "row-pending" : lunas ? "row-lunas" : ""}>
                            <td className="td-res">{res.linked_number}</td>
                            <td>
                              <a href={`/invoice/${res.invoice_id}/`} target="_blank" rel="noreferrer" className="td-link">{res.invoice_number}</a>
                            </td>
                            <td className="td-muted">{res.customer_name}</td>
                            <td className="td-date" style={{ textAlign: "right" }}>{res.check_in || "-"}</td>
                            <td className="td-date" style={{ textAlign: "right" }}>{res.check_out || "-"}</td>
                            <td className="td-mono">{fmt(res.total_sar)}</td>
                            <td className="td-mono">{fmt(res.terbayar_total)}</td>
                            <td className="td-mono">{fmt(res.sudah_dikirim)}</td>
                            <td className="td-pending">{res.mengendap > 0 ? fmt(res.mengendap) : "-"}</td>
                            <td>
                              {res.mengendap > 0 ? (
                                <input type="number" className="rem-input" min="0" max={res.mengendap} step="1" placeholder="0"
                                  value={amounts[res.linked_number] ?? ""}
                                  onChange={(e) => setAmount(res.linked_number, e.target.value)} />
                              ) : lunas ? (
                                <span className="badge-lunas">{t("Paid")}</span>
                              ) : (
                                <span style={{ float: "right", color: "var(--muted-foreground)", fontSize: 12 }}>-</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="rem-total-bar">
                  <span className="rem-total-label">{t("Total sent now")}</span>
                  <span className="rem-total-val">{fmt(total)} SAR</span>
                </div>
              </>
            ) : (
              <div className="empty" style={{ padding: 40 }}>
                <div className="empty-title">{t("No reservations")}</div>
                <div className="empty-sub">{t("No active reservations yet")}</div>
              </div>
            )}
          </FormSection>

          <FormActions
            cancelHref="/remittance/"
            submitLabel={hasRows ? (form.processing ? t("Saving…") : t("Save Remittance")) : undefined}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}

// Form-specific row + cell styles; shared table/input/total styles come from REM_TABLE_CSS.
const CSS = `
.rem-table tbody tr.row-pending { background:color-mix(in srgb, var(--yellow) 5%, transparent); }
.rem-table tbody tr.row-lunas td { opacity:.5; }

.td-res  { font-family:var(--font-mono); font-weight:700; font-size:12px; color:var(--foreground); white-space:nowrap; }
.td-link { color:var(--foreground); text-decoration:none; font-size:12px; white-space:nowrap; }
.td-link:hover { text-decoration:underline; }
.td-muted { font-size:12px; color:var(--muted-foreground); }
.td-date  { font-size:12px; color:var(--muted-foreground); white-space:nowrap; }
.td-mono  { font-family:var(--font-mono); font-size:12px; color:var(--muted-foreground); text-align:right; white-space:nowrap; }
.td-pending { font-family:var(--font-mono); font-size:12px; font-weight:700; color:var(--yellow); text-align:right; white-space:nowrap; }

.badge-lunas {
  font-size:11px; font-weight:600; color:var(--green);
  background:color-mix(in srgb, var(--green) 12%, transparent);
  border-radius:calc(var(--radius) - 4px); padding:3px 8px;
  float:right;
}
`;
