import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import {
  ListPage, Toolbar, Primary, TableCard, RowMenu, Pill, rowNav,
} from "../../components/shadcn/list-a.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

/** "6 modules · 24 permissions" — enough to tell two roles apart at a glance. */
function summarise(permissions) {
  const modules = Object.keys(permissions || {}).filter((m) => permissions[m]?.length);
  const grants = modules.reduce((n, m) => n + permissions[m].length, 0);
  return { modules: modules.length, grants };
}

// Deleting a role has to move its members somewhere, so the confirmation and
// the destination picker are the same step — never delete first, ask later.
function DeleteDialog({ role, roles, onClose }) {
  const { t } = useI18n();
  const others = roles.filter((r) => r.slug !== role?.slug);
  const [target, setTarget] = useState(others[0]?.slug ?? "staff");
  if (!role) return null;

  const confirm = () => {
    router.post(`/roles/${role.slug}/delete/`, { reassign_to: target }, { forceFormData: true });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="hms-dialog">
        <DialogHeader>
          <DialogTitle>{t("Delete {label}", { label: role.label })}</DialogTitle>
        </DialogHeader>

        {role.user_count > 0 ? (
          <div className="form-field">
            <label className="form-label" htmlFor="reassign-to">
              {t("{count} account(s) use this role. Move them to:", { count: role.user_count })}
            </label>
            <select
              id="reassign-to"
              className="form-input"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              {others.map((r) => (
                <option key={r.slug} value={r.slug}>{r.label}</option>
              ))}
            </select>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t("No accounts use this role. It will be removed.")}</p>
        )}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>{t("Cancel")}</Button>
          <Button type="button" variant="destructive" onClick={confirm}>{t("Delete role")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function List({ roles = [], modules = [], current_role }) {
  const { t } = useI18n();
  const [deleting, setDeleting] = useState(null);

  return (
    <ListPage title={t("Roles")}>
      <Toolbar left={<span className="la-note">{t("{count} roles across {modules} modules", { count: roles.length, modules: modules.length })}</span>}>
        <Link className="la-tool" href="/users/">{t("Users")}</Link>
        <Primary label={t("New role")} href="/roles/new/" />
      </Toolbar>

      <TableCard cols={[260, null, 220, 100, 56]}>
        <thead><tr>
          <th>{t("Role")}</th><th>{t("Description")}</th><th>{t("Permissions")}</th><th className="n">{t("Accounts")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {roles.map((r) => {
            const { modules: m, grants } = summarise(r.permissions);
            // The Administrator row is shown for reference but never editable:
            // it is the account that could undo a bad edit.
            const editable = !r.locked && r.slug !== current_role;
            return (
              <tr key={r.slug} className={editable ? "" : "static"} {...(editable ? rowNav(`/roles/${r.slug}/edit/`) : {})}>
                <td>
                  <span className="strong">{r.label}</span>
                  {r.locked && <> <Pill tone="outline" sm>{t("Locked")}</Pill></>}
                  {!r.locked && r.is_system && <> <Pill tone="gray" sm>{t("Built-in")}</Pill></>}
                  {r.slug === current_role && <> <Pill tone="gray" sm>{t("Yours")}</Pill></>}
                </td>
                <td className="ell mut" title={r.description || ""}>{r.description || "–"}</td>
                <td className="mut">{t("{m} modules · {grants} permissions", { m, grants })}</td>
                <td className={"n" + (r.user_count ? "" : " zero")}>{r.user_count}</td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: r.label })} items={[
                    editable && { label: t("Edit permissions"), onClick: () => router.visit(`/roles/${r.slug}/edit/`) },
                    !r.is_system && r.slug !== current_role && { label: t("Delete"), danger: true, onClick: () => setDeleting(r) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <DeleteDialog role={deleting} roles={roles} onClose={() => setDeleting(null)} />
    </ListPage>
  );
}
