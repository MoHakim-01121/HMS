import { useState } from "react";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "../shadcn/toast.jsx";
import { useConfirm } from "../shadcn/confirm-dialog.jsx";
import Section from "../shadcn/section.jsx";
import { Icon } from "../icons.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtSize } from "../../utils/format.js";

// Port of _attachments.html + the upload/delete helpers from _base.html.
// Reusable for both invoice and CL: <Attachments targetType="cl" targetId={pk} initial={[...]} />
function AttIcon({ icon }) {
  if (icon === "pdf")
    return <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>;
  if (icon === "image")
    return <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>;
  return <svg viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>;
}

export default function Attachments({ targetType, targetId, initial = [], bare = false, compact = false, dashedAdd = false, onCountChange }) {
  const { t } = useI18n();
  const [items, setItemsRaw] = useState(initial);
  // onCountChange lets a parent label (e.g. the rail's count) follow uploads/deletes.
  const setItems = (fn) =>
    setItemsRaw((prev) => {
      const next = fn(prev);
      if (onCountChange && next.length !== prev.length) queueMicrotask(() => onCountChange(next.length));
      return next;
    });
  const [confirm, confirmDialog] = useConfirm();
  // Both endpoints (/attachments/upload/, /attachments/<pk>/delete/) are
  // guarded server-side by invoice.edit; read-only roles get the list only.
  const canEdit = usePerms().can("invoice", "edit");

  const upload = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append(targetType + "_id", targetId);
      try {
        const d = await fetchJson("/attachments/upload/", {
          method: "POST",
          body: fd,
        });
        if (d.error) { showToast(d.error, "error"); continue; }
        setItems((prev) => [...prev, { id: d.id, icon: d.icon, url: d.url, name: d.name, size: d.size }]);
      } catch {
        showToast(t("Upload failed"), "error");
      }
    }
    e.target.value = "";
  };

  const del = (pk) => {
    confirm({
      title: t("Delete attachment"),
      message: t("Delete this attachment?"),
      onConfirm: async () => {
        try {
          const d = await fetchJson(`/attachments/${pk}/delete/`, { method: "POST" });
          if (d.ok) setItems((prev) => prev.filter((x) => x.id !== pk));
        } catch { /* ignore */ }
      },
    });
  };

  // Compact list for the record-view rail (matches the Claude Design "Lampiran"
  // block: icon + name + size in a plain list, an "Add file" link below —
  // instead of the bordered tile grid used elsewhere).
  const compactInner = (
    <>
      {items.length ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          {items.map((att) => (
            <div className="hms-rv-filerow" key={att.id}>
              <AttIcon icon={att.icon} />
              <a href={att.url} target="_blank" rel="noreferrer" className="t" title={att.name}>{att.name}</a>
              <span className="s n">{fmtSize(att.size)}</span>
              {canEdit && (
                <button type="button" className="hms-rv-filedel" onClick={() => del(att.id)} title={t("Delete")} aria-label={t("Delete {name}", { name: att.name })}>
                  <Icon name="trash" size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="hms-dv-empty">{t("No attachments yet")}</div>
      )}
      {canEdit && (
        <label className={dashedAdd ? "hms-rv-addfile" : "hms-rv-raillink"} style={dashedAdd ? undefined : { marginTop: 8, cursor: "pointer" }}>
          {dashedAdd ? <Icon name="plus" size={13} strokeWidth={1.8} /> : null}
          {dashedAdd ? t("Upload file") : items.length ? t("Add file") : t("Add the first file")}
          <input type="file" style={{ display: "none" }} multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" onChange={upload} />
        </label>
      )}
      {confirmDialog}
    </>
  );

  // File tiles + a dashed "add" tile, following the Attachment block of the
  // detail-page reference (21st.dev Project Detail View, demo 8248) instead of
  // the old full-width dv-item rows. The dashed tile is the only upload
  // affordance — a second "Upload" button in the section header said the
  // same thing twice.
  const inner = (
    <>
      {items.length || canEdit ? (
        <div className="hms-dv-att-grid">
          {items.map((att) => (
            <div className="hms-dv-att" key={att.id}>
              <span className="hms-dv-att-ico"><AttIcon icon={att.icon} /></span>
              <div style={{ minWidth: 0 }}>
                <a href={att.url} target="_blank" rel="noreferrer" className="hms-dv-att-name" title={att.name}>{att.name}</a>
                <div className="hms-dv-att-size">{fmtSize(att.size)}</div>
              </div>
              <div className="hms-dv-att-act">
                <a className="hms-dv-att-btn" href={att.url} target="_blank" rel="noreferrer" title={t("Download")} aria-label={t("Download {name}", { name: att.name })}>
                  <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 10l5 5 5-5" /><path d="M12 15V3" /></svg>
                </a>
                {canEdit && (
                  <button type="button" className="hms-dv-att-btn" onClick={() => del(att.id)} title={t("Delete")} aria-label={t("Delete {name}", { name: att.name })}>
                    <svg viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                )}
              </div>
            </div>
          ))}
          {canEdit && (
            <label className="hms-dv-att-add">
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
              {items.length ? t("Add file") : t("Add the first file")}
              <input type="file" style={{ display: "none" }} multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" onChange={upload} />
            </label>
          )}
        </div>
      ) : (
        <div className="hms-dv-empty">{t("No attachments yet")}</div>
      )}
      {confirmDialog}
    </>
  );

  if (compact) return compactInner;
  if (bare) return inner;
  return (
    <Section label={t("Attachments")} icon="paperclip" count={items.length || null}>
      {inner}
    </Section>
  );
}
