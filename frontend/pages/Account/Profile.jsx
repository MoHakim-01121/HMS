import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { router } from "@inertiajs/react";
import { Dialog, DialogContent, DialogTitle } from "../../components/shadcn/ui/dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import "../../styles/profile.css";

// My Profile, as approved on the Record View HMS canvas (Profile E2): who you
// are with your photo, two cards side by side (personal info, access), the
// language preference, and your activity — opening on today, with search, a
// filter panel, active-filter chips, day bands and pages.

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n) => String(n).padStart(2, "0");
const MB = 1024 * 1024;
const TYPES_OK = ["image/jpeg", "image/png", "image/webp", "image/gif"];

const ACT = {
  login: ["Sign in", "pf-pill sm"],
  create: ["Create", "pf-pill sm ok"],
  edit: ["Edit", "pf-pill sm warn"],
  delete: ["Delete", "pf-pill sm bad"],
  pdf: ["Export PDF", "pf-pill sm info"],
};
const RANGES = [["any", "Any time"], ["today", "Today"], ["7d", "Last 7 days"], ["30d", "Last 30 days"], ["custom", "Custom"]];
const NONE = { acts: [], types: [], range: "any", from: "", to: "" };

const Svg = ({ d, size = 16, sw = 1.8, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d ? <path d={d} /> : children}</svg>
);
const I = {
  back: <Svg d="M15 18l-6-6 6-6" size={14} />,
  close: <Svg d="M6 6l12 12M18 6L6 18" />,
  cam: <Svg size={15} sw={2}><path d="M4 8.5A2.5 2.5 0 016.5 6h1.6l1.4-2h5l1.4 2h1.6A2.5 2.5 0 0120 8.5v9a2.5 2.5 0 01-2.5 2.5h-11A2.5 2.5 0 014 17.5z" /><circle cx="12" cy="13" r="3.5" /></Svg>,
  go: <Svg d="M9 6l6 6-6 6" />,
  lock: <Svg size={15}><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></Svg>,
  ok: <Svg d="M5 12l5 5 9-10" size={13} sw={2.4} />,
  search: <Svg size={15}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></Svg>,
  filter: <Svg d="M4 5h16l-6 7.5V19l-4 1.5v-8z" size={15} />,
  x: <Svg d="M6 6l12 12M18 6L6 18" size={12} sw={2.2} />,
  up: <Svg size={20} sw={1.9}><path d="M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M4 14.5V18a2 2 0 002 2h12a2 2 0 002-2v-3.5" /></Svg>,
  err: <Svg size={15} sw={2}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.01" /></Svg>,
  minus: <Svg d="M5 12h14" size={14} sw={2} />,
  plus: <Svg d="M12 5v14M5 12h14" size={14} sw={2} />,
  prev: <Svg d="M15 18l-6-6 6-6" size={15} sw={2} />,
  next: <Svg d="M9 6l6 6-6 6" size={15} sw={2} />,
  empty: <Svg size={20}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></Svg>,
};

function initials(name) {
  const parts = (name || "?").trim().split(/\s+/);
  return (parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : parts[0].slice(0, 2)).toUpperCase();
}
function dayLabel(d) { return `${pad(d.getDate())} ${MON[d.getMonth()]} ${d.getFullYear()}`; }
function lastSignIn(iso, t) {
  if (!iso) return t("Never");
  const d = new Date(iso), now = new Date();
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.toDateString() === now.toDateString()) return t("Today, {time}", { time: hm });
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return t("Yesterday, {time}", { time: hm });
  return dayLabel(d);
}
const short = (iso) => { const p = iso.split("-"); return `${+p[2]} ${MON[+p[1] - 1]}`; };

