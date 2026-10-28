import { useState } from "react";
import axios from "axios";
import { Link, router } from "@inertiajs/react";
import { ListPage, Toolbar, Primary, TableCard, PRow, RowMenu, Pill, Tr, Th, Td, Note, ToolButton } from "../../components/shadcn/list-a.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
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
import BranchField from "./BranchField.jsx";

function action(userId, fields) {
  router.post(`/users/${userId}/edit/`, fields, { forceFormData: true });
}

// The role decides what this account can do, the branch on whose records;
// the server applies both in the 'set_access' action.
function AccessDialog({ user, roleChoices, branchChoices, onClose }) {
  const { t } = useI18n();
  const [role, setRole] = useState(user?.role ?? "staff");
  const [branch, setBranch] = useState(user?.branch || "all");
  if (!user) return null;

  // The hint under the role picker is the role's own description, so a custom
  // role explains itself here without a second copy in the client.
  const roleHint = roleChoices.find((c) => c.value === role)?.description || "";

  const save = () => {
    action(user.id, { action: "set_access", role, branch: role === "admin" ? "all" : branch });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent>
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
          <BranchField role={role} value={branch} onChange={setBranch} choices={branchChoices} />
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
      <DialogContent>
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
      <DialogContent>
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

export default function List({ users, role_choices = [], branch_choices = [] }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const del = (u) => confirm({ title: t("Delete user"), message: t("Delete user {name}?", { name: u.username }), onConfirm: () => router.post(`/users/${u.id}/delete/`) });
  const openForm = useFormModal();
  const [accessUser, setAccessUser] = useState(null);
  const [resetUser, setResetUser] = useState(null);
  const [cardUser, setCardUser] = useState(null);
  const branchLabel = Object.fromEntries(branch_choices.map((c) => [c.value, c.label]));
  const active = users.filter((u) => u.is_active).length;

  // The row's actions: the desktop row menu, and the same menu on a phone row.
  const menuFor = (u) => [
    { label: t("Edit"), onClick: () => openForm(`/users/${u.id}/edit/`) },
    // Changing your own role would revoke the permission needed
    // to change it back; the server refuses it too.
    !u.is_self && { label: t("Manage access"), onClick: () => setAccessUser(u) },
    { label: t("Reset password"), onClick: () => setResetUser(u) },
    { label: t("Credential card"), onClick: () => setCardUser(u) },
    !u.is_self && !u.is_superuser && { label: u.is_active ? t("Deactivate") : t("Activate"), onClick: () => action(u.id, { action: "toggle_active" }) },
    !u.is_self && !u.is_superuser && { label: t("Delete"), danger: true, onClick: () => del(u) },
  ];
  return (
    <ListPage title={t("Users")}>
      <Toolbar left={<Note>{t("{n} accounts, {a} active", { n: users.length, a: active })}</Note>}>
        <ToolButton as={Link} href="/roles/">{t("Roles")}</ToolButton>
        <Primary label={t("New user")} onClick={() => openForm("/users/new/")} onPrefetch={() => openForm.prefetch("/users/new/")} />
      </Toolbar>

      <TableCard cols={[200, null, 110, 160, 200, 56]}
        phone={users.map((u) => (
          <PRow key={u.id} menu={<RowMenu label={t("Actions for {n}", { n: u.username })} items={menuFor(u)} />} onClick={() => openForm(`/users/${u.id}/edit/`)} no={u.is_self ? `${u.username} (${t("You")})` : u.username} dim={!u.is_active}
            tag={<Pill tone={u.is_active ? "green" : "gray"} sm>{u.is_active ? t("Active") : t("Inactive")}</Pill>}
            meta={[u.full_name, u.branch === "all" ? t("All branches") : u.branch.split(",").map((code) => branchLabel[code] || code).join(", ")].filter(Boolean).join(" · ")}
            note={u.role_label} />
        ))}>
        <thead><Tr>
          <Th>{t("Username")}</Th><Th>{t("Name")}</Th><Th>{t("Status")}</Th><Th>{t("Role")}</Th><Th>{t("Branch")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {users.map((u) => (
            <Tr key={u.id} row={u.is_active ? undefined : "dim"} onClick={() => openForm(`/users/${u.id}/edit/`)}>
              <Td><span className="font-medium">{u.username}</span>{u.is_self && <> <Pill tone="gray" sm>{t("You")}</Pill></>}</Td>
              <Td className="truncate">{u.full_name}</Td>
              <Td><Pill tone={u.is_active ? "green" : "gray"}>{u.is_active ? t("Active") : t("Inactive")}</Pill></Td>
              <Td>{u.role_label}</Td>
              <Td className="truncate">{u.branch === "all" ? t("All branches") : u.branch.split(",").map((code) => branchLabel[code] || code).join(", ")}</Td>
              <Td className="text-center">
                <RowMenu label={t("Actions for {n}", { n: u.username })} items={menuFor(u)} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>
      <AccessDialog
        key={`access-${accessUser?.id ?? "none"}`}
        user={accessUser}
        roleChoices={role_choices}
        branchChoices={branch_choices}
        onClose={() => setAccessUser(null)}
      />
      <ResetPasswordDialog user={resetUser} onClose={() => setResetUser(null)} />
      <CredentialCardDialog key={`card-${cardUser?.id ?? "none"}`} user={cardUser} onClose={() => setCardUser(null)} />
      {confirmDialog}
    </ListPage>
  );
}
