import { router } from "@inertiajs/react";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Recap({ monthly }) {
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Monthly Recap</div>
          <div className="page-sub">Remittance summary per month</div>
        </div>
      </div>

      {monthly.length ? monthly.map((m, i) => (
        <div className="month-card" key={i}>
          <div className="month-header">
            <div className="month-label">{m.label}</div>
            <div className="month-meta">
              <div className="month-badges">
                {m.count_pending > 0 && <span className="badge badge-yellow">{m.count_pending} Pending</span>}
                {m.count_received > 0 && <span className="badge badge-green">{m.count_received} Received</span>}
              </div>
              <div className="month-total">{fmt(m.total_sent)} SAR</div>
              <a href={`/remittance/export/pdf/?month=${m.period}`} target="_blank" rel="noreferrer" className="btn btn-ghost pdf-btn">PDF ↓</a>
            </div>
          </div>
          <table className="recap-table">
            <thead>
              <tr><th>No</th><th>Date</th><th>Res Count</th><th>Status</th><th className="r">Total SAR</th></tr>
            </thead>
            <tbody>
              {m.remittances.map((rem) => (
                <tr key={rem.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/remittance/${rem.id}/`)}>
                  <td className="mono" style={{ fontWeight: 600 }}>{rem.remittance_number}</td>
                  <td>{rem.date}</td>
                  <td style={{ color: "var(--text-2)" }}>{rem.lines_count} reservations</td>
                  <td>{rem.status === "received" ? <span className="badge badge-green">Received</span> : <span className="badge badge-yellow">Pending</span>}</td>
                  <td className="mono r" style={{ fontWeight: 600 }}>{fmt(rem.total_sar)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="month-foot">
            <div style={{ display: "flex", gap: 16 }}>
              {m.total_received > 0 && <span className="month-foot-label">Received: <span className="month-foot-val" style={{ color: "var(--green)" }}>{fmt(m.total_received)}</span></span>}
              {m.total_pending > 0 && <span className="month-foot-label">Pending: <span className="month-foot-val" style={{ color: "var(--yellow)" }}>{fmt(m.total_pending)}</span></span>}
            </div>
            <span className="month-foot-label">Total: <span className="month-foot-val">{fmt(m.total_sent)} SAR</span></span>
          </div>
        </div>
      )) : (
        <div className="card">
          <div className="empty"><div className="empty-title">No remittance data yet</div></div>
        </div>
      )}
    </div>
  );
}