export default function Profile({ profile, account, activity, errors: serverErrors = {} }) {
  const { t, locale } = useI18n();
  const isAdmin = account.is_superuser;
  const [toast, setToast] = useState("");
  const [ok, setOk] = useState(null);
  const [edit, setEdit] = useState(null);
  const [photo, setPhoto] = useState(null); // "pick" | "view"
  const [lang, setLang] = useState(profile.language || locale);
  const [langOk, setLangOk] = useState(false);

  useEffect(() => { if (!toast) return undefined; const id = setTimeout(() => setToast(""), 3600); return () => clearTimeout(id); }, [toast]);

  const fields = [
    { key: "full_name", label: t("Name"), value: account.full_name, editable: true },
    { key: "email", label: t("Email"), value: account.email, editable: true },
    { key: "username", label: t("Username"), value: account.username, editable: isAdmin,
      sub: isAdmin ? t("Used to sign in") : t("Used to sign in. Only an administrator can change it.") },
  ];

  const pickLang = async (v) => {
    if (v === lang) return;
    setLang(v);
    try {
      await axios.post("/account/language/", new URLSearchParams({ language: v }));
      setLangOk(true);
      router.reload({ preserveScroll: true });
    } catch { setLang(lang); }
  };

  return (
    <div className="page shadcn-root">
      <div className="pf">
        <div><a href="/" className="pf-back" onClick={(e) => { if (window.history.length > 1) { e.preventDefault(); window.history.back(); } }}>{I.back}{t("Back")}</a></div>
        {toast && <div className="pf-toast" role="status">{I.ok}{toast}</div>}

        <section className="pf-card pf-idc">
          <button type="button" className="pf-av" aria-label={profile.avatar_url ? t("View photo") : t("Add a photo")}
            onClick={() => setPhoto(profile.avatar_url ? "view" : "pick")}>
            {profile.avatar_url ? <span className="img"><img src={profile.avatar_url} alt="" /></span> : initials(account.full_name)}
            <span className="cam">{I.cam}</span>
          </button>
          <div style={{ minWidth: 0 }}>
            <h1 className="pf-name">{account.full_name}</h1>
            <div className="pf-mail">{account.email || t("No email")}</div>
            <div className="pf-pills">
              <span className="pf-pill info">{account.role_badge}</span>
              <span className="pf-pill">{t(account.branch)}</span>
              <span className={"pf-pill" + (account.is_active ? " ok" : "")}>{account.is_active ? t("Active") : t("Inactive")}</span>
              {isAdmin && <span className="pf-pill">{t("Superuser")}</span>}
            </div>
          </div>
          <dl className="pf-facts">
            <div><dt>{t("Username")}</dt><dd>{account.username}</dd></div>
            <div><dt>{t("Last sign in")}</dt><dd>{lastSignIn(account.last_login, t)}</dd></div>
            <div><dt>{t("Member since")}</dt><dd>{account.date_joined ? dayLabel(new Date(account.date_joined)) : "—"}</dd></div>
          </dl>
        </section>

        <div className="pf-grid2">
          <section className="pf-card pf-sec">
            <div className="pf-ch"><div><h2>{t("Personal info")}</h2><p>{t("How other people in HMS see you.")}</p></div></div>
            {fields.map((f, i) => f.editable ? (
              <button type="button" key={f.key} className={"pf-rb" + (i === 0 ? " first" : "")} aria-label={t("Edit {field}", { field: f.label.toLowerCase() })}
                onClick={() => { setOk(null); setEdit(f.key); }}>
                <span className="pf-k">{f.label}</span>
                <span className="pf-v"><span className={f.value ? "" : "mute"}>{f.value || t("Not set")}</span>{f.sub && <small>{f.sub}</small>}</span>
                {ok === f.key && <span className="pf-okm" role="status">{I.ok}{t("Saved")}</span>}
                <span className="pf-go">{I.go}</span>
              </button>
            ) : (
              <div key={f.key} className={"pf-ri" + (i === 0 ? " first" : "")}>
                <span className="pf-k">{f.label}</span>
                <span className="pf-v"><span>{f.value}</span><small>{f.sub}</small></span>
                <span className="pf-go">{I.lock}</span>
              </div>
            ))}
          </section>

          <section className="pf-card pf-sec">
            <div className="pf-ch">
              <div><h2>{t("Access and sign-in")}</h2><p>{t("What you can do in HMS and how you sign in.")}</p></div>
              <span className="pf-aside">{t("Managed by an administrator")}</span>
            </div>
            <div className="pf-ri first"><span className="pf-k">{t("Role")}</span><span className="pf-v"><span>{account.role}</span>{account.role_meta && <small>{t(account.role_meta)}</small>}</span></div>
            <div className="pf-ri"><span className="pf-k">{t("Branch")}</span><span className="pf-v"><span>{t(account.branch)}</span><small>{t(account.branch_meta)}</small></span></div>
            <div className="pf-ri"><span className="pf-k">{t("Password")}</span><span className="pf-v"><span className="mute" style={{ letterSpacing: 3 }}>••••••••</span><small>{t("Forgot it? An administrator can reset it for you.")}</small></span></div>
          </section>
        </div>

        <section className="pf-card">
          <div className="pf-ch flat" style={{ alignItems: "center", flexWrap: "wrap" }}>
            <div><h2>{t("Preferences")}</h2><p>{t("Only changes HMS for you.")}</p></div>
            <div className="pf-pref">
              <span className="lbl">{t("Language")}</span>
              {langOk && <span className="pf-okm" role="status">{I.ok}{t("Saved")}</span>}
              <span className="pf-seg" role="group" aria-label={t("Language")}>
                {[["en", "English"], ["id", "Indonesian"]].map(([v, label]) => (
                  <button type="button" key={v} className={lang === v ? "on" : ""} aria-pressed={lang === v} onClick={() => pickLang(v)}>{t(label)}</button>
                ))}
              </span>
            </div>
          </div>
        </section>

        <ActivityCard activity={activity} />
      </div>

      <EditSheet field={edit} account={account} serverErrors={serverErrors}
        onClose={() => setEdit(null)} onSaved={(k) => { setEdit(null); setOk(k); }} />
      <PhotoSheet open={photo === "pick"} hasPhoto={!!profile.avatar_url}
        onClose={() => setPhoto(null)} onDone={(msg) => { setPhoto(null); setToast(msg); }} />
      <ViewSheet open={photo === "view"} url={profile.avatar_url} name={account.full_name}
        onClose={() => setPhoto(null)} onChange={() => setPhoto("pick")}
        onRemoved={() => { setPhoto(null); setToast(t("Photo removed.")); }} />
    </div>
  );
}

