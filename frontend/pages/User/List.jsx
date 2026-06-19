import { router } from "@inertiajs/react";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";

function action(userId, fields) {
  router.post(`/users/${userId}/edit/`, fields);
}

export default function List({ users }) {
  const resetPw = (u) => {
    const pw = window.prompt(`Password baru untuk ${u.username}:`);
    if (!pw) return;
    action(u.id, { action: "reset_password", password: pw, password_confirm: pw });
  };
  const [confirm, confirmDialog] = useConfirm();
  const del = (u) => confirm({ title: "Delete user", message: `Delete user ${u.username}?`, onConfirm: () => router.post(`/users/${u.id}/delete/`) });

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div><div className="page-title">Users</div><div className="page-sub">{users.length} akun terdaftar</div></div>
        <div className="page-actions">
          <a href="/users/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            User baru
          </a>
        </div>
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="col-bold">{u.username}{u.is_self && <span className="badge badge-gray" style={{ marginLeft: 6 }}>Anda</span>}</td>
                  <td>{u.is_superuser ? <span className="badge badge-blue">Admin</span> : u.is_staff ? <span className="badge badge-green">Staff</span> : <span className="badge badge-gray">User</span>}</td>
                  <td>{u.is_active ? <span className="badge badge-green">Aktif</span> : <span className="badge badge-gray">Nonaktif</span>}</td>
                  <td className="col-m-actions" style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => resetPw(u)}>Reset PW</button>
                    {!u.is_superuser && <button className="btn btn-ghost btn-sm" onClick={() => action(u.id, { action: "toggle_staff" })}>{u.is_staff ? "Cabut Staff" : "Jadikan Staff"}</button>}
                    {!u.is_self && !u.is_superuser && <button className="btn btn-ghost btn-sm" onClick={() => action(u.id, { action: "toggle_active" })}>{u.is_active ? "Nonaktifkan" : "Aktifkan"}</button>}
                    {!u.is_self && !u.is_superuser && <button className="btn btn-danger btn-sm" onClick={() => del(u)}>Hapus</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {confirmDialog}
    </div>
  );
}
