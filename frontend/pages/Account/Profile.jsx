import { useEffect, useMemo, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Dialog, DialogContent, DialogTitle } from "../../components/shadcn/ui/dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { saveLanguage } from "../../utils/language.js";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { cn } from "@/lib/utils";
import Page from "../../components/shadcn/page.jsx";

// My Profile, as approved on the Record View HMS canvas (Profile E2): who you
// are with your photo, two cards side by side (personal info, access), the
// language preference, and your activity — opening on today, with search, a
// filter panel, active-filter chips, day bands and pages.

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n) => String(n).padStart(2, "0");
const MB = 1024 * 1024;
const TYPES_OK = ["image/jpeg", "image/png", "image/webp", "image/gif"];

// ── Look ─────────────────────────────────────────────────────────────────
const CARD = "surface overflow-hidden rounded-[20px] border border-border bg-card";
const PILL_TONE = {
  ok: "border-success text-success-text", info: "border-info text-info-text",
  warn: "border-warning text-warning-text", bad: "border-danger text-danger-text",
};
const pill = (tone, sm) => cn(
  "inline-flex h-6 items-center gap-[5px] rounded-full border border-input px-3 text-[12px] font-semibold whitespace-nowrap text-muted-foreground",
  sm && "h-[22px] px-2", PILL_TONE[tone],
);
const BTN = {
  o: "border border-input bg-card text-foreground hover:border-foreground",
  p: "border-0 bg-primary text-primary-foreground shadow-primary hover:bg-primary-hover",
  g: "border-0 bg-transparent px-3 text-muted-foreground hover:bg-secondary hover:text-foreground",
  d: "border-0 bg-transparent px-3 text-danger-text hover:bg-danger-tint",
};
// `off` looks disabled but stays focusable (aria-disabled).
const btn = (kind, { sm, off } = {}) => cn(
  "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-full px-4 font-sans text-[13px] leading-[normal] font-semibold whitespace-nowrap",
  "transition-[background-color,border-color,scale] duration-[120ms] ease-[ease] active:scale-[.97] disabled:cursor-default disabled:opacity-50",
  BTN[kind], sm && "h-8 px-4 text-[13px]", off && "cursor-default opacity-50 active:scale-100",
);
// Card header: title + one line, tools on the right.
const HEAD = "flex items-start justify-between gap-4 border-b border-border px-6 py-4";
const H2 = "m-0 text-[16px] font-semibold tracking-[-0.01em]";
const HEAD_P = "mx-0 mt-0.5 mb-0 text-[13px] leading-[1.5] text-muted-foreground";
// Key / value rows in the two info cards; the editable ones are buttons.
const ROW = "box-border flex min-h-16 w-full items-center gap-4 border-0 border-t border-hairline bg-transparent py-3 pr-5 pl-6 text-left font-sans text-[14px] leading-[normal] font-normal text-foreground";
const KEY = "w-[104px] flex-none text-[13px] text-muted-foreground max-[640px]:w-[88px]";
const VAL = "flex min-w-0 flex-1 flex-col gap-px font-medium";
const VAL_MAIN = "overflow-hidden text-ellipsis whitespace-nowrap";
const VAL_SUB = "text-[12px] leading-[1.45] font-normal text-muted-foreground";
const MUTE = "font-normal text-muted-foreground";
const SAVED = "inline-flex flex-none items-center gap-1 text-[12px] font-semibold text-success-text";
const SEG_BTN = "h-8 cursor-pointer rounded-full border-0 bg-transparent px-4 font-sans text-[13px] leading-[normal] font-semibold text-muted-foreground";
// A drawn text field (search, sheet inputs): the box is the field.
const FIELD = "box-border flex min-w-0 cursor-text items-center gap-2 rounded-[10px] border-[1.5px] border-field bg-card px-3 focus-within:border-foreground focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring focus-within:outline-solid";
const FIELD_INPUT = "h-full min-h-0 min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 font-sans leading-[normal] text-foreground shadow-none outline-none";
// Sheets: a centred card, a bottom sheet on phones.
const SHEET = cn(
  "surface block max-w-[460px] gap-0 rounded-[20px] bg-popover p-0 shadow-palette sm:max-w-[460px]",
  "[&_button:focus-visible]:outline-2 [&_button:focus-visible]:outline-offset-2 [&_button:focus-visible]:outline-ring [&_button:focus-visible]:outline-solid",
  "max-[640px]:top-auto max-[640px]:bottom-0 max-[640px]:w-full max-[640px]:max-w-full max-[640px]:translate-y-0 max-[640px]:rounded-t-[20px] max-[640px]:rounded-b-none max-[640px]:border-b-0",
);
const SHEET_WIDE = "max-w-[480px] sm:max-w-[480px]";
const ICON_BTN = "grid size-8 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground hover:bg-secondary hover:text-foreground disabled:cursor-default disabled:opacity-40";
const SHEET_FOOT = "flex justify-end gap-2 rounded-b-[20px] border-t border-border bg-card px-5 py-4 max-[640px]:rounded-none max-[640px]:[&_button]:flex-1";
const PREVIEW_IMG = "pointer-events-none absolute max-w-none select-none [-webkit-user-drag:none]";
const FILTER_CHIP = "inline-flex h-8 cursor-pointer items-center rounded-full border border-input bg-card px-3 font-sans text-[12px] leading-[normal] font-semibold text-muted-foreground hover:border-foreground hover:text-foreground";
const FILTER_CHIP_ON = "border-foreground bg-foreground text-background hover:text-background";
const ACT_COLS = "grid grid-cols-[84px_minmax(0,1fr)_minmax(0,1.6fr)_104px] items-center gap-4 px-6";
const SHEET_BODY = "flex flex-col gap-2 px-6 pt-4 pb-6";
const SHEET_NOTE = "mt-0 mb-2 text-[13px] leading-[1.5] text-muted-foreground";
const PHOTO_ERR = "mt-1 flex items-start gap-2 text-[13px] text-danger-text [&_svg]:mt-px [&_svg]:flex-none";
const PREVIEW = "relative flex-none overflow-hidden rounded-full bg-photo-backdrop ring-1 ring-border";
const PAGE_BTN = "box-border grid h-[34px] min-w-[34px] cursor-pointer place-content-center rounded-full border-0 bg-transparent px-2 font-sans text-[13px] leading-[normal] font-semibold text-foreground tabular-nums hover:bg-secondary";

