import { useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const token = (module, action) => `${module}:${action}`;

/** {module: [actions]} → Set of "module:action", the shape the grid works in. */
function toSet(permissions) {
  const set = new Set();
  for (const [module, actions] of Object.entries(permissions || {})) {
    for (const action of actions || []) set.add(token(module, action));
  }
  return set;
}

function Cell({ checked, onChange, label }) {
  return (
    <td className="px-2 py-2 text-center">
      <Checkbox checked={checked} onCheckedChange={onChange} aria-label={label} className="mx-auto" />
    </td>
  );
}

export default function Form({ role, modules = [], actions = [], errors = {} }) {
  const { t } = useI18n();
  const editing = Boolean(role?.slug);
  const [label, setLabel] = useState(role?.label ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [djangoStaff, setDjangoStaff] = useState(Boolean(role?.grants_django_staff));
  const [granted, setGranted] = useState(() => toSet(role?.permissions));
  const [processing, setProcessing] = useState(false);

  const total = modules.length * actions.length;
  const count = granted.size;

  const mutate = (fn) => setGranted((prev) => { const next = new Set(prev); fn(next); return next; });

  const has = (m, a) => granted.has(token(m, a));
  const toggle = (m, a) => mutate((s) => (s.has(token(m, a)) ? s.delete(token(m, a)) : s.add(token(m, a))));

  const rowFull = (m) => actions.every((a) => has(m.key, a.key));
  const toggleRow = (m) => {
    const fill = !rowFull(m);
    mutate((s) => actions.forEach((a) => (fill ? s.add(token(m.key, a.key)) : s.delete(token(m.key, a.key)))));
  };

  const colFull = (a) => modules.every((m) => has(m.key, a.key));
  const toggleCol = (a) => {
    const fill = !colFull(a);
    mutate((s) => modules.forEach((m) => (fill ? s.add(token(m.key, a.key)) : s.delete(token(m.key, a.key)))));
  };

  const allFull = useMemo(() => count === total && total > 0, [count, total]);
  const toggleAll = () => {
    if (allFull) return setGranted(new Set());
    const next = new Set();
    modules.forEach((m) => actions.forEach((a) => next.add(token(m.key, a.key))));
    setGranted(next);
  };

  const submit = (e) => {
    e.preventDefault();
    // Built by hand rather than through useForm: the matrix posts one repeated
    // `permissions` key, which Django reads with getlist() and an object-shaped
    // payload cannot express.
    const fd = new FormData();
    fd.append("label", label);
    fd.append("description", description);
    if (djangoStaff) fd.append("grants_django_staff", "1");
    granted.forEach((t) => fd.append("permissions", t));

    setProcessing(true);
    router.post(editing ? `/roles/${role.slug}/edit/` : "/roles/new/", fd, {
      forceFormData: true,
      onFinish: () => setProcessing(false),
    });
  };

  return (
    <div className="form-page shadcn-root">
      <PageBack href="/roles/" />
      <FormHeader
        kicker={t("Role")}
        title={editing ? t("Edit {label}", { label: role.label }) : t("New Role")}
        sub={editing ? t("{count} account(s) hold this role", { count: role.user_count }) : t("Define what this role may do")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Identity")}>
            <FormField
              label={t("Role name")} name="label" required
              value={label} onChange={setLabel} error={errors.label} autoFocus
            />
            <div style={{ marginTop: 12 }}>
              <FormField
                label={t("Description")} name="description"
                hint={t("Shown under the role picker when assigning accounts.")}
                value={description} onChange={setDescription} error={errors.description}
              />
            </div>
            <label className="flex items-center gap-2 mt-3 cursor-pointer text-sm">
              <Checkbox checked={djangoStaff} onCheckedChange={(v) => setDjangoStaff(Boolean(v))} />
              <span>{t("Also grant Django admin access (is_staff)")}</span>
            </label>
          </FormSection>

          <FormSection
            label={t("Permissions")}
            sub={t("{count} of {total} granted", { count, total })}
            action={
              <button type="button" className="btn btn-ghost btn-sm" onClick={toggleAll}>
                {allFull ? t("Clear all") : t("Grant all")}
              </button>
            }
          >
            {errors.permissions && (
              <div role="alert" style={{ fontSize: 12, color: "var(--destructive)" }}>
                {errors.permissions}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="text-left font-medium py-2 pr-3">{t("Module")}</th>
                    {actions.map((a) => (
                      <th key={a.key} className="py-2 px-2 font-medium">
                        <button
                          type="button"
                          // design.css styles bare <button>; reset it so the
                          // column header reads as a label, not a chip.
                          className="bg-transparent border-0 p-0 shadow-none font-medium hover:underline whitespace-nowrap cursor-pointer"
                          onClick={() => toggleCol(a)}
                          title={t("Toggle {label} for every module", { label: a.label })}
                        >
                          {a.label}
                        </button>
                      </th>
                    ))}
                    <th className="py-2 pl-2 text-right font-medium">{t("All")}</th>
                  </tr>
                </thead>
                <tbody>
                  {modules.map((m) => (
                    <tr key={m.key} className="border-b last:border-0">
                      <td className="py-2 pr-3 whitespace-nowrap">{m.label}</td>
                      {actions.map((a) => (
                        <Cell
                          key={a.key}
                          checked={has(m.key, a.key)}
                          onChange={() => toggle(m.key, a.key)}
                          label={`${m.label}: ${a.label}`}
                        />
                      ))}
                      <td className="py-2 pl-2 text-right">
                        <button
                          type="button"
                          className="bg-transparent border-0 p-0 shadow-none text-xs opacity-70 hover:opacity-100 hover:underline cursor-pointer"
                          onClick={() => toggleRow(m)}
                        >
                          {rowFull(m) ? t("none") : t("all")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </FormSection>

          <FormActions
            cancelHref="/roles/"
            submitLabel={editing ? t("Save role") : t("Create role")}
            processing={processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}