// ── Edit name / email / username ─────────────────────────────────────────
function EditSheet({ field, account, serverErrors, onClose, onSaved }) {
  const { t } = useI18n();
  const DEFS = {
    full_name: { label: t("Name"), type: "text", title: t("Edit name"), note: t("Shown on records you create and in the activity log."), hint: t("Max 150 characters"),
      test: (v) => (!v ? t("Display name is required.") : v.length > 150 ? t("Display name must be 150 characters or fewer.") : "") },
    email: { label: t("Email"), type: "email", title: t("Edit email"), note: t("Your primary email address."), hint: t("Leave empty if you have none."),
      test: (v) => (v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? t("Enter a valid email address.") : "") },
    username: { label: t("Username"), type: "text", title: t("Edit username"), note: t("You sign in with this. Use the new one the next time you sign in."), hint: t("Letters, digits and @ . + - _ only."),
      test: (v) => (!v ? t("Username is required.") : !/^[\w.@+-]+$/.test(v) ? t("Use letters, digits and @ . + - _ only.") : "") },
  };
  const cur = field ? DEFS[field] : null;
  const [draft, setDraft] = useState("");
  const [tried, setTried] = useState(false);
  const [server, setServer] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (field) { setDraft(field === "full_name" ? account.full_name : account[field] || ""); setTried(false); setServer(""); }
  }, [field, account]);
  useEffect(() => { if (field && serverErrors[field]) setServer(serverErrors[field]); }, [serverErrors, field]);

  const err = cur && tried ? cur.test(draft.trim()) : "";
  const shown = err || server;
  const save = () => {
    if (!cur || busy) return;
    const v = draft.trim();
    if (cur.test(v)) { setTried(true); return; }
    setBusy(true);
    router.post("/account/profile/update/", { [field]: v }, {
      preserveScroll: true,
      onSuccess: (page) => { if (!page.props.errors?.[field]) onSaved(field); },
      onError: (errs) => setServer(errs[field] || Object.values(errs)[0] || ""),
      onFinish: () => setBusy(false),
    });
  };

  return (
    <Dialog open={!!cur} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="pf-sheet" showCloseButton={false}>
        {cur && (
          <>
            <div className="pf-sh"><DialogTitle asChild><h2>{cur.title}</h2></DialogTitle><button type="button" className="pf-iconbtn" aria-label={t("Close")} onClick={onClose}>{I.close}</button></div>
            <div className="pf-sb">
              <p>{cur.note}</p>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="pf-ol">{cur.label}</span>
                <span className={"pf-fld" + (shown ? " bad" : "")}>
                  <input aria-label={cur.label} type={cur.type} autoComplete="off" value={draft} autoFocus
                    onChange={(e) => { setDraft(e.target.value); setServer(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } }} />
                </span>
              </label>
              <span className={"pf-hint" + (shown ? " err" : "")}>{shown ? t(shown) : cur.hint}</span>
            </div>
            <div className="pf-sf"><button type="button" className="pf-btn o" onClick={onClose}>{t("Cancel")}</button><button type="button" className="pf-btn p" onClick={save} disabled={busy}>{t("Save")}</button></div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Photo: choose, crop, upload ──────────────────────────────────────────
// Removing the photo cannot be undone (it has to be uploaded again), so it asks.
function useRemovePhoto(onRemoved) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const ask = () => confirm({
    title: t("Remove photo"),
    message: t("Remove your profile photo?"),
    detail: t("Your initials show instead until you upload a new one."),
    confirmLabel: "Remove",
    danger: true,
    onConfirm: () => router.post("/account/avatar/delete/", {}, { preserveScroll: true, onSuccess: onRemoved }),
  });
  return [ask, confirmDialog];
}

function PhotoSheet({ open, hasPhoto, onClose, onDone }) {
  const { t } = useI18n();
  const [mode, setMode] = useState("pick"); // pick | crop | busy
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const [file, setFile] = useState(null);
  const [img, setImg] = useState(null); // { url, w, h }
  const [pos, setPos] = useState({ x: 0, y: 0, z: 1 });
  const [box, setBox] = useState(320);
  const cropRef = useRef(null);
  const drag = useRef(null);

  useEffect(() => {
    if (open) { setMode("pick"); setErr(""); setOver(false); setFile(null); setImg(null); setPos({ x: 0, y: 0, z: 1 }); }
  }, [open]);
  useEffect(() => () => { if (img) URL.revokeObjectURL(img.url); }, [img]);
  useEffect(() => { if (mode !== "pick" && cropRef.current) setBox(cropRef.current.clientWidth || 320); }, [mode, img]);

  const D = box - 24; // the round mask, inset 12px
  const base = img ? box / Math.min(img.w, img.h) : 1;
  const dispW = img ? img.w * base * pos.z : 0, dispH = img ? img.h * base * pos.z : 0;
  const clamp = (v, size) => Math.round(Math.max(-Math.max(0, (size - D) / 2), Math.min(Math.max(0, (size - D) / 2), v)));
  const setXY = (x, y, z = pos.z) => {
    const w = img.w * base * z, h = img.h * base * z;
    setPos({ x: clamp(x, w), y: clamp(y, h), z });
  };

  const check = (f) => {
    if (!f) return;
    if (!TYPES_OK.includes(f.type)) { setErr(t("This file type is not supported. Use JPG, PNG, WEBP or GIF.")); return; }
    if (f.size > 10 * MB) { setErr(t("This file is {mb} MB. Choose one up to 10 MB.", { mb: (f.size / MB).toFixed(1) })); return; }
    const url = URL.createObjectURL(f);
    const el = new Image();
    el.onload = () => { setImg({ url, w: el.naturalWidth, h: el.naturalHeight }); setFile(f); setPos({ x: 0, y: 0, z: 1 }); setErr(""); setMode("crop"); };
    el.onerror = () => { URL.revokeObjectURL(url); setErr(t("This file is not a valid image.")); };
    el.src = url;
  };

  // The visible image at `size` px for the mask's diameter (crop box, previews).
  const view = (size) => {
    const f = size / D;
    const w = dispW * f, h = dispH * f;
    return { width: w, height: h, left: size / 2 + pos.x * f - w / 2, top: size / 2 + pos.y * f - h / 2 };
  };
  const cropStyle = img ? { width: dispW, height: dispH, left: box / 2 + pos.x - dispW / 2, top: box / 2 + pos.y - dispH / 2 } : {};

  const save = () => {
    if (mode !== "crop" || !img) return;
    setMode("busy");
    const el = new Image();
    el.onload = () => {
      // The mask's square in the crop box, mapped back onto the original.
      const k = base * pos.z;
      const left = box / 2 + pos.x - dispW / 2, top = box / 2 + pos.y - dispH / 2;
      const sx = (12 - left) / k, sy = (12 - top) / k, s = D / k;
      const out = document.createElement("canvas");
      out.width = 512; out.height = 512;
      out.getContext("2d").drawImage(el, sx, sy, s, s, 0, 0, 512, 512);
      out.toBlob((blob) => {
        const name = (file?.name || "photo").replace(/\.[^.]+$/, "") + ".jpg";
        router.post("/account/avatar/upload/", { avatar: new File([blob], name, { type: "image/jpeg" }) }, {
          forceFormData: true, preserveScroll: true,
          onSuccess: () => onDone(t("Photo updated.")),
          onError: () => { setMode("crop"); setErr(t("The photo could not be saved. Try again.")); },
        });
      }, "image/jpeg", 0.9);
    };
    el.src = img.url;
  };
  const [remove, removeDialog] = useRemovePhoto(() => onDone(t("Photo removed.")));

  const busy = mode === "busy";
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <DialogContent className="pf-sheet wide" showCloseButton={false} aria-busy={busy}>
        <div className="pf-sh">
          <DialogTitle asChild><h2>{hasPhoto ? t("Change photo") : t("Add a photo")}</h2></DialogTitle>
          <button type="button" className="pf-iconbtn" aria-label={t("Close")} disabled={busy} style={busy ? { opacity: .4, cursor: "default" } : null} onClick={() => !busy && onClose()}>{I.close}</button>
        </div>
        <div className="pf-sb">
          {mode === "pick" ? (
            <>
              <label className={"pf-dz" + (over ? " over" : "") + (err ? " bad" : "")}
                onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                onDrop={(e) => { e.preventDefault(); setOver(false); check(e.dataTransfer?.files?.[0]); }}>
                <input className="pf-sr" type="file" accept={TYPES_OK.join(",")} onChange={(e) => check(e.target.files?.[0])} />
                <span className="pf-dzi">{I.up}</span>
                <span className="pf-dzt">{t("Drag a photo here or")} <u>{t("choose a file")}</u></span>
                <span className="pf-dzh">{t("JPG, PNG, WEBP or GIF, up to 10 MB")}</span>
              </label>
              {err && <span className="pf-perr" role="alert">{I.err}{err}</span>}
            </>
          ) : (
            <>
              <div className="pf-fname">{file?.name}, {(file?.size / MB).toFixed(1)} MB</div>
              <div ref={cropRef} className={"pf-crop" + (busy ? " busy" : "")} tabIndex={busy ? -1 : 0}
                aria-label={busy ? t("Crop area, locked while uploading") : t("Crop area. Drag the photo or use the arrow keys to move it.")}
                onPointerDown={(e) => { if (busy) return; e.currentTarget.setPointerCapture(e.pointerId); drag.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y }; }}
                onPointerMove={(e) => { const g = drag.current; if (g) setXY(g.ox + e.clientX - g.sx, g.oy + e.clientY - g.sy); }}
                onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
                onKeyDown={(e) => {
                  const m = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -8], ArrowDown: [0, 8] }[e.key];
                  if (!m || busy) return;
                  e.preventDefault(); setXY(pos.x + m[0], pos.y + m[1]);
                }}>
                {img && <img src={img.url} alt="" style={cropStyle} />}
                <span className="pf-ring" aria-hidden="true" />
              </div>
              <div className="pf-zoom">
                {I.minus}
                <input type="range" min="1" max="3" step="0.01" aria-label={t("Zoom")} value={pos.z} disabled={busy}
                  onChange={(e) => setXY(pos.x, pos.y, parseFloat(e.target.value))} />
                {I.plus}
              </div>
              {err && <span className="pf-perr" role="alert">{I.err}{err}</span>}
              {!busy && img && (
                <div className="pf-pv">
                  <span className="pf-pvl">{t("Preview")}</span>
                  <span className="pf-pva lg"><img src={img.url} alt="" style={view(72)} /></span>
                  <span className="pf-pva sm"><img src={img.url} alt="" style={view(32)} /></span>
                </div>
              )}
            </>
          )}
        </div>
        <div className="pf-sf">
          {mode === "pick" && hasPhoto && <span className="left"><button type="button" className="pf-btn d" onClick={remove}>{t("Remove photo")}</button></span>}
          {mode === "crop" && <span className="left"><button type="button" className="pf-btn g" onClick={() => { setMode("pick"); setErr(""); }}>{t("Choose another")}</button></span>}
          <button type="button" className={"pf-btn o" + (busy ? " off" : "")} aria-disabled={busy} onClick={() => !busy && onClose()}>{t("Cancel")}</button>
          <button type="button" className={"pf-btn p" + (mode !== "crop" ? " off" : "")} aria-disabled={mode !== "crop"} onClick={save}>
            {busy && <span className="pf-spin" aria-hidden="true" />}{busy ? t("Uploading") : t("Save")}
          </button>
        </div>
        {removeDialog}
      </DialogContent>
    </Dialog>
  );
}

