import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";

export default function Form({ form_data, errors: serverErrors }) {
  const fd = form_data || {};
  const form = useForm({
    username: fd.username || "", password: "", password_confirm: "",
    is_staff: !!fd.is_staff,
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, is_staff: d.is_staff ? "on" : "" }));
    form.post("/users/new/", { forceFormData: true });
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div><div className="page-title">User Baru</div><div className="page-sub">Buat akun baru</div></div>
      </div>
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Akun">
            <FormField label="Username" name="username" required value={form.data.username} onChange={set("username")} error={errors.username} autoFocus />
            <div className="fg-2" style={{ marginTop: 12 }}>
              <FormField label="Password" name="password" type="password" required value={form.data.password} onChange={set("password")} error={errors.password} />
              <FormField label="Konfirmasi Password" name="password_confirm" type="password" required value={form.data.password_confirm} onChange={set("password_confirm")} error={errors.password_confirm} />
            </div>
            <label className="ff-check" style={{ marginTop: 12 }}>
              <input type="checkbox" checked={form.data.is_staff} onChange={(e) => form.setData("is_staff", e.target.checked)} />
              <span>Staff <span className="check-sub">Akses ke menu administrasi terbatas</span></span>
            </label>
          </FormSection>
          <FormActions cancelHref="/users/" submitLabel="Buat User" processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
