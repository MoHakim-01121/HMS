import { useState } from "react";
import { router } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, ReadOnly, TextIn, Foot } from "../../components/shadcn/form-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// New / edit role, the "Role Form" artboard on the Record View HMS canvas:
// name and description, then the permission table per module, grouped as
// the sidebar groups them. Users and Roles stay with the Administrator role
// only; Django admin access is a switch of its own.

const token = (module, action) => `${module}:${action}`;
const GROUPS = [
  ["Operations", ["cl", "invoice", "hotels", "clients", "calendar", "penalty", "landing"]],
  ["Money", ["payments", "bank", "expenses", "remittance"]],
  ["Finance reports", ["statements", "journal", "periods"]],
];

/** {module: [actions]} → Set of "module:action", the shape the table works in. */
function toSet(permissions) {
  const set = new Set();
  for (const [module, actions] of Object.entries(permissions || {})) {
    for (const action of actions || []) set.add(token(module, action));
  }
  return set;
}

const Tick = () => <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M5 12l5 5 9-10" /></svg>;
const Dash = () => <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" aria-hidden="true"><path strokeLinecap="round" d="M6 12h12" /></svg>;

function FormBody({ role, modules = [], actions = [], errors = {} }) {
  const { t } = useI18n();
  const editing = Boolean(role?.slug);
  const locked = Boolean(role?.locked);
  const [label, setLabel] = useState(role?.label ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [djangoStaff, setDjangoStaff] = useState(Boolean(role?.grants_django_staff));
  const [granted, setGranted] = useState(() => toSet(role?.permissions));
  const [processing, setProcessing] = useState(false);

  const total = modules.length * actions.length;
  const mutate = (fn) => setGranted((prev) => { const next = new Set(prev); fn(next); return next; });
  const has = (m, a) => granted.has(token(m, a));
  const toggle = (m, a) => mutate((s) => (s.has(token(m, a)) ? s.delete(token(m, a)) : s.add(token(m, a))));
  const rowCount = (m) => actions.filter((a) => has(m.key, a.key)).length;
  const toggleRow = (m) => {
    const fill = rowCount(m) < actions.length;
    mutate((s) => actions.forEach((a) => (fill ? s.add(token(m.key, a.key)) : s.delete(token(m.key, a.key)))));
  };
  const colFull = (a) => modules.every((m) => has(m.key, a.key));
  const toggleCol = (a) => {
    const fill = !colFull(a);
    mutate((s) => modules.forEach((m) => (fill ? s.add(token(m.key, a.key)) : s.delete(token(m.key, a.key)))));
  };

  // The sidebar's groups; a module the canvas does not name goes under Other.
  const known = new Set(GROUPS.flatMap(([, keys]) => keys));
  const groups = [
    ...GROUPS.map(([name, keys]) => [name, keys.map((k) => modules.find((m) => m.key === k)).filter(Boolean)]),
    ["Other", modules.filter((m) => !known.has(m.key))],
  ].filter(([, rows]) => rows.length);

  const why = locked ? "" : !label.trim() ? t("Name the role.") : "";

  const submit = (e) => {
    e.preventDefault();
    if (why || locked) return;
    // Built by hand rather than through useForm: the table posts one repeated
    // `permissions` key, which Django reads with getlist() and an object-shaped
    // payload cannot express.
    const fd = new FormData();
    fd.append("label", label);
    fd.append("description", description);
    if (djangoStaff) fd.append("grants_django_staff", "1");
    granted.forEach((x) => fd.append("permissions", x));
    setProcessing(true);
    router.post(editing ? `/roles/${role.slug}/edit/` : "/roles/new/", fd, {
      forceFormData: true,
      onFinish: () => setProcessing(false),
    });
  };

  return (
    <FormA title={editing ? role.label : t("New Role")} onSubmit={submit}>
      {locked ? (
        <div className="ro-info"><b>{t("This role always has full access")}</b><span>{t("It cannot be edited or deleted, so no one can lock the last administrator out.")}</span></div>
      ) : null}
      <div className="fa-fields">
        <Field label={t("Name")} required error={errors.label ? t(errors.label) : null}>
          {locked ? <ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{label}</span></ReadOnly>
            : <TextIn value={label} onChange={setLabel} placeholder={t("Branch supervisor")} autoFocus invalid={!!errors.label} />}
        </Field>
        <Field label={t("Description")} optional error={errors.description ? t(errors.description) : null}>
          {locked ? <ReadOnly>{description}</ReadOnly>
            : <TextIn value={description} onChange={setDescription} maxLength={200} placeholder={t("What this role is for, shown when picking a role")} />}
        </Field>
      </div>

      <div className="fa-rh">
        <span className="fa-cap">{t("Permissions")}</span>
        <span className="fa-mut"><b style={{ color: "var(--foreground)" }}>{granted.size}</b> {t("of {n} ticked", { n: total })}</span>
      </div>
      {errors.permissions ? <div className="fa-alert" role="alert">{t(errors.permissions)}</div> : null}
      <div className="ro-mx">
        <div className="fa-scroll" style={{ margin: 0, padding: 0 }}>
          <div className="ro-r ro-h" style={{ gridTemplateColumns: `minmax(0,1fr) repeat(${actions.length}, 76px) 64px` }}>
            <span className="mn">{t("Module")}</span>
            {actions.map((a) => (
              <span key={a.key} className="c">
                <button type="button" className="ro-colb" disabled={locked} onClick={() => toggleCol(a)} title={t("Toggle {label} for every module", { label: a.label })}>{a.label}</button>
              </span>
            ))}
            <span className="c"><span className="ro-colb">{t("All")}</span></span>
          </div>
          {groups.map(([name, rows]) => [
            <div key={"g" + name} className="ro-g"><span className="fa-cap">{t(name)}</span></div>,
            ...rows.map((m) => {
              const n = rowCount(m);
              return (
                <div key={m.key} className="ro-r" style={{ gridTemplateColumns: `minmax(0,1fr) repeat(${actions.length}, 76px) 64px` }}>
                  <span className="mn">{m.label}</span>
                  {actions.map((a) => (
                    <span key={a.key} className="c">
                      <input type="checkbox" className="ro-cb" checked={locked || has(m.key, a.key)} disabled={locked}
                        onChange={() => toggle(m.key, a.key)} aria-label={`${m.label}: ${a.label}`} />
                    </span>
                  ))}
                  <span className="c">
                    <button type="button" className={"ro-tri" + (locked || n === actions.length ? " all" : n ? " some" : "")} disabled={locked}
                      onClick={() => toggleRow(m)} aria-label={t("All of {module}", { module: m.label })}>
                      {locked || n === actions.length ? <Tick /> : n ? <Dash /> : null}
                    </button>
                  </span>
                </div>
              );
            }),
          ])}
          <div className="ro-g"><span className="fa-cap">{t("Admin only")}</span></div>
          <div className="ro-r ro-lock">
            <span className="mn">{t("Users and Roles")}</span>
            <span className="lk">{t("Only the Administrator role manages accounts and roles. It cannot be granted here.")}</span>
          </div>
        </div>
      </div>

      <div className="fa-rh"><span className="fa-cap">{t("Other access")}</span></div>
      <div className="ro-prow">
        <span><b>{t("Django admin")}</b><span>{t("Members of this role can also open the Django admin site.")}</span></span>
        <button type="button" role="switch" aria-checked={locked || djangoStaff} aria-label={t("Django admin")} disabled={locked}
          className={"ro-tg" + (locked || djangoStaff ? " on" : "")} onClick={() => setDjangoStaff((v) => !v)} />
      </div>

      {locked ? (
        <div className="hms-form-actions fa-foot"><a className="fa-btn o" href="/roles/">{t("Close")}</a></div>
      ) : (
        <Foot why={why} note={editing ? t(role.user_count === 1 ? "1 account holds this role" : "{n} accounts hold this role", { n: role.user_count }) : ""}
          cancelHref="/roles/" submitLabel={editing ? t("Save role") : t("Create role")} processing={processing} />
      )}
      <style>{`
.ro-info { display: flex; flex-direction: column; gap: 2px; margin-bottom: 14px; padding: 11px 14px; border-radius: 12px; background: var(--info-tint); color: var(--info-text); font-size: 13px; line-height: 1.5; }
.ro-info span { color: var(--foreground); }
.ro-mx { border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.ro-r { display: grid; align-items: center; min-height: 40px; padding: 0 6px 0 14px; border-top: 1px solid var(--hairline); min-width: 640px; }
.ro-r:hover { background: color-mix(in oklch, var(--secondary) 55%, transparent); }
.ro-r .mn { padding: 0; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ro-r .c { display: grid; place-items: center; }
.ro-h { min-height: 44px; background: var(--background); border-top: 0; }
.ro-h:hover { background: var(--background); }
.ro-h .mn { font-size: 12px; font-weight: 500; color: var(--muted-foreground); }
.ro-colb { display: inline-flex; align-items: center; height: 28px; padding: 0 8px; border: 0; border-radius: 8px; background: none; font: 600 12px var(--font-sans); color: var(--muted-foreground); cursor: pointer; }
.ro-colb:hover:not(:disabled) { background: var(--secondary); color: var(--foreground); }
.ro-colb:disabled, span.ro-colb { cursor: default; }
.ro-g { display: flex; align-items: center; min-height: 34px; padding: 0 14px; border-top: 1px solid var(--border); background: var(--background); min-width: 640px; }
.ro-g .fa-cap { font-size: 12px; }
/* input.ro-cb, not .ro-cb: the global input[type="checkbox"] reset outranks a bare class. */
.ro-r input.ro-cb { appearance: none; margin: 0; width: 18px; height: 18px; border: 2px solid var(--input); border-radius: 5px; display: grid; place-content: center; cursor: pointer; background: var(--card); }
.ro-r input.ro-cb:checked { background: var(--primary); border-color: var(--primary); }
.ro-cb:checked::after { content: ""; width: 8px; height: 4px; border-left: 2px solid var(--primary-foreground); border-bottom: 2px solid var(--primary-foreground); transform: rotate(-45deg) translate(1px, -1px); }
.ro-r input.ro-cb:disabled, .ro-tri:disabled { cursor: not-allowed; opacity: .55; }
.ro-tri { width: 18px; height: 18px; padding: 0; border: 2px solid var(--input); border-radius: 5px; background: var(--card); display: grid; place-content: center; cursor: pointer; color: var(--primary-foreground); }
.ro-tri.all, .ro-tri.some { background: var(--primary); border-color: var(--primary); }
.ro-lock { grid-template-columns: minmax(0,1fr) minmax(0,3fr); }
.ro-lock .lk { font-size: 13px; color: var(--muted-foreground); }
.ro-prow { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.ro-prow b { display: block; font-size: 14px; font-weight: 600; }
.ro-prow span span { display: block; font-size: 13px; color: var(--muted-foreground); }
.ro-tg { position: relative; flex: none; width: 38px; height: 22px; border: 0; border-radius: 999px; background: var(--input); cursor: pointer; padding: 0; transition: background 150ms ease; }
.ro-tg::after { content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.2); transition: transform 150ms ease; }
.ro-tg.on { background: var(--foreground); }
.ro-tg.on::after { transform: translateX(16px); }
.ro-cb:focus-visible, .ro-tri:focus-visible, .ro-colb:focus-visible, .ro-tg:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
`}</style>
    </FormA>
  );
}

export default withStandaloneModal(FormBody, "/roles/");
