import { useState } from "react";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "../shadcn/toast.jsx";
import Section from "../shadcn/section.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Photo proof grid for a visit, mirroring components/ui/Attachments.jsx's
// immediate-upload-on-select pattern but rendering image thumbnails instead
// of file-type icons, since these are always photos.
export default function VisitPhotos({ visitId, initial = [], canEdit }) {
  const { t } = useI18n();
  const [items, setItems] = useState(initial);

  const upload = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      try {
        const d = await fetchJson(`/visits/${visitId}/photos/upload/`, {
          method: "POST",
          body: fd,
        });
        if (d.error) { showToast(d.error, "error"); continue; }
        setItems((prev) => [...prev, { id: d.id, url: d.url }]);
      } catch {
        showToast(t("Upload failed"), "error");
      }
    }
    e.target.value = "";
  };

  const del = async (id) => {
    try {
      const d = await fetchJson(`/visits/${visitId}/photos/${id}/delete/`, { method: "POST" });
      if (d.ok) setItems((prev) => prev.filter((x) => x.id !== id));
    } catch { /* ignore */ }
  };

  return (
    <Section label={t("Photos")} icon="camera" count={items.length || null}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {items.map((p) => (
          <div key={p.id} style={{ position: "relative", width: 92, height: 92 }}>
            <img src={p.url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 8, border: "1px solid var(--border)" }} />
            {canEdit && (
              <button
                type="button"
                onClick={() => del(p.id)}
                title={t("Delete")}
                style={{ position: "absolute", top: 4, right: 4, width: 20, height: 20, borderRadius: "50%", border: "none", background: "rgba(0,0,0,.6)", color: "#fff", cursor: "pointer", fontSize: 11, lineHeight: "20px" }}
              >×</button>
            )}
          </div>
        ))}
        {canEdit && (
          <label style={{ width: 92, height: 92, display: "flex", alignItems: "center", justifyContent: "center", border: "1px dashed var(--border)", borderRadius: 8, cursor: "pointer", fontSize: 11, color: "var(--muted-foreground)", textAlign: "center" }}>
            {t("Add photo")}
            <input type="file" style={{ display: "none" }} multiple accept="image/jpeg,image/png,image/webp" onChange={upload} />
          </label>
        )}
      </div>
    </Section>
  );
}
