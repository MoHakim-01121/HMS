import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
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
          <p className="col-dim">{t("No accounts use this role. It will be removed.")}</p>
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
    <div className="page shadcn-root">
      <PageBack href="/users/" />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Roles")}</div>
          <div className="page-sub">
            {t("{count} roles across {modules} modules", { count: roles.length, modules: modules.length })}
          </div>
        </div>
        <div className="page-actions">
          <Link href="/roles/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            {t("New role")}
          </Link>
        </div>
      </div>

      <div className="card">
        <Table
          columns={[
            {
              header: t("Role"),
              className: "col-bold col-m-primary",
              render: (r) => (
                <>
                  {r.label}
                  {r.locked && <span className="badge badge-blue" style={{ marginLeft: 6 }}>{t("Locked")}</span>}
                  {!r.locked && r.is_system && <span className="badge badge-gray" style={{ marginLeft: 6 }}>{t("Built-in")}</span>}
                  {r.slug === current_role && <span className="badge badge-gray" style={{ marginLeft: 6 }}>{t("Yours")}</span>}
                </>
              ),
            },
            {
              header: t("Description"),
              className: "col-m-secondary",
              // Capped: an unbounded description column pushes the row-actions
              // column past the card's right edge.
              render: (r) => (
                <span
                  className="col-dim block truncate max-w-[340px]"
                  title={r.description || ""}
                >
                  {r.description || t("—")}
                </span>
              ),
            },
            {
              header: t("Permissions"),
              className: "col-m-secondary",
              render: (r) => {
                const { modules: m, grants } = summarise(r.permissions);
                return <span className="col-dim">{t("{m} modules · {grants} permissions", { m, grants })}</span>;
              },
            },
            {
              header: t("Accounts"),
              className: "col-m-badge",
              render: (r) => <span className="badge badge-gray">{r.user_count}</span>,
            },
            {
                header: "",
                className: "col-m-actions",
                render: (r) => (
                  <RowActions actions={[
                    // The Administrator row is shown for reference but never
                    // editable — it is the account that could undo a bad edit.
                    !r.locked && r.slug !== current_role && {
                      icon: "edit", label: t("Edit permissions"),
                      onClick: () => router.visit(`/roles/${r.slug}/edit/`),
                    },
                    !r.is_system && r.slug !== current_role && {
                      icon: "trash", label: t("Delete"), variant: "red",
                      onClick: () => setDeleting(r),
                    },
                  ]} />
                ),
            },
          ]}
          rows={roles}
          rowKey={(r) => r.slug}
        />
      </div>

      <DeleteDialog role={deleting} roles={roles} onClose={() => setDeleting(null)} />
    </div>
  );
}
