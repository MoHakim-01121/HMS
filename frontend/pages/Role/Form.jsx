import { useState } from "react";
import { router } from "@inertiajs/react";
import { withStandaloneModal, actionsClass } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, ReadOnly, TextIn, Foot, FA, Caption, btnClass } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { Switch } from "../../components/shadcn/ui/switch.jsx";
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
const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring";
// The permission matrix: a header row, group bands and one row per module.
const ROW = "grid min-h-10 min-w-[640px] items-center border-t border-hairline pr-1.5 pl-3.5 hover:bg-[color:color-mix(in_oklch,var(--secondary)_55%,transparent)]";
const HEAD = "min-h-11 border-t-0 bg-background hover:bg-background";
const GROUP = "flex min-h-[34px] min-w-[640px] items-center border-t border-border bg-background px-3.5";
const NAME = "truncate p-0 text-[13px] font-medium";
const CELL = "grid place-items-center";
const COL_BTN = cn("inline-flex h-7 cursor-pointer items-center rounded-[8px] border-0 bg-transparent px-2 font-sans text-[12px] leading-[normal] font-semibold text-muted-foreground enabled:hover:bg-secondary enabled:hover:text-foreground disabled:cursor-default", FOCUS);
const BOX = "size-[18px] cursor-pointer rounded-[5px] border-2 border-input bg-card disabled:cursor-not-allowed disabled:opacity-55";
const CHECK = cn(BOX, "m-0 grid appearance-none place-content-center checked:border-primary checked:bg-primary checked:after:h-1 checked:after:w-2 checked:after:translate-x-px checked:after:-translate-y-px checked:after:-rotate-45 checked:after:border-b-2 checked:after:border-l-2 checked:after:border-primary-foreground checked:after:content-['']", FOCUS);
const TRI = cn(BOX, "grid place-content-center p-0 text-primary-foreground", FOCUS);

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
        <div className="mb-3.5 flex flex-col gap-0.5 rounded-[12px] bg-info-tint px-3.5 py-[11px] text-[13px] leading-normal text-info-text"><b>{t("This role always has full access")}</b><span className="text-foreground">{t("It cannot be edited or deleted, so no one can lock the last administrator out.")}</span></div>
      ) : null}
      <div className={FA.fields}>
        <Field label={t("Name")} required error={errors.label ? t(errors.label) : null}>
          {locked ? <ReadOnly><span className="font-semibold text-foreground">{label}</span></ReadOnly>
            : <TextIn value={label} onChange={setLabel} placeholder={t("Branch supervisor")} autoFocus invalid={!!errors.label} />}
        </Field>
        <Field label={t("Description")} optional error={errors.description ? t(errors.description) : null}>
          {locked ? <ReadOnly>{description}</ReadOnly>
            : <TextIn value={description} onChange={setDescription} maxLength={200} placeholder={t("What this role is for, shown when picking a role")} />}
        </Field>
      </div>

      <div className={FA.sectionHead}>
        <Caption>{t("Permissions")}</Caption>
        <span className={FA.muted}><b className="text-foreground">{granted.size}</b> {t("of {n} ticked", { n: total })}</span>
      </div>
      {errors.permissions ? <div className={FA.alert} role="alert">{t(errors.permissions)}</div> : null}
      <div className="overflow-hidden rounded-[14px] border border-border">
        <div className="overflow-x-auto">
          <div className={cn(ROW, HEAD)} style={{ gridTemplateColumns: `minmax(0,1fr) repeat(${actions.length}, 76px) 64px` }}>
            <span className={cn(NAME, "text-[12px] text-muted-foreground")}>{t("Module")}</span>
            {actions.map((a) => (
              <span key={a.key} className={CELL}>
                <button type="button" className={COL_BTN} disabled={locked} onClick={() => toggleCol(a)} title={t("Toggle {label} for every module", { label: a.label })}>{a.label}</button>
              </span>
            ))}
            <span className={CELL}><span className={COL_BTN}>{t("All")}</span></span>
          </div>
          {groups.map(([name, rows]) => [
            <div key={"g" + name} className={GROUP}><Caption>{t(name)}</Caption></div>,
            ...rows.map((m) => {
              const n = rowCount(m);
              return (
                <div key={m.key} className={ROW} style={{ gridTemplateColumns: `minmax(0,1fr) repeat(${actions.length}, 76px) 64px` }}>
                  <span className={NAME}>{m.label}</span>
                  {actions.map((a) => (
                    <span key={a.key} className={CELL}>
                      <input type="checkbox" className={CHECK} checked={locked || has(m.key, a.key)} disabled={locked}
                        onChange={() => toggle(m.key, a.key)} aria-label={`${m.label}: ${a.label}`} />
                    </span>
                  ))}
                  <span className={CELL}>
                    <button type="button" className={cn(TRI, (locked || n) && "border-primary bg-primary")} disabled={locked}
                      onClick={() => toggleRow(m)} aria-label={t("All of {module}", { module: m.label })}>
                      {locked || n === actions.length ? <Tick /> : n ? <Dash /> : null}
                    </button>
                  </span>
                </div>
              );
            }),
          ])}
          <div className={GROUP}><Caption>{t("Admin only")}</Caption></div>
          <div className={cn(ROW, "grid-cols-[minmax(0,1fr)_minmax(0,3fr)]")}>
            <span className={NAME}>{t("Users and Roles")}</span>
            <span className="text-[13px] text-muted-foreground">{t("Only the Administrator role manages accounts and roles. It cannot be granted here.")}</span>
          </div>
        </div>
      </div>

      <div className={FA.sectionHead}><Caption>{t("Other access")}</Caption></div>
      <div className="flex items-center justify-between gap-4">
        <span><b className="block text-[14px] font-semibold">{t("Django admin")}</b><span className="block text-[13px] text-muted-foreground">{t("Members of this role can also open the Django admin site.")}</span></span>
        <Switch checked={locked || djangoStaff} aria-label={t("Django admin")} disabled={locked} onCheckedChange={setDjangoStaff} />
      </div>

      {locked ? (
        <div className={actionsClass("a")}><a className={btnClass("o")} href="/roles/">{t("Close")}</a></div>
      ) : (
        <Foot why={why} note={editing ? t(role.user_count === 1 ? "1 account holds this role" : "{n} accounts hold this role", { n: role.user_count }) : ""}
          cancelHref="/roles/" submitLabel={editing ? t("Save role") : t("Create role")} processing={processing} />
      )}
    </FormA>
  );
}

export default withStandaloneModal(FormBody, "/roles/");
