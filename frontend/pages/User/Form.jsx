import { useState } from "react";
import { router, useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { FormA, Field, Picker, ReadOnly, TextIn, Foot, FA, Caption, btnClass, SettingRow, SwitchRow } from "../../components/shadcn/form-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";

// New and edit user, the "User Form" artboard on the Record View HMS canvas:
// who the account is, its role and branch, its password (set on create,
// reset on edit) and whether it is active, saved together. An administrator
// always covers every branch; no one changes their own role or deactivates
// themselves.
function FormBody({ edit = null, form_data, errors: serverErrors, role_choices = [], branch_choices = [] }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const fd = form_data || {};
  const form = useForm({
    username: fd.username || "", full_name: fd.full_name || "",
    password: "", password_confirm: "",
    role: fd.role || "staff",
    branch: fd.branch || "all",
    is_active: fd.is_active !== false,
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);
  const errors = { ...serverErrors, ...form.errors };
  const [resetting, setResetting] = useState(!edit || !!errors.password || !!errors.password_confirm);
  const isSelf = !!edit?.is_self;
  const canEditUsername = !edit || !!edit.can_edit_username;
  const admin = d.role === "admin";
  const err = (k) => (errors[k] ? t(errors[k]) : null);
  const roleHint = role_choices.find((c) => c.value === d.role)?.description || "";

  const mismatch = d.password && d.password_confirm && d.password !== d.password_confirm;
  const why = !d.full_name.trim() ? t("Enter the full name.")
    : canEditUsername && !d.username.trim() ? t(edit ? "Username is required." : "Choose a username.")
      : !edit && !d.password ? t("Set a password.")
        : resetting && edit && !d.password ? t("Type the new password, or keep the current one.")
          : resetting && d.password && !d.password_confirm ? t("Confirm the password.")
            : mismatch ? t("Passwords do not match.")
              : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    if (edit) {
      form.transform((x) => ({
        action: "save", username: canEditUsername ? x.username : edit.username,
        full_name: x.full_name, role: x.role, branch: admin ? "all" : x.branch,
        password: resetting ? x.password : "", password_confirm: resetting ? x.password_confirm : "",
        is_active: x.is_active ? "on" : "",
      }));
      form.post(`/users/${edit.id}/edit/`, { forceFormData: true });
    } else {
      form.transform((x) => ({ ...x, branch: admin ? "all" : x.branch }));
      form.post("/users/new/", { forceFormData: true });
    }
  };

  const del = () => confirm({
    title: t("Delete user"),
    message: t("Delete {name}? Accounts that recorded financial documents cannot be deleted; deactivate them instead.", { name: edit.username }),
    danger: true,
    onConfirm: () => router.post(`/users/${edit.id}/delete/`),
  });

  return (
    <FormA title={edit ? edit.username : t("New User")} onSubmit={submit}>
      <div className={FA.fields}>
        <Field label={t("Full name")} required error={err("full_name")}>
          <TextIn value={d.full_name} onChange={set("full_name")} placeholder={t("Enter the full name.")} autoFocus
            invalid={!!errors.full_name} suffix={isSelf ? <span className={FA.newTag}>{t("You")}</span> : null} />
        </Field>
        <Field label={t("Username")} required={!edit || canEditUsername} error={err("username")}
          hint={!canEditUsername ? t("Username cannot be changed.")
            : edit ? t("You sign in with this. Use the new one the next time you sign in.") : null}>
          {canEditUsername
            ? <TextIn value={d.username} onChange={set("username")} placeholder={t("Username")} autoComplete="off" invalid={!!errors.username} />
            : <ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{d.username}</span></ReadOnly>}
        </Field>
        <Field label={t("Role")} required error={err("role")} hint={isSelf ? t("You cannot change your own role.") : roleHint || null}>
          <Picker searchable={false} value={d.role} heading={t("Role")}
            options={role_choices.map((c) => ({ value: c.value, label: c.label, meta: c.description || "" }))}
            onPick={(o) => !isSelf && form.setData("role", o.value)} />
        </Field>
        <Field label={t("Branch")} required error={err("branch")} hint={admin ? t("An administrator always covers every branch.") : null}>
          <Picker searchable={false} value={admin ? "all" : d.branch} heading={t("Branch")}
            options={branch_choices.map((c) => ({ value: c.value, label: c.value === "all" ? t("All branches") : c.label }))}
            onPick={(o) => !admin && !isSelf && form.setData("branch", o.value)} />
        </Field>
      </div>

      <div className={FA.sectionHead}><Caption>{t("Password")}</Caption></div>
      {edit && !resetting ? (
        <SettingRow title={t("Password is set")} note={t("Reset it when the user forgets it. They sign in with the new one right away.")}>
          <button type="button" className={btnClass("o", true)} onClick={() => setResetting(true)}>{t("Reset password")}</button>
        </SettingRow>
      ) : (
        <div className={FA.fields}>
          <Field label={edit ? t("New password") : t("Password")} required error={err("password")}>
            <TextIn type="password" value={d.password} onChange={set("password")} autoComplete="new-password" invalid={!!errors.password} />
          </Field>
          <Field label={t("Confirm password")} required error={mismatch ? t("Passwords do not match.") : err("password_confirm")}>
            <TextIn type="password" value={d.password_confirm} onChange={set("password_confirm")} autoComplete="new-password" invalid={!!mismatch || !!errors.password_confirm} />
          </Field>
          {edit ? (
            <div className={FA.wide}><button type="button" className={FA.textBtn} onClick={() => { setResetting(false); form.setData((x) => ({ ...x, password: "", password_confirm: "" })); }}>{t("Keep current password")}</button></div>
          ) : null}
        </div>
      )}

      {edit ? (
        <>
          <div className={FA.sectionHead}><Caption>{t("Account")}</Caption></div>
          <SwitchRow title={t("Active")} note={isSelf ? t("You cannot deactivate your own account.") : edit.is_superuser ? t("A superuser stays active.") : t("An inactive user cannot sign in.")}
            checked={d.is_active} aria-label={t("Active")} disabled={isSelf || edit.is_superuser} onCheckedChange={(v) => form.setData("is_active", v)} />
          {err("is_active") ? <div className={FA.alert} role="alert">{err("is_active")}</div> : null}
        </>
      ) : null}

      <Foot why={why} cancelHref="/users/" submitLabel={edit ? t("Save changes") : t("Create user")} processing={form.processing}
        extra={edit && !isSelf && !edit.is_superuser ? <button type="button" className={cn(FA.textBtn, "order-first mr-auto text-danger-text hover:text-danger-text")} onClick={del}>{t("Delete user")}</button> : null} />
      {confirmDialog}
    </FormA>
  );
}

export default withStandaloneModal(FormBody, "/users/");
