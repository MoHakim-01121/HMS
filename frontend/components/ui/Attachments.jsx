import { useState } from "react";
import { getCsrf } from "../../utils/csrf.js";
import { fetchJson } from "../../utils/fetchJson.js";

// Port of _attachments.html + the upload/delete helpers from _base.html.
// Reusable for both invoice and CL: <Attachments targetType="cl" targetId={pk} initial={[...]} />
function fmtSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function AttIcon({ icon }) {
  if (icon === "pdf")
    return <svg width="14" height="14" fill="none" stroke="var(--red)" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>;
  if (icon === "image")
    return <svg width="14" height="14" fill="none" stroke="var(--green)" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" /></svg>;
  return <svg width="14" height="14" fill="none" stroke="var(--text-2)" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>;
}

export default function Attachments({ targetType, targetId, initial = [] }) {
  const [items, setItems] = useState(initial);

  const upload = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append(targetType + "_id", targetId);
      try {
        const d = await fetch("/attachments/upload/", {
          method: "POST",
          headers: { "X-CSRFToken": getCsrf() },
          body: fd,
        }).then((r) => r.json());
        if (d.error) { alert(d.error); continue; }
        setItems((prev) => [...prev, { id: d.id, icon: d.icon, url: d.url, name: d.name, size: d.size }]);
      } catch {
        alert("Gagal upload");
      }
    }
    e.target.value = "";
  };

  const del = async (pk) => {
    if (!confirm("Hapus lampiran ini?")) return;
    try {
      const d = await fetchJson(`/attachments/${pk}/delete/`, { method: "POST" });
      if (d.ok) setItems((prev) => prev.filter((x) => x.id !== pk));
    } catch { /* ignore */ }
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Lampiran</span>
        <label className="btn btn-ghost" style={{ height: 26, padding: "0 10px", fontSize: 12, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5 }}>
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
          Upload
          <input type="file" style={{ display: "none" }} multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" onChange={upload} />
        </label>
      </div>
      <div style={{ padding: items.length ? 0 : 16 }}>
        {items.length ? items.map((att) => (
          <div className="att-row" key={att.id}>
            <div className="att-icon"><AttIcon icon={att.icon} /></div>
            <a href={att.url} target="_blank" rel="noreferrer" className="att-name" title={att.name}>{att.name}</a>
            <span className="att-size">{fmtSize(att.size)}</span>
            <button type="button" className="btn btn-ghost att-del" style={{ width: 24, height: 24, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--text-3)" }} onClick={() => del(att.id)} title="Hapus">
              <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        )) : (
          <div style={{ color: "var(--text-3)", fontSize: 12, textAlign: "center" }}>Belum ada lampiran</div>
        )}
      </div>
    </div>
  );
}