const PAGE_STEP = cn(PAGE_BTN, "aria-disabled:cursor-default aria-disabled:opacity-35 aria-disabled:hover:bg-transparent");

const ACT = {
  login: ["Sign in", null],
  create: ["Create", "ok"],
  edit: ["Edit", "warn"],
  delete: ["Delete", "bad"],
  pdf: ["Export PDF", "info"],
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
  const isSuperuser = account.is_superuser;
  const canEditUsername = account.can_edit_username ?? isSuperuser;
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
    { key: "username", label: t("Username"), value: account.username, editable: canEditUsername,
      sub: canEditUsername ? t("Used to sign in") : t("Used to sign in. Only an administrator can change it.") },
  ];

  const pickLang = async (v) => {
    if (v === lang) return;
    setLang(v);
    try {
      await saveLanguage(v, { preserveScroll: true });
      setLangOk(true);
    } catch { setLang(lang); }
  };

  return (
    <Page>
      <div className="mx-auto flex max-w-[1040px] flex-col gap-4 pt-1 pb-16 text-[14px] leading-[1.5] text-foreground [&_:is(button,input,a):focus-visible]:outline-2 [&_:is(button,input,a):focus-visible]:outline-offset-2 [&_:is(button,input,a):focus-visible]:outline-ring [&_:is(button,input,a):focus-visible]:outline-solid">
        <div>
          <a href="/" className="inline-flex items-center gap-1 text-[13px] font-medium text-muted-foreground no-underline hover:text-foreground"
            onClick={(e) => { if (window.history.length > 1) { e.preventDefault(); window.history.back(); } }}>{I.back}{t("Back")}</a>
        </div>
        {toast && <div className="flex items-center gap-2 rounded-[12px] bg-success-tint px-4 py-3 text-[13px] font-semibold text-success-text" role="status">{I.ok}{toast}</div>}

        <section className={cn(CARD, "flex flex-wrap items-center gap-6 p-7 max-[640px]:p-5")}>
          <button type="button" aria-label={profile.avatar_url ? t("View photo") : t("Add a photo")}
            className="relative grid size-[88px] flex-none cursor-pointer place-content-center rounded-full border-0 bg-secondary p-0 font-sans text-[30px] leading-[normal] font-semibold tracking-[-0.02em] text-foreground ring-1 ring-border"
            onClick={() => setPhoto(profile.avatar_url ? "view" : "pick")}>
            {profile.avatar_url
              ? <span className="absolute inset-0 overflow-hidden rounded-full"><img className="block size-full object-cover" src={profile.avatar_url} alt="" /></span>
              : initials(account.full_name)}
            <span className="absolute right-[-2px] bottom-0.5 grid size-[30px] place-content-center rounded-full bg-foreground text-background ring-3 ring-card">{I.cam}</span>
          </button>
          <div className="min-w-0">
            <h1 className="m-0 text-[24px] leading-[1.15] font-semibold tracking-[-0.025em]">{account.full_name}</h1>
            <div className="mt-[3px] text-[14px] text-muted-foreground">{account.email || t("No email")}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className={pill("info")}>{account.role_badge}</span>
              <span className={pill()}>{t(account.branch)}</span>
              <span className={pill(account.is_active && "ok")}>{account.is_active ? t("Active") : t("Inactive")}</span>
              {isSuperuser && <span className={pill()}>{t("Superuser")}</span>}
            </div>
          </div>
          <dl className="m-0 ml-auto flex flex-wrap gap-y-3 max-[900px]:ml-0 max-[900px]:w-full">
            {[
              [t("Username"), account.username],
              [t("Last sign in"), lastSignIn(account.last_login, t)],
              [t("Member since"), account.date_joined ? dayLabel(new Date(account.date_joined)) : "—"],
            ].map(([k, v], i) => (
              <div key={k} className={cn("px-6 last:pr-0 max-[900px]:first:pl-0 max-[640px]:px-4", i > 0 && "border-l border-border")}>
                <dt className="text-[12px] text-muted-foreground">{k}</dt>
                <dd className="mx-0 mt-0.5 mb-0 text-[14px] font-semibold whitespace-nowrap">{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        <div className="grid grid-cols-2 items-stretch gap-4 max-[900px]:grid-cols-1">
          <section className={cn(CARD, "flex flex-col")}>
            <div className={HEAD}><div><h2 className={H2}>{t("Personal info")}</h2><p className={HEAD_P}>{t("How other people in HMS see you.")}</p></div></div>
            {fields.map((f, i) => f.editable ? (
              <button type="button" key={f.key} aria-label={t("Edit {field}", { field: f.label.toLowerCase() })}
                className={cn(ROW, "cursor-pointer transition-[background-color] duration-[120ms] ease-[ease] hover:bg-secondary", i === 0 && "border-t-0")}
                onClick={() => { setOk(null); setEdit(f.key); }}>
                <span className={KEY}>{f.label}</span>
                <span className={VAL}><span className={cn(VAL_MAIN, !f.value && MUTE)}>{f.value || t("Not set")}</span>{f.sub && <small className={VAL_SUB}>{f.sub}</small>}</span>
                {ok === f.key && <span className={SAVED} role="status">{I.ok}{t("Saved")}</span>}
                <span className="grid flex-none text-muted-foreground">{I.go}</span>
              </button>
            ) : (
              <div key={f.key} className={cn(ROW, i === 0 && "border-t-0")}>
                <span className={KEY}>{f.label}</span>
                <span className={VAL}><span className={VAL_MAIN}>{f.value}</span><small className={VAL_SUB}>{f.sub}</small></span>
                <span className="grid flex-none text-muted-foreground">{I.lock}</span>
              </div>
            ))}
          </section>

          <section className={cn(CARD, "flex flex-col")}>
            <div className={HEAD}>
              <div><h2 className={H2}>{t("Access and sign-in")}</h2><p className={HEAD_P}>{t("What you can do in HMS and how you sign in.")}</p></div>
              <span className="flex-none pt-0.5 text-[12px] font-semibold text-muted-foreground">{t("Managed by an administrator")}</span>
            </div>
            <div className={cn(ROW, "border-t-0")}><span className={KEY}>{t("Role")}</span><span className={VAL}><span className={VAL_MAIN}>{account.role}</span>{account.role_meta && <small className={VAL_SUB}>{t(account.role_meta)}</small>}</span></div>
            <div className={ROW}><span className={KEY}>{t("Branch")}</span><span className={VAL}><span className={VAL_MAIN}>{t(account.branch)}</span><small className={VAL_SUB}>{t(account.branch_meta)}</small></span></div>
            <div className={ROW}><span className={KEY}>{t("Password")}</span><span className={VAL}><span className={cn(VAL_MAIN, MUTE, "tracking-[3px]")}>••••••••</span><small className={VAL_SUB}>{t("Forgot it? An administrator can reset it for you.")}</small></span></div>
          </section>
        </div>

        <section className={CARD}>
          <div className={cn(HEAD, "flex-wrap items-center border-b-0")}>
            <div><h2 className={H2}>{t("Preferences")}</h2><p className={HEAD_P}>{t("Only changes HMS for you.")}</p></div>
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-[13px] font-semibold">{t("Language")}</span>
              {langOk && <span className={SAVED} role="status">{I.ok}{t("Saved")}</span>}
              <span className="inline-flex flex-none rounded-full bg-secondary p-[3px]" role="group" aria-label={t("Language")}>
                {[["en", "English"], ["id", "Indonesian"]].map(([v, label]) => (
                  <button type="button" key={v} className={cn(SEG_BTN, lang === v && "bg-card text-foreground shadow-seg")} aria-pressed={lang === v} onClick={() => pickLang(v)}>{t(label)}</button>
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
    </Page>
  );
}

const SheetHead = ({ title, onClose, busy }) => {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-between pt-4 pr-4 pb-0 pl-6">
      <DialogTitle asChild><h2 className="m-0 text-[17px] font-semibold tracking-[-0.01em]">{title}</h2></DialogTitle>
      <button type="button" className={ICON_BTN} aria-label={t("Close")} disabled={busy} onClick={() => !busy && onClose()}>{I.close}</button>
    </div>
  );
};

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
      <DialogContent className={SHEET} showCloseButton={false}>
        {cur && (
          <>
            <SheetHead title={cur.title} onClose={onClose} />
            <div className={SHEET_BODY}>
              <p className={SHEET_NOTE}>{cur.note}</p>
              <label className="flex flex-col gap-1.5">
                <span className="text-[13px] font-medium text-muted-foreground">{cur.label}</span>
                <span className={cn(FIELD, "h-11 transition-[border-color] duration-[120ms] ease-[ease]", shown && "border-danger focus-within:border-danger")}>
                  <input aria-label={cur.label} type={cur.type} autoComplete="off" value={draft} autoFocus
                    className={cn(FIELD_INPUT, "text-[14px] font-semibold")}
                    onChange={(e) => { setDraft(e.target.value); setServer(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } }} />
                </span>
              </label>
              <span className={cn("text-[12px] text-muted-foreground", shown && "text-danger-text")}>{shown ? t(shown) : cur.hint}</span>
            </div>
            <div className={SHEET_FOOT}><button type="button" className={btn("o")} onClick={onClose}>{t("Cancel")}</button><button type="button" className={btn("p")} onClick={save} disabled={busy}>{t("Save")}</button></div>
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
      <DialogContent className={cn(SHEET, SHEET_WIDE)} showCloseButton={false} aria-busy={busy}>
        <SheetHead title={hasPhoto ? t("Change photo") : t("Add a photo")} onClose={onClose} busy={busy} />
        <div className={SHEET_BODY}>
          {mode === "pick" ? (
            <>
              <label
                className={cn(
                  "relative flex min-h-[220px] cursor-pointer flex-col items-center justify-center gap-2 rounded-[16px] border-[1.5px] border-dashed border-input p-6 text-center",
                  "bg-[color:color-mix(in_oklch,var(--foreground)_3%,var(--card))] transition-[border-color,background-color] duration-[120ms] ease-[ease]",
                  "hover:border-foreground hover:bg-secondary focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring focus-within:outline-solid",
                  over && "border-foreground bg-secondary",
                  err && "border-danger bg-danger-tint hover:border-danger hover:bg-danger-tint",
                )}
                onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                onDrop={(e) => { e.preventDefault(); setOver(false); check(e.dataTransfer?.files?.[0]); }}>
                <input className="sr-only" type="file" accept={TYPES_OK.join(",")} onChange={(e) => check(e.target.files?.[0])} />
                <span className="mb-1 grid size-11 place-content-center rounded-full border border-border bg-card text-foreground">{I.up}</span>
                <span className="text-[14px] font-semibold [&_u]:underline-offset-3">{t("Drag a photo here or")} <u>{t("choose a file")}</u></span>
                <span className="text-[12px] text-muted-foreground">{t("JPG, PNG, WEBP or GIF, up to 10 MB")}</span>
              </label>
              {err && <span className={PHOTO_ERR} role="alert">{I.err}{err}</span>}
            </>
          ) : (
            <>
              <div className="mb-3 text-center text-[13px] text-muted-foreground">{file?.name}, {(file?.size / MB).toFixed(1)} MB</div>
              <div ref={cropRef} tabIndex={busy ? -1 : 0}
                className={cn(
                  "relative mx-auto size-[320px] cursor-grab touch-none overflow-hidden rounded-[16px] bg-photo-backdrop active:cursor-grabbing max-[640px]:size-[296px]",
                  "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ring focus-visible:outline-solid",
                  busy && "cursor-default active:cursor-default",
                )}
                aria-label={busy ? t("Crop area, locked while uploading") : t("Crop area. Drag the photo or use the arrow keys to move it.")}
                onPointerDown={(e) => { if (busy) return; e.currentTarget.setPointerCapture(e.pointerId); drag.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y }; }}
                onPointerMove={(e) => { const g = drag.current; if (g) setXY(g.ox + e.clientX - g.sx, g.oy + e.clientY - g.sy); }}
                onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
                onKeyDown={(e) => {
                  const m = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -8], ArrowDown: [0, 8] }[e.key];
                  if (!m || busy) return;
                  e.preventDefault(); setXY(pos.x + m[0], pos.y + m[1]);
                }}>
                {img && <img className={PREVIEW_IMG} src={img.url} alt="" style={cropStyle} />}
                <span className="pointer-events-none absolute inset-3 rounded-full border-2 border-white/90 shadow-crop-mask" aria-hidden="true" />
              </div>
              <div className="mx-auto mt-4 flex w-[320px] max-w-full items-center gap-3 text-muted-foreground [&_svg]:flex-none">
                {I.minus}
                <input type="range" min="1" max="3" step="0.01" aria-label={t("Zoom")} value={pos.z} disabled={busy}
                  className="min-w-0 flex-1 accent-foreground"
                  onChange={(e) => setXY(pos.x, pos.y, parseFloat(e.target.value))} />
                {I.plus}
              </div>
              {err && <span className={PHOTO_ERR} role="alert">{I.err}{err}</span>}
              {!busy && img && (
                <div className="mt-4 flex items-center gap-4 border-t border-hairline pt-4">
                  <span className="mr-auto text-[13px] font-medium text-muted-foreground">{t("Preview")}</span>
                  <span className={cn(PREVIEW, "size-[72px]")}><img className={PREVIEW_IMG} src={img.url} alt="" style={view(72)} /></span>
                  <span className={cn(PREVIEW, "size-8")}><img className={PREVIEW_IMG} src={img.url} alt="" style={view(32)} /></span>
                </div>
              )}
            </>
          )}
        </div>
        <div className={SHEET_FOOT}>
          {mode === "pick" && hasPhoto && <span className="mr-auto"><button type="button" className={btn("d")} onClick={remove}>{t("Remove photo")}</button></span>}
          {mode === "crop" && <span className="mr-auto"><button type="button" className={btn("g")} onClick={() => { setMode("pick"); setErr(""); }}>{t("Choose another")}</button></span>}
          <button type="button" className={btn("o", { off: busy })} aria-disabled={busy} onClick={() => !busy && onClose()}>{t("Cancel")}</button>
          <button type="button" className={btn("p", { off: mode !== "crop" })} aria-disabled={mode !== "crop"} onClick={save}>
            {busy && <span className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent [animation-duration:700ms]" aria-hidden="true" />}{busy ? t("Uploading") : t("Save")}
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
      <DialogContent className={SHEET} showCloseButton={false}>
        <SheetHead title={t("Profile photo")} onClose={onClose} />
        <div className="flex flex-col items-center gap-1 px-6 pt-2 pb-6 text-center">
          <span className="relative mb-4 size-[280px] max-w-full overflow-hidden rounded-full ring-1 ring-border"><img className="block size-full object-cover" src={url} alt={t("Profile photo of {name}", { name })} /></span>
          <span className="text-[17px] font-semibold tracking-[-0.01em]">{name}</span>
          <span className="text-[13px] text-muted-foreground">{t("Everyone in HMS sees this photo.")}</span>
        </div>
        <div className={SHEET_FOOT}>
          <span className="mr-auto"><button type="button" className={btn("d")} onClick={remove}>{t("Remove photo")}</button></span>
          <button type="button" className={btn("p")} onClick={onChange}>{I.cam}{t("Change photo")}</button>
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
    <section className={cn(CARD, "overflow-visible")} aria-busy={loading}>
      <div className={cn(HEAD, "flex-wrap items-center border-b-0")}>
        <div><h2 className={H2}>{t("Activity")}</h2><p className={HEAD_P}>{t("Everything you did in HMS, newest first.")}</p></div>
        <div className="flex flex-wrap items-center gap-3">
          <label className={cn(FIELD, "h-9 w-[280px] max-w-full max-[640px]:w-auto max-[640px]:flex-1 [&_svg]:flex-none [&_svg]:text-muted-foreground")}>
            {I.search}
            <input aria-label={t("Search activity")} placeholder={t("Search record, field or value")} value={q} onChange={(e) => setQ(e.target.value)}
              className={cn(FIELD_INPUT, "text-[13px] font-medium")} />
          </label>
          <div className="relative" ref={panel}>
            <button type="button" aria-haspopup="dialog" aria-expanded={fOpen}
              className={cn(
                "inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border border-input bg-card px-4 font-sans text-[13px] leading-[normal] font-semibold text-foreground hover:border-foreground [&_svg]:text-muted-foreground",
                (fOpen || groupsOn(f)) && "border-foreground bg-secondary",
              )}
              onClick={() => { setDf(f); setFOpen((v) => !v); }}>
              {I.filter}{t("Filter")}
              {groupsOn(f) > 0 && <span className="box-border grid h-[18px] min-w-[18px] place-content-center rounded-full bg-foreground px-[5px] text-[12px] font-semibold text-background">{groupsOn(f)}</span>}
            </button>
            {fOpen && (
              <div className="surface absolute top-[calc(100%_+_8px)] right-0 z-30 w-[380px] max-w-[calc(100vw_-_48px)] rounded-[16px] border border-border bg-popover text-left shadow-menu"
                role="dialog" aria-label={t("Filter activity")}>
                <div className="px-4 pt-4 pb-2 text-[14px] font-semibold">{t("Filter")}</div>
                <FilterSection title={t("Action")} onReset={() => setDf({ ...df, acts: [] })}>
                  <div className="flex flex-wrap gap-2">{Object.keys(ACT).map((v) => (
                    <button type="button" key={v} className={cn(FILTER_CHIP, df.acts.includes(v) && FILTER_CHIP_ON)} aria-pressed={df.acts.includes(v)} onClick={() => setDf({ ...df, acts: tog(df.acts, v) })}>{t(ACT[v][0])}</button>
                  ))}</div>
                </FilterSection>
                {activity.types.length > 0 && (
                  <FilterSection title={t("Record type")} onReset={() => setDf({ ...df, types: [] })}>
                    <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">{activity.types.map((c) => {
                      const on = df.types.includes(c.name);
                      return (
                        <button type="button" key={c.name} role="checkbox" aria-checked={on} onClick={() => setDf({ ...df, types: tog(df.types, c.name) })}
                          className="flex min-h-[34px] cursor-pointer items-center gap-2 rounded-[8px] border-0 bg-transparent px-2 text-left font-sans text-[13px] leading-[normal] font-medium text-foreground hover:bg-secondary">
                          <span className={cn("box-border grid size-4 flex-none place-content-center rounded-[5px] border-[1.5px] border-field text-transparent", on && "border-foreground bg-foreground text-background")}>{I.ok}</span>
                          <span className="min-w-0 flex-1 truncate">{t(c.name)}</span>
                          <span className="text-[12px] text-muted-foreground tabular-nums">{c.count}</span>
                        </button>
                      );
                    })}</div>
                  </FilterSection>
                )}
                <FilterSection title={t("Date")} onReset={() => setDf({ ...df, range: "any", from: "", to: "" })}>
                  <div className="flex flex-wrap gap-2">{RANGES.map(([v, label]) => (
                    <button type="button" key={v} className={cn(FILTER_CHIP, df.range === v && FILTER_CHIP_ON)} aria-pressed={df.range === v} onClick={() => setDf({ ...df, range: v })}>{t(label)}</button>
                  ))}</div>
                  {df.range === "custom" && (
                    <div className="mt-3 flex gap-2">
                      {[["From", "from"], ["To", "to"]].map(([label, k]) => (
                        <label key={k} className="flex min-w-0 flex-1 flex-col gap-1 text-[12px] font-medium text-muted-foreground">
                          {t(label)}
                          <input type="date" value={df[k]} onChange={(e) => setDf({ ...df, [k]: e.target.value })}
                            className="box-border h-9 rounded-[10px] border-[1.5px] border-field bg-card px-3 font-sans text-[13px] leading-[normal] font-medium text-foreground" />
                        </label>
                      ))}
                    </div>
                  )}
                </FilterSection>
                <div className="flex justify-between rounded-b-[16px] border-t border-border bg-card px-4 py-3">
                  <button type="button" className={btn("g", { sm: true })} onClick={clearAll}>{t("Reset all")}</button>
                  <button type="button" className={btn("p", { sm: true })} onClick={() => { setFOpen(false); apply(df); }}>
                    {JSON.stringify(df) !== JSON.stringify(f) ? t("Apply changes") : t("Apply")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 px-6 pt-0 pb-4">
          <span className="mr-1 text-[12px] text-muted-foreground">{t("Active filters")}</span>
          {chips.map((c) => (
            <button type="button" key={c.label} aria-label={t("Remove filter {name}", { name: c.label })} onClick={c.remove}
              className="inline-flex h-7 cursor-pointer items-center gap-2 rounded-full border border-input bg-secondary pr-2 pl-3 font-sans text-[12px] leading-[normal] font-semibold text-foreground hover:border-foreground [&_svg]:text-muted-foreground">
              {c.label}{I.x}
            </button>
          ))}
          <button type="button" onClick={clearAll}
            className="cursor-pointer border-0 bg-transparent px-2 py-0 font-sans text-[12px] leading-[normal] font-semibold text-muted-foreground underline underline-offset-3 hover:text-foreground">
            {t("Clear all")}
          </button>
        </div>
      )}
      {hasRows && (
        <div className={cn(ACT_COLS, "border-t border-border py-2 text-[12px] font-medium text-muted-foreground max-[640px]:hidden")}>
          <span>{t("Action")}</span><span>{t("Record")}</span><span>{t("Change")}</span><span className="text-right">{t("Time")}</span>
        </div>
      )}
      {groups.map((g) => (
        <div key={g.key}>
          <div className="flex justify-between border-t border-hairline bg-day-band px-6 py-2 text-[12px] font-semibold text-muted-foreground"><span>{g.label}</span><span>{g.count}</span></div>
          {g.rows.map((r) => {
            const ch = Array.isArray(r.changes) ? r.changes : [];
            const open = openRow === r.id;
            const more = ch.length - 1;
            const [label, tone] = ACT[r.action] || [r.action, null];
            return (
              <div key={r.id} className={cn(ACT_COLS, "box-border min-h-[52px] border-t border-hairline py-3 text-[14px] max-[640px]:grid-cols-[auto_minmax(0,1fr)_auto]")}>
                <span className={cn(pill(tone, true), "justify-self-start")}>{t(label)}</span>
                <span className="min-w-0 truncate text-muted-foreground">{r.model_name ? t(r.model_name) : ""} <b className="font-semibold text-foreground">{r.object_ref}</b></span>
                <span className="flex min-w-0 flex-col gap-[3px] max-[640px]:order-4 max-[640px]:col-span-full">
                  {(open ? ch : ch.slice(0, 1)).map((c, i) => (
                    <span className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground" key={i}>
                      <span>{t(c.label || "")}</span>
                      {c.before !== undefined && c.before !== "" && <s>{String(c.before)}</s>}
                      <b className="font-semibold text-foreground">{String(c.after ?? "")}</b>
                    </span>
                  ))}
                  {more > 0 && (
                    <button type="button" aria-expanded={open} onClick={() => setOpenRow(open ? null : r.id)}
                      className="cursor-pointer self-start border-0 bg-transparent p-0 font-sans text-[12px] leading-[normal] font-semibold text-info-text hover:underline hover:underline-offset-3">
                      {open ? t("Show less") : t("+{n} more", { n: more })}
                    </button>
                  )}
                </span>
                <span className="text-right text-[12px] text-muted-foreground tabular-nums" title={r.full}>{r.time}</span>
              </div>
            );
          })}
        </div>
      ))}
      {!hasRows && (
        <div className="flex flex-col items-center gap-1 border-t border-hairline px-6 py-12 text-center text-[13px] text-muted-foreground">
          <span className="mb-2 grid size-11 place-content-center rounded-full bg-secondary text-muted-foreground">{I.empty}</span>
          <b className="text-[14px] text-foreground">{t("No activity matches")}</b>
          <span>{t("Try another search, or clear the filters.")}</span>
          <button type="button" className={cn(btn("o", { sm: true }), "mt-3")} onClick={clearAll}>{t("Clear all")}</button>
        </div>
      )}
      {hasRows && (
        <nav className="flex flex-wrap items-center justify-between gap-3 rounded-b-[20px] border-t border-border bg-muted py-3 pr-4 pl-6" aria-label={t("Pagination")}>
          <span className="text-[13px] text-muted-foreground tabular-nums">{t("{a} to {b} of {n}", { a: activity.start, b: activity.end, n: activity.total })} {activity.total === 1 ? t("entry") : t("entries")}</span>
          <span className="flex items-center gap-0.5">
            <button type="button" className={PAGE_STEP} aria-label={t("Previous page")} aria-disabled={page <= 1} onClick={() => page > 1 && apply(f, page - 1)}>{I.prev}</button>
            {nums.map((n, i) => (
              <span key={n} className="contents">
                {i > 0 && n - nums[i - 1] > 1 && <span className="grid w-[22px] place-content-center text-muted-foreground" aria-hidden="true">…</span>}
                <button type="button" className={cn(PAGE_BTN, n === page && "bg-foreground text-background hover:bg-foreground")} aria-label={t("Page {n}", { n })} aria-current={n === page ? "page" : undefined} onClick={() => n !== page && apply(f, n)}>{n}</button>
              </span>
            ))}
            <button type="button" className={PAGE_STEP} aria-label={t("Next page")} aria-disabled={page >= pages} onClick={() => page < pages && apply(f, page + 1)}>{I.next}</button>
          </span>
        </nav>
      )}
    </section>
  );
}

function FilterSection({ title, onReset, children }) {
  const { t } = useI18n();
  return (
    <div className="border-t border-hairline px-4 pt-3 pb-4">
      <div className="mb-2 flex items-center justify-between text-[12px] font-semibold tracking-[.08em] text-muted-foreground uppercase">
        <span>{title}</span>
        <button type="button" onClick={onReset}
          className="cursor-pointer border-0 bg-transparent px-1 py-0.5 font-sans text-[12px] leading-[normal] font-semibold tracking-normal text-muted-foreground normal-case hover:text-foreground">
          {t("Reset")}
        </button>
      </div>
      {children}
    </div>
  );
}
