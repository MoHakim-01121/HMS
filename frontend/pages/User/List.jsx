import { useState } from "react";
import axios from "axios";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

function action(userId, fields) {
  router.post(`/users/${userId}/edit/`, fields, { forceFormData: true });
}

const ROLE_TONE = {
  admin: "badge-blue",
  manager: "badge-green",
  staff: "badge-gray",
  viewer: "badge-yellow",
};

// Role + company access live in one dialog: they are the two halves of "what
// this account can reach", and the server applies them in a single action.
function AccessDialog({ user, roleChoices, companyChoices, onClose }) {
  const { t } = useI18n();
  const [role, setRole] = useState(user?.role ?? "staff");
  const [companyAccess, setCompanyAccess] = useState(user?.company_access ?? "all");
  if (!user) return null;

  // The hint under the role picker is the role's own description, so a custom
  // role explains itself here without a second copy in the client.
  const roleHint = roleChoices.find((c) => c.value === role)?.description || "";

  const save = () => {
    action(user.id, { action: "set_access", role, company_access: companyAccess });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="hms-dialog">
        <DialogHeader>
          <DialogTitle>{t("Access for {name}", { name: user.username })}</DialogTitle>
          <DialogDescription>
            {t("Choose what {name} may reach across the system.", { name: user.username })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <FormField label={t("Role")} name="role" hint={roleHint}>
            <Select name="role" value={role} onValueChange={setRole}>
              <SelectTrigger id="role" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roleChoices.map((c) => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>

          <FormField
            label={t("Company access")}
            name="company_access"
            hint={t("Which workspace this account may switch to.")}
          >
            <Select name="company_access" value={companyAccess} onValueChange={setCompanyAccess}>
              <SelectTrigger id="company_access" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {companyChoices.map((c) => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>{t("Cancel")}</Button>
          <Button type="button" onClick={save}>{t("Save access")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Mirrors the server's reset_password branch: password + password_confirm, with
// the same two client-side checks (non-empty, matching) so a mismatch is caught
// before the round trip instead of as a flash toast.
function ResetPasswordDialog({ user, onClose }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  if (!user) return null;

  const save = () => {
    if (!password) return setError("New password is required.");
    if (password !== confirm) return setError("Passwords do not match.");
    action(user.id, { action: "reset_password", password, password_confirm: password });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="hms-dialog">
        <DialogHeader>
          <DialogTitle>{t("Reset password")}</DialogTitle>
          <DialogDescription>
            {t("Set a new password for {name}. It takes effect immediately.", { name: user.username })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <FormField label={t("New password")} name="password">
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              autoFocus
              value={password}
              onChange={(e) => { setPassword(e.target.value); if (error) setError(""); }}
            />
          </FormField>

          <FormField label={t("Confirm password")} name="password_confirm">
            <Input
              id="password_confirm"
              name="password_confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => { setConfirm(e.target.value); if (error) setError(""); }}
            />
          </FormField>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
              {t(error)}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>{t("Cancel")}</Button>
          <Button type="button" onClick={save}>{t("Reset password")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Print a credential card: the admin types the password that goes on the
// card (the stored hash is one-way, so the real one can never be shown).
// The account's password is never changed.
function CredentialCardDialog({ user, onClose }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  const download = async () => {
    if (!password) return setError("Password is required to print the card.");
    setBusy(true);
    setError("");
    try {
      const res = await axios.post(
        `/users/${user.id}/credential-card/`,
        new URLSearchParams({ password, password_confirm: password }),
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      onClose();
    } catch (err) {
      let msg = "Failed to generate the credential card.";
      const blob = err.response?.data;
      if (blob instanceof Blob) {
        try { msg = JSON.parse(await blob.text()).error || msg; } catch { /* not JSON */ }
      } else if (err.response?.data?.error) {
        msg = err.response.data.error;
      }
      setError(msg);
    } finally {
      // Always clear the spinner — the tab switch can delay React's flush
      // (or the dialog may be re-opened before the unmount lands), leaving
      // busy stuck on "Generating…" otherwise.
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="hms-dialog">
        <DialogHeader>
          <DialogTitle>{t("Print credential card")}</DialogTitle>
          <DialogDescription>
            {t("Type the password to print on the card for {name}. This does not change the account password.", { name: user.username })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <FormField label={t("Username")} name="cred_username">
            <div className="flex h-[40px] items-center rounded-[16px] border-2 border-input bg-card px-[14px] text-[14px]">{user.username}</div>
          </FormField>

          <FormField label={t("Confirm password")} name="password">
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="off"
              autoFocus
              value={password}
              onChange={(e) => { setPassword(e.target.value); if (error) setError(""); }}
            />
          </FormField>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
              {t(error)}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>{t("Cancel")}</Button>
          <Button type="button" onClick={download} disabled={busy}>
            {busy ? t("Generating…") : t("Download PDF")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function List({ users, role_choices = [], company_choices = [] }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const del = (u) => confirm({ title: t("Delete user"), message: t("Delete user {name}?", { name: u.username }), onConfirm: () => router.post(`/users/${u.id}/delete/`) });
  const openForm = useFormModal();
  const [accessUser, setAccessUser] = useState(null);
  const [resetUser, setResetUser] = useState(null);
  const [cardUser, setCardUser] = useState(null);

  return (
    <div className="page shadcn-root">
      <PageBack />
      <div className="page-header">
        <div><div className="page-title">{t("Users")}</div><div className="page-sub">{t("{count} accounts registered", { count: users.length })}</div></div>
        <div className="page-actions">
          <button type="button" onClick={() => openForm("/users/new/")} onPointerEnter={() => openForm.prefetch("/users/new/")} onFocus={() => openForm.prefetch("/users/new/")} className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            {t("New user")}
          </button>
        </div>
      </div>

      <div className="card">
        <Table
          columns={[
            {
              header: t("Username"),
              className: "col-bold col-m-primary",
              render: (u) => (
                <>
                  {u.username}
                  {u.is_self && <span className="badge badge-gray" style={{ marginLeft: 6 }}>{t("You")}</span>}
                </>
              ),
            },
            {
              header: t("Name"),
              className: "col-m-secondary",
              render: (u) => u.full_name,
            },
            {
              header: t("Status"),
              className: "col-m-badge",
              render: (u) => u.is_active ? <span className="badge badge-green">{t("Active")}</span> : <span className="badge badge-gray">{t("Inactive")}</span>,
            },
            {
              header: t("Role"),
              className: "col-m-secondary",
              render: (u) => (
                <span className={"badge " + (ROLE_TONE[u.role] || "badge-gray")}>{u.role_label}</span>
              ),
            },
            {
              header: t("Company"),
              className: "col-m-secondary",
              render: (u) => (
                <span className="col-dim">{u.company_access_label}</span>
              ),
            },
            {
              header: "",
              className: "col-m-actions",
              render: (u) => (
                <RowActions actions={[
                  { icon: "pdf", label: t("Credential card"), variant: "green", onClick: () => setCardUser(u) },
                  { icon: "key", label: t("Reset Password"), onClick: () => setResetUser(u) },
                  // Changing your own role would revoke the permission needed
                  // to change it back — the server refuses it too.
                  !u.is_self && { icon: "shield", label: t("Manage access"), onClick: () => setAccessUser(u) },
                  !u.is_self && !u.is_superuser && { icon: "power", label: u.is_active ? t("Deactivate") : t("Activate"), onClick: () => action(u.id, { action: "toggle_active" }) },
                  !u.is_self && !u.is_superuser && { icon: "trash", label: t("Delete"), variant: "red", onClick: () => del(u) },
                ]} />
              ),
            },
          ]}
          rows={users}
          rowKey={(u) => u.id}
        />
      </div>
      <AccessDialog
        user={accessUser}
        roleChoices={role_choices}
        companyChoices={company_choices}
        onClose={() => setAccessUser(null)}
      />
      <ResetPasswordDialog user={resetUser} onClose={() => setResetUser(null)} />
      <CredentialCardDialog key={cardUser?.id ?? "none"} user={cardUser} onClose={() => setCardUser(null)} />
      {confirmDialog}
    </div>
  );
}
