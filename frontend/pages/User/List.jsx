import { router } from "@inertiajs/react";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import Table from "../../components/ui/Table.jsx";
import RowActions from "../../components/ui/RowActions.jsx";

function action(userId, fields) {
  router.post(`/users/${userId}/edit/`, fields);
}

export default function List({ users }) {
  const resetPw = (u) => {
    const pw = window.prompt(`New password for ${u.username}:`);
    if (!pw) return;
    action(u.id, { action: "reset_password", password: pw, password_confirm: pw });
  };
  const [confirm, confirmDialog] = useConfirm();
  const del = (u) => confirm({ title: "Delete user", message: `Delete user ${u.username}?`, onConfirm: () => router.post(`/users/${u.id}/delete/`) });

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div><div className="page-title">Users</div><div className="page-sub">{users.length} accounts registered</div></div>
        <div className="page-actions">
          <a href="/users/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            New user
          </a>
        </div>
      </div>

      <div className="card">
        <Table
          columns={[
            {
              header: "Username",
              className: "col-bold col-m-primary",
              render: (u) => (
                <>
                  {u.username}
                  {u.is_self && <span className="badge badge-gray" style={{ marginLeft: 6 }}>You</span>}
                </>
              ),
            },
            {
              header: "Status",
              className: "col-m-badge",
              render: (u) => u.is_active ? <span className="badge badge-green">Active</span> : <span className="badge badge-gray">Inactive</span>,
            },
            {
              header: "Role",
              className: "col-m-secondary",
              render: (u) => u.is_superuser ? <span className="badge badge-blue">Admin</span> : u.is_staff ? <span className="badge badge-green">Staff</span> : <span className="badge badge-gray">User</span>,
            },
            {
              header: "",
              className: "col-m-actions",
              render: (u) => (
                <RowActions actions={[
                  { icon: "key", label: "Reset Password", onClick: () => resetPw(u) },
                  !u.is_superuser && { icon: "shield", label: u.is_staff ? "Revoke Staff" : "Make Staff", onClick: () => action(u.id, { action: "toggle_staff" }) },
                  !u.is_self && !u.is_superuser && { icon: "power", label: u.is_active ? "Deactivate" : "Activate", onClick: () => action(u.id, { action: "toggle_active" }) },
                  !u.is_self && !u.is_superuser && { icon: "trash", label: "Delete", variant: "red", onClick: () => del(u) },
                ]} />
              ),
            },
          ]}
          rows={users}
          rowKey={(u) => u.id}
        />
      </div>
      {confirmDialog}
    </div>
  );
}
