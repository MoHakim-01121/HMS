import { useState } from "react";
import { getCsrf } from "../../utils/csrf.js";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "../shell/Toast.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";

// Port of _attachments.html + the upload/delete helpers from _base.html.
// Reusable for both invoice and CL: <Attachments targetType="cl" targetId={pk} initial={[...]} />
function fmtSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function AttIcon({ icon }) {
  if (icon === "pdf")
    return <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>;
  if (icon === "image")
    return <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>;
  return <svg viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>;
}

export default function Attachments({ targetType, targetId, initial = [] }) {
  const [items, setItems] = useState(initial);
  const [confirm, confirmDialog] = useConfirm();

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
        if (d.error) { showToast(d.error, "error"); continue; }
        setItems((prev) => [...prev, { id: d.id, icon: d.icon, url: d.url, name: d.name, size: d.size }]);
      } catch {
        showToast("Upload failed", "error");
      }
    }
    e.target.value = "";
  };

  const del = (pk) => {
    confirm({
      title: "Delete attachment",
      message: "Delete this attachment?",
      onConfirm: async () => {
        try {
          const d = await fetchJson(`/attachments/${pk}/delete/`, { method: "POST" });
          if (d.ok) setItems((prev) => prev.filter((x) => x.id !== pk));
        } catch { /* ignore */ }
      },
    });
  };

  return (
    <div className="dv-sec">
      <div className="dv-sech">
        <span className="dv-l">Attachments</span>
        <label className="dv-sec-action" style={{ cursor: "pointer" }}>
          <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
          Upload
          <input type="file" style={{ display: "none" }} multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" onChange={upload} />
        </label>
      </div>
      {items.length ? items.map((att) => (
        <div className="dv-item" key={att.id}>
          <div className="dv-attach">
            <span className="dv-fico"><AttIcon icon={att.icon} /></span>
            <div style={{ minWidth: 0 }}>
              <a href={att.url} target="_blank" rel="noreferrer" className="dv-attach-name" title={att.name}>{att.name}</a>
              <div className="dv-item-sub" style={{ marginTop: 1 }}>{fmtSize(att.size)}</div>
            </div>
          </div>
          <div className="dv-attach-actions">
            <a className="dv-fico ghost" href={att.url} target="_blank" rel="noreferrer" title="Download">
              <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 10l5 5 5-5" /><path d="M12 15V3" /></svg>
            </a>
            <button type="button" className="dv-fico ghost" onClick={() => del(att.id)} title="Delete">
              <svg viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
      )) : (
        <div className="dv-empty">No attachments yet</div>
      )}
      {confirmDialog}
    </div>
  );
}
