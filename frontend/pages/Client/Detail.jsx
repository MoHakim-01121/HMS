import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const scoreColor = (s) => (s >= 70 ? "var(--green)" : s >= 40 ? "var(--yellow)" : "var(--red)");
const scoreValCls = (s) => (s >= 70 ? "green" : s >= 40 ? "" : "red");

function riskBadge(risk) {
  if (risk === "high") return ["badge badge-red", "High Risk"];
  if (risk === "medium") return ["badge badge-yellow", "Overdue"];
  if (risk === "dormant") return ["badge badge-gray", "Dormant"];
  return ["badge badge-green", "OK"];
}

const WaIcon = () => (
  <svg width="13" height="13" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" /></svg>
);

function Field({ label, children }) {
  return <div className="field"><div className="field-label">{label}</div><div className="field-value">{children}</div></div>;
}

export default function Detail({ client, invoices, cls }) {
  const c = client;
  const [rcls, rlabel] = riskBadge(c.risk_label);
  const [confirm, confirmDialog] = useConfirm();
  const [tab, setTab] = useState(invoices.length > 0 || cls.length === 0 ? "invoice" : "cl");
  const del = () => confirm({ title: "Delete client", message: `Delete client "${c.name}"?`, onConfirm: () => router.post(`/clients/${c.pk}/delete/`) });
  const hasTransactions = invoices.length > 0 || cls.length > 0;

  return (
    <div className="page">
      <PageBack href="/clients/" />

      <div className="dhero">
        <div className="dhero-main">
          <div className="dhero-kicker">Client</div>
          <div className="dhero-title txt">{c.name}</div>
          <div className="dhero-meta">
            <div>
              <div className="stat-label">Total Billed</div>
              <div className="dhero-meta-value blue mono">{fmt(c.total_billed)} <span className="stat-sub" style={{ display: "inline" }}>SAR</span></div>
            </div>
            <div>
              <div className="stat-label">Outstanding</div>
              <div className={"dhero-meta-value mono " + (c.outstanding > 0 ? "red" : "green")}>{fmt(c.outstanding)} <span className="stat-sub" style={{ display: "inline" }}>SAR</span></div>
            </div>
            <div>
              <div className="stat-label">Avg Payment</div>
              <div className="dhero-meta-value">{c.avg_days_to_pay != null ? `${c.avg_days_to_pay} days` : "—"}</div>
            </div>
            <div>
              <div className="stat-label">Client Score</div>
              <div className={"dhero-meta-value " + scoreValCls(c.score)}>{c.score}<span style={{ fontSize: 12, color: "var(--text-3)" }}>/100</span></div>
            </div>
          </div>
        </div>
        <div className="dhero-side">
          <div className="dhero-badges"><span className={rcls}>{rlabel}</span></div>
          <div className="dhero-actions">
            <a href={`/clients/${c.pk}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
            {c.wa && <a href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer" className="btn btn-success btn-sm"><WaIcon /> WhatsApp</a>}
            <button onClick={del} className="btn btn-danger btn-sm">Delete</button>
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 14 }}>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header"><span className="card-title">Contact</span></div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {c.city && <Field label="Location">{c.city}{c.province ? `, ${c.province}` : ""}</Field>}
            {c.pic && <Field label="PIC">{c.pic}</Field>}
            {c.wa && <Field label="WhatsApp"><a href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer" style={{ color: "var(--green)" }}>{c.wa}</a></Field>}
            {c.email && <Field label="Email">{c.email}</Field>}
            {!c.city && !c.pic && !c.wa && !c.email && (
              <div style={{ fontSize: 13, color: "var(--text-3)" }}>No contact details on file yet.</div>
            )}
          </div>
        </div>

        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header"><span className="card-title">Health &amp; Notes</span></div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="field">
              <div className="field-label">Score</div>
              <div className="score-gauge">
                <div className="score-gauge-track"><div className="score-gauge-fill" style={{ width: `${c.score}%`, background: scoreColor(c.score) }} /></div>
                <span className="score-gauge-value">{c.score}</span>
              </div>
            </div>
            {c.days_since_last_order != null && (
              <div className="field">
                <div className="field-label">Last Order</div>
                <div className={"field-value" + (c.days_since_last_order > 45 ? " remaining-unpaid" : "")}>{c.days_since_last_order} days ago</div>
              </div>
            )}
            {c.note && (
              <div className="field">
                <div className="field-label">Notes</div>
                <div style={{ fontSize: 13, color: "var(--text-2)", whiteSpace: "pre-wrap" }}>{c.note}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {hasTransactions ? (
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-header">
            <div className="tab-strip">
              <button type="button" className={tab === "invoice" ? "tab-active" : ""} onClick={() => setTab("invoice")}>Invoice ({invoices.length})</button>
              <button type="button" className={tab === "cl" ? "tab-active" : ""} onClick={() => setTab("cl")}>Confirmation Letter ({cls.length})</button>
            </div>
            {tab === "invoice" && invoices.length > 0 && <a href={`/invoice/?client=${c.pk}`} className="btn btn-ghost btn-sm">View all</a>}
          </div>

          {tab === "invoice" ? (
            invoices.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Number</th><th>Type</th><th>Billed</th><th>Remaining</th><th>Date</th><th></th></tr></thead>
                  <tbody>
                    {invoices.slice(0, 10).map((inv) => (
                      <tr key={inv.pk} style={{ cursor: "pointer" }} onClick={() => router.visit(`/invoice/${inv.pk}/`)}>
                        <td className="col-m-primary"><a href={`/invoice/${inv.pk}/`} className="col-bold" style={{ color: "var(--accent-2)", textDecoration: "none" }}>{inv.invoice_number}</a></td>
                        <td className="col-m-secondary"><span className={"badge " + (inv.invoice_type === "hotel" ? "badge-blue" : "badge-purple")}>{inv.invoice_type_display}</span></td>
                        <td className="mono col-m-hide">{fmt(inv.total_sar)}</td>
                        <td className={"mono col-m-amount " + (inv.remaining_sar > 0 ? "remaining-unpaid" : "remaining-paid")}>{fmt(inv.remaining_sar)} SAR</td>
                        <td className="col-muted col-m-hide">{inv.issued_date || "—"}</td>
                        <td className="col-m-actions" onClick={(e) => e.stopPropagation()}><a href={`/invoice/${inv.pk}/`} className="btn btn-ghost btn-sm">→</a></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty" style={{ padding: 32 }}>
                <div className="empty-title">No invoices yet</div>
              </div>
            )
          ) : cls.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Number</th><th>Guest</th><th>Hotel</th><th>Check-in</th><th></th></tr></thead>
                <tbody>
                  {cls.slice(0, 8).map((cl) => (
                    <tr key={cl.pk} style={{ cursor: "pointer" }} onClick={() => router.visit(`/cl/${cl.pk}/`)}>
                      <td className="col-m-primary"><a href={`/cl/${cl.pk}/`} className="col-bold" style={{ color: "var(--accent-2)", textDecoration: "none" }}>{cl.confirmation_number}</a></td>
                      <td className="col-m-secondary col-ellipsis">{cl.guest_name}</td>
                      <td className="col-ellipsis col-muted col-m-hide">{cl.hotel_name}</td>
                      <td className="col-muted col-m-hide">{cl.check_in || "—"}</td>
                      <td className="col-m-actions" onClick={(e) => e.stopPropagation()}><a href={`/cl/${cl.pk}/`} className="btn btn-ghost btn-sm">→</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty" style={{ padding: 32 }}>
              <div className="empty-title">No confirmation letters yet</div>
            </div>
          )}
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="empty" style={{ padding: 40 }}>
            <div className="empty-title">No transactions yet</div>
            <div className="empty-sub">Invoices and CLs assigned to this client will appear here</div>
          </div>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}