function ViewSheet({ open, url, name, onClose, onChange, onRemoved }) {
  const { t } = useI18n();
  const [remove, removeDialog] = useRemovePhoto(onRemoved);
  return (
    <Dialog open={open && !!url} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="pf-sheet" showCloseButton={false}>
        <div className="pf-sh"><DialogTitle asChild><h2>{t("Profile photo")}</h2></DialogTitle><button type="button" className="pf-iconbtn" aria-label={t("Close")} onClick={onClose}>{I.close}</button></div>
        <div className="pf-vb">
          <span className="pf-vph"><img src={url} alt={t("Profile photo of {name}", { name })} /></span>
          <span className="pf-vn">{name}</span>
          <span className="pf-vm">{t("Everyone in HMS sees this photo.")}</span>
        </div>
        <div className="pf-sf">
          <span className="left"><button type="button" className="pf-btn d" onClick={remove}>{t("Remove photo")}</button></span>
          <button type="button" className="pf-btn p" onClick={onChange}>{I.cam}{t("Change photo")}</button>
        </div>
        {removeDialog}
      </DialogContent>
    </Dialog>
  );
}

// ── Activity ─────────────────────────────────────────────────────────────
function ActivityCard({ activity }) {
  const { t } = useI18n();
  const f = activity.filters;
  const [q, setQ] = useState(f.q || "");
  const [fOpen, setFOpen] = useState(false);
  const [df, setDf] = useState(f);
  const [openRow, setOpenRow] = useState(null);
  const [loading, setLoading] = useState(false);
  const panel = useRef(null);
  const timer = useRef(null);

  const load = (next) => {
    const params = {
      q: next.q || undefined, acts: next.acts.join(",") || undefined, types: next.types.join(",") || undefined,
      range: next.range, from: next.range === "custom" ? next.from || undefined : undefined,
      to: next.range === "custom" ? next.to || undefined : undefined, page: next.page > 1 ? next.page : undefined,
    };
    setOpenRow(null);
    router.get("/account/profile/", params, {
      only: ["activity"], preserveState: true, preserveScroll: true, replace: true,
      onStart: () => setLoading(true), onFinish: () => setLoading(false),
    });
  };
  const apply = (nf, page = 1) => load({ ...nf, q, page });

  useEffect(() => {
    if (q === (f.q || "")) return undefined;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => load({ ...f, q, page: 1 }), 300);
    return () => clearTimeout(timer.current);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!fOpen) return undefined;
    const onDoc = (e) => { if (panel.current && !panel.current.contains(e.target)) setFOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setFOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [fOpen]);

  const groupsOn = (x) => (x.acts.length ? 1 : 0) + (x.types.length ? 1 : 0) + (x.range !== "any" ? 1 : 0);
  const tog = (arr, v) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const rangeLabel = (x) => (x.range !== "custom" ? t((RANGES.find((r) => r[0] === x.range) || [])[1])
    : x.from && x.to ? t("{a} to {b}", { a: short(x.from), b: short(x.to) }) : x.from ? t("From {d}", { d: short(x.from) }) : x.to ? t("Until {d}", { d: short(x.to) }) : t("Custom"));
  const chips = [
    ...f.acts.map((v) => ({ label: t(ACT[v][0]), remove: () => apply({ ...f, acts: f.acts.filter((x) => x !== v) }) })),
    ...f.types.map((v) => ({ label: t(v), remove: () => apply({ ...f, types: f.types.filter((x) => x !== v) }) })),
    ...(f.range !== "any" ? [{ label: rangeLabel(f), remove: () => apply({ ...f, range: "any", from: "", to: "" }) }] : []),
  ];
  const clearAll = () => { setQ(""); setFOpen(false); load({ ...NONE, q: "", page: 1 }); };

  const groups = useMemo(() => {
    const out = [];
    const today = new Date(activity.today + "T00:00:00");
    const yest = new Date(today); yest.setDate(today.getDate() - 1);
    for (const a of activity.rows) {
      const d = new Date(a.timestamp);
      const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
      let g = out[out.length - 1];
      if (!g || g.key !== key) {
        const nice = `${t(DAYS[d.getDay()])} ${d.getDate()} ${t(MON[d.getMonth()])}`;
        const same = (x) => x.toDateString() === d.toDateString();
        const label = same(today) ? t("Today, {d}", { d: nice }) : same(yest) ? t("Yesterday, {d}", { d: nice }) : nice;
        const n = activity.day_counts[key] || 0;
        g = { key, label, count: n === 1 ? t("1 entry") : t("{n} entries", { n }), rows: [] };
        out.push(g);
      }
      g.rows.push({ ...a, time: `${pad(d.getHours())}:${pad(d.getMinutes())}`, full: `${dayLabel(d)}, ${pad(d.getHours())}:${pad(d.getMinutes())}` });
    }
    return out;
  }, [activity, t]);

  const page = activity.page, pages = activity.pages;
  const nums = [1, page - 1, page, page + 1, pages].filter((n, i, a) => n >= 1 && n <= pages && a.indexOf(n) === i).sort((a, b) => a - b);
  const hasRows = activity.total > 0;

  return (
    <section className="pf-card pf-act" aria-busy={loading}>
      <div className="pf-ch flat" style={{ alignItems: "center", flexWrap: "wrap" }}>
        <div><h2>{t("Activity")}</h2><p>{t("Everything you did in HMS, newest first.")}</p></div>
        <div className="pf-tools">
          <label className="pf-search">{I.search}<input aria-label={t("Search activity")} placeholder={t("Search record, field or value")} value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <div className="pf-fwrap" ref={panel}>
            <button type="button" className={"pf-fbtn" + (fOpen || groupsOn(f) ? " on" : "")} aria-haspopup="dialog" aria-expanded={fOpen}
              onClick={() => { setDf(f); setFOpen((v) => !v); }}>
              {I.filter}{t("Filter")}{groupsOn(f) > 0 && <span className="pf-fcount">{groupsOn(f)}</span>}
            </button>
            {fOpen && (
              <div className="pf-fpanel" role="dialog" aria-label={t("Filter activity")}>
                <div className="pf-fph">{t("Filter")}</div>
                <div className="pf-fps">
                  <div className="pf-fpsh"><span>{t("Action")}</span><button type="button" className="pf-fpr" onClick={() => setDf({ ...df, acts: [] })}>{t("Reset")}</button></div>
                  <div className="pf-chips">{Object.keys(ACT).map((v) => (
                    <button type="button" key={v} className={"pf-chip" + (df.acts.includes(v) ? " on" : "")} aria-pressed={df.acts.includes(v)} onClick={() => setDf({ ...df, acts: tog(df.acts, v) })}>{t(ACT[v][0])}</button>
                  ))}</div>
                </div>
                {activity.types.length > 0 && (
                  <div className="pf-fps">
                    <div className="pf-fpsh"><span>{t("Record type")}</span><button type="button" className="pf-fpr" onClick={() => setDf({ ...df, types: [] })}>{t("Reset")}</button></div>
                    <div className="pf-tlist">{activity.types.map((c) => {
                      const on = df.types.includes(c.name);
                      return (
                        <button type="button" key={c.name} className={"pf-tck" + (on ? " on" : "")} role="checkbox" aria-checked={on} onClick={() => setDf({ ...df, types: tog(df.types, c.name) })}>
                          <span className="pf-cb">{I.ok}</span><span className="pf-tl">{t(c.name)}</span><span className="pf-tc">{c.count}</span>
                        </button>
                      );
                    })}</div>
                  </div>
                )}
                <div className="pf-fps">
                  <div className="pf-fpsh"><span>{t("Date")}</span><button type="button" className="pf-fpr" onClick={() => setDf({ ...df, range: "any", from: "", to: "" })}>{t("Reset")}</button></div>
                  <div className="pf-chips">{RANGES.map(([v, label]) => (
                    <button type="button" key={v} className={"pf-chip" + (df.range === v ? " on" : "")} aria-pressed={df.range === v} onClick={() => setDf({ ...df, range: v })}>{t(label)}</button>
                  ))}</div>
                  {df.range === "custom" && (
                    <div className="pf-drange">
                      <label>{t("From")}<input type="date" value={df.from} onChange={(e) => setDf({ ...df, from: e.target.value })} /></label>
                      <label>{t("To")}<input type="date" value={df.to} onChange={(e) => setDf({ ...df, to: e.target.value })} /></label>
                    </div>
                  )}
                </div>
                <div className="pf-fpf">
                  <button type="button" className="pf-btn g sm" onClick={clearAll}>{t("Reset all")}</button>
                  <button type="button" className="pf-btn p sm" onClick={() => { setFOpen(false); apply(df); }}>
                    {JSON.stringify(df) !== JSON.stringify(f) ? t("Apply changes") : t("Apply")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {chips.length > 0 && (
        <div className="pf-fchips">
          <span className="pf-fcl">{t("Active filters")}</span>
          {chips.map((c) => <button type="button" key={c.label} className="pf-fchip" aria-label={t("Remove filter {name}", { name: c.label })} onClick={c.remove}>{c.label}{I.x}</button>)}
          <button type="button" className="pf-fclear" onClick={clearAll}>{t("Clear all")}</button>
        </div>
      )}
      {hasRows && <div className="pf-thead"><span>{t("Action")}</span><span>{t("Record")}</span><span>{t("Change")}</span><span style={{ textAlign: "right" }}>{t("Time")}</span></div>}
      {groups.map((g) => (
        <div key={g.key}>
          <div className="pf-band"><span>{g.label}</span><span>{g.count}</span></div>
          {g.rows.map((r) => {
            const ch = Array.isArray(r.changes) ? r.changes : [];
            const open = openRow === r.id;
            const more = ch.length - 1;
            const [label, cls] = ACT[r.action] || [r.action, "pf-pill sm"];
            return (
              <div className="pf-trow" key={r.id}>
                <span className={cls}>{t(label)}</span>
                <span className="pf-rec">{r.model_name ? t(r.model_name) : ""} <b>{r.object_ref}</b></span>
                <span className="pf-chgc">
                  {(open ? ch : ch.slice(0, 1)).map((c, i) => (
                    <span className="pf-ac" key={i}><span>{t(c.label || "")}</span>{c.before !== undefined && c.before !== "" && <s>{String(c.before)}</s>}<b>{String(c.after ?? "")}</b></span>
                  ))}
                  {more > 0 && <button type="button" className="pf-mch" aria-expanded={open} onClick={() => setOpenRow(open ? null : r.id)}>{open ? t("Show less") : t("+{n} more", { n: more })}</button>}
                </span>
                <span className="pf-when" title={r.full}>{r.time}</span>
              </div>
            );
          })}
        </div>
      ))}
      {!hasRows && (
        <div className="pf-empty">
          <span className="pf-ei">{I.empty}</span>
          <b>{t("No activity matches")}</b>
          <span>{t("Try another search, or clear the filters.")}</span>
          <button type="button" className="pf-btn o sm" onClick={clearAll}>{t("Clear all")}</button>
        </div>
      )}
      {hasRows && (
        <nav className="pf-pag" aria-label={t("Pagination")}>
          <span className="pf-pcount">{t("{a} to {b} of {n}", { a: activity.start, b: activity.end, n: activity.total })} {activity.total === 1 ? t("entry") : t("entries")}</span>
          <span className="pf-pnav">
            <button type="button" className="pf-pstep" aria-label={t("Previous page")} aria-disabled={page <= 1} onClick={() => page > 1 && apply(f, page - 1)}>{I.prev}</button>
            {nums.map((n, i) => (
              <span key={n} style={{ display: "contents" }}>
                {i > 0 && n - nums[i - 1] > 1 && <span className="pf-pgap" aria-hidden="true">…</span>}
                <button type="button" className={"pf-pnum" + (n === page ? " cur" : "")} aria-label={t("Page {n}", { n })} aria-current={n === page ? "page" : undefined} onClick={() => n !== page && apply(f, n)}>{n}</button>
              </span>
            ))}
            <button type="button" className="pf-pstep" aria-label={t("Next page")} aria-disabled={page >= pages} onClick={() => page < pages && apply(f, page + 1)}>{I.next}</button>
          </span>
        </nav>
      )}
    </section>
  );
}
