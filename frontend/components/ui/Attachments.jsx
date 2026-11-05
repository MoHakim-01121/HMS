import { useState } from "react";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "../shadcn/toast.jsx";
import { useConfirm } from "../shadcn/confirm-dialog.jsx";
import { Icon } from "../icons.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtSize } from "../../utils/format.js";

// A record's files: icon + name + size per row, a dashed "Upload file" button
// below. <Attachments targetType="cl" targetId={pk} initial={[...]} />
function AttIcon({ icon }) {
  const props = { viewBox: "0 0 24 24", width: 14, height: 14, fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", className: "flex-none text-muted-foreground", "aria-hidden": true };
  if (icon === "pdf")
    return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>;
  if (icon === "image")
    return <svg {...props}><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>;
  return <svg {...props}><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>;
}

export default function Attachments({ targetType, targetId, initial = [], onCountChange }) {
  const { t } = useI18n();
  const [items, setItemsRaw] = useState(initial);
  // onCountChange lets a parent label (e.g. the tab's count) follow uploads/deletes.
  const setItems = (fn) =>
    setItemsRaw((prev) => {
      const next = fn(prev);
      if (onCountChange && next.length !== prev.length) queueMicrotask(() => onCountChange(next.length));
      return next;
    });
  const [confirm, confirmDialog] = useConfirm();
  // Both endpoints (/attachments/upload/, /attachments/<pk>/delete/) need edit
  // on the record the file belongs to (cl or invoice); read-only roles get the list only.
  const canEdit = usePerms().can(targetType === "cl" ? "cl" : "invoice", "edit");
  // The server says why it refused (wrong type, too large); show that, translated.
  const failed = (err, fallback) => showToast(err?.data?.error ? t(err.data.error) : t(fallback), "error");

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
        setItems((prev) => [...prev, { id: d.id, icon: d.icon, url: d.url, name: d.name, size: d.size }]);
      } catch (err) {
        failed(err, "Upload failed");
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
        } catch (err) {
          failed(err, "Could not delete the attachment");
        }
      },
    });
  };

  return (
    <>
      {items.length ? (
        <div className="flex flex-col gap-[7px]">
          {items.map((att) => (
            <div className="flex min-w-0 items-center gap-[9px]" key={att.id}>
              <AttIcon icon={att.icon} />
              <a href={att.url} target="_blank" rel="noreferrer" title={att.name}
                className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground no-underline hover:underline hover:underline-offset-2">
                {att.name}
              </a>
              <span className="flex-none text-[11.5px] text-muted-foreground tabular-nums">{fmtSize(att.size)}</span>
              {canEdit && (
                <button type="button" onClick={() => del(att.id)} title={t("Delete")} aria-label={t("Delete {name}", { name: att.name })}
                  className="inline-flex size-5 flex-none cursor-pointer items-center justify-center rounded-[6px] border-0 bg-transparent p-0 text-muted-foreground hover:bg-secondary hover:text-red">
                  <Icon name="trash" size={12} strokeWidth={1.6} />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="py-3 text-[13px] text-muted-foreground">{t("No attachments yet")}</div>
      )}
      {canEdit && (
        <label className="mt-2 box-border flex h-9 w-full cursor-pointer items-center justify-center gap-[7px] rounded-[10px] border border-dashed border-input bg-transparent text-[12.5px] font-semibold text-muted-foreground hover:border-foreground hover:text-foreground">
          <Icon name="plus" size={13} strokeWidth={1.8} />
          {t("Upload file")}
          <input type="file" className="hidden" multiple accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.xls,.xlsx,.csv,.txt" onChange={upload} />
        </label>
      )}
      {confirmDialog}
    </>
  );
}
