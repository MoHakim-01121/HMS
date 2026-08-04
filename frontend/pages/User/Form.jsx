import { useForm } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function Form({ form_data, errors: serverErrors, role_choices = [], company_choices = [] }) {
  const { t } = useI18n();
  // The hint under the picker is the role's own description, edited at /roles/,
  // so a custom role explains itself here without a second copy in the client.
  const roleHint = Object.fromEntries(role_choices.map((c) => [c.value, c.description || ""]));
  const fd = form_data || {};
  const form = useForm({
    username: fd.username || "", full_name: fd.full_name || "",
    password: "", password_confirm: "",
    role: fd.role || "staff",
    company_access: fd.company_access || "all",
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    form.post("/users/new/", { forceFormData: true });
  };

  return (
    <div className="form-page shadcn-root">
      <PageBack href="/users/" />
      <FormHeader kicker={t("User")} title={t("New User")} sub={t("Create a new account")} />
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Account")}>
            <FormField label={t("Full name")} name="full_name" value={form.data.full_name} onChange={set("full_name")} error={errors.full_name} placeholder={t("Optional")} />
            <FormField label={t("Username")} name="username" required value={form.data.username} onChange={set("username")} error={errors.username} autoFocus />
            <div className="fg-2" style={{ marginTop: 12 }}>
              <FormField label={t("Password")} name="password" type="password" required value={form.data.password} onChange={set("password")} error={errors.password} />
              <FormField label={t("Confirm Password")} name="password_confirm" type="password" required value={form.data.password_confirm} onChange={set("password_confirm")} error={errors.password_confirm} />
            </div>
          </FormSection>

          <FormSection label={t("Access")}>
            <FormField label={t("Role")} name="role" hint={roleHint[form.data.role]} error={errors.role}>
              <Select name="role" value={form.data.role} onValueChange={set("role")}>
                <SelectTrigger id="role" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {role_choices.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormField>

            <div style={{ marginTop: 12 }}>
              <FormField
                label={t("Company access")}
                name="company_access"
                hint={t("Which workspace this account may switch to.")}
                error={errors.company_access}
              >
                <Select name="company_access" value={form.data.company_access} onValueChange={set("company_access")}>
                  <SelectTrigger id="company_access" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {company_choices.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
            </div>
          </FormSection>

          <FormActions cancelHref="/users/" submitLabel={t("Create User")} processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
