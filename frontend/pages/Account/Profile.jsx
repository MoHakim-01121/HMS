import { useRef, useState } from "react";
import { router } from "@inertiajs/react";

function relTime(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  const diff = Math.floor((new Date() - dt) / 1000);
  if (diff < 60) return "Just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  if (diff < 2592000) return Math.floor(diff / 86400) + "d ago";
  return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

const joinedFmt = (iso) =>
  iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—";

const ACTION_CLASS = { create: "act-create", edit: "act-update", delete: "act-delete", login: "act-login" };

function ActivityRow({ a }) {
  const [open, setOpen] = useState(false);
  const hasChanges = Array.isArray(a.changes) && a.changes.length > 0;
  return (
    <>
      <div
        className={`afl-row${hasChanges ? " has-changes" : ""}${open ? " open" : ""}`}
        onClick={hasChanges ? () => setOpen((o) => !o) : undefined}
      >
        <span className="afl-ts">{relTime(a.timestamp)}</span>
        <span className={"afl-action " + (ACTION_CLASS[a.action] || "act-other")}>{(a.action || "").toUpperCase()}</span>
        <span className="afl-desc">
          {a.model_name && <span className="afl-model">{a.model_name} </span>}
          {a.object_ref && <span className="afl-ref">{a.object_ref}</span>}
          {!a.model_name && !a.object_ref && "—"}
        </span>
        <span className="afl-co">{a.company || "—"}</span>
        <span className="afl-chevron">
          {hasChanges && (
            <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </span>
      </div>
      {hasChanges && (
        <div className={"afl-detail" + (open ? " open" : "")}>
          {a.changes.map((ch, i) => (
            <div className="afl-ch" key={i}>
              <span className="afl-ch-label">{ch.label}</span>
              <span className="afl-ch-before">{ch.before || "—"}</span>
              <span className="afl-ch-arrow">→</span>
              <span className="afl-ch-after">{ch.after || "—"}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function Profile({ profile, account, activities }) {
  const fileRef = useRef(null);
  const badgeClass =
    account.role_badge === "Admin" ? "badge-blue" : account.role_badge === "Staff" ? "badge-green" : "badge-gray";

  const pickAvatar = (e) => {
    const file = e.target.files?.[0];
    if (file) router.post("/account/avatar/upload/", { avatar: file }, { forceFormData: true });
  };

  return (
    <div className="pf-page">
      <style>{CSS}</style>

      <button className="page-back" onClick={() => history.back()}>
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </button>

      {/* Profile header */}
      <div className="form-panel">
        <div className="pf-header">
          <div className="pf-avatar-wrap" onClick={() => fileRef.current?.click()}>
            {profile.avatar_url ? (
              <img src={profile.avatar_url} className="pf-avatar" alt="avatar" />
            ) : (
              <div className="pf-avatar pf-avatar-blank">
                <svg width="36" height="36" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="7.5" r="3.5" fill="currentColor" />
                  <path d="M3 17c0-3.866 3.134-7 7-7s7 3.134 7 7" fill="currentColor" />
                </svg>
              </div>
            )}
            <div
              className="pf-ring"
              style={{ "--ring-color": account.is_superuser ? "var(--accent)" : account.is_staff ? "var(--green)" : "var(--border-2)" }}
            />
            <span className="pf-bracket pf-tl" />
            <span className="pf-bracket pf-tr" />
            <span className="pf-bracket pf-bl" />
            <span className="pf-bracket pf-br" />
            <div className="pf-cam">
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
              </svg>
            </div>
          </div>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={pickAvatar} />

          <div className="pf-meta">
            <div className="pf-name">{account.full_name}</div>
            <div className="pf-uid-row">
              <span className="pf-uid">{account.uid}</span>
              <span className={"badge " + badgeClass}>{account.role_badge}</span>
              <span className="pf-status">
                <span
                  className="pf-status-dot"
                  style={account.is_active ? { background: "var(--green)", boxShadow: "0 0 5px var(--green)" } : { background: "var(--red)" }}
                />
                <span style={{ fontSize: 12, color: account.is_active ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {account.is_active ? "Active" : "Inactive"}
                </span>
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
              Joined {joinedFmt(account.date_joined)}
              &nbsp;·&nbsp; Last login {relTime(account.last_login)}
            </div>
          </div>
        </div>

        {/* Account info rows */}
        <div className="pf-section-label">Account Info</div>
        <div className="pf-rows">
          <div className="pf-row">
            <span className="pf-row-icon">
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0" /></svg>
            </span>
            <span className="pf-key">Username</span>
            <span className="pf-val">{account.username}</span>
          </div>

          <div className="pf-row">
            <span className="pf-row-icon">
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" /></svg>
            </span>
            <span className="pf-key">Email</span>
            <span className={"pf-val" + (account.email ? "" : " pf-empty")}>{account.email || "Not set"}</span>
          </div>

          <div className="pf-row">
            <span className="pf-row-icon">
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
            </span>
            <span className="pf-key">Clearance</span>
            <span className="pf-val">{account.role}</span>
          </div>

          <div className="pf-row" style={{ borderBottom: "none" }}>
            <span className="pf-row-icon">
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" /><path strokeLinecap="round" d="M7 11V7a5 5 0 0110 0v4" /></svg>
            </span>
            <span className="pf-key">Password</span>
            <span className="pf-val pf-empty">••••••••</span>
          </div>
        </div>
      </div>

      {/* Activity log */}
      <div className="form-panel">
        <div className="afl-head">
          <span className="afl-title">Activity Log</span>
          <span className="afl-count">{activities.length} entries</span>
        </div>
        <div className="afl-body">
          {activities.length ? (
            activities.map((a, i) => <ActivityRow a={a} key={i} />)
          ) : (
            <div className="afl-empty">No activity recorded</div>
          )}
        </div>
      </div>
    </div>
  );
}

const CSS = `
  .pf-page { max-width: 760px; margin: 0 auto; padding: 20px 16px 40px; display: flex; flex-direction: column; gap: 12px; }
  .pf-header { display: grid; grid-template-columns: auto 1fr; gap: 24px; align-items: center; padding: 24px; }
  @media (max-width: 560px) { .pf-header { grid-template-columns: 1fr; justify-items: center; text-align: center; gap: 16px; } }
  .pf-avatar-wrap { position: relative; width: 80px; height: 80px; cursor: pointer; flex-shrink: 0; }
  .pf-avatar { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; display: block; }
  .pf-avatar-blank { width: 80px; height: 80px; border-radius: 50%; background: var(--surface-2); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; color: var(--text-3); }
  .pf-ring { position: absolute; inset: -4px; border-radius: 50%; border: 1.5px solid var(--ring-color, var(--border-2)); pointer-events: none; }
  .pf-bracket { position: absolute; width: 9px; height: 9px; }
  .pf-tl { top:-7px; left:-7px; border-top:2px solid var(--accent); border-left:2px solid var(--accent); }
  .pf-tr { top:-7px; right:-7px; border-top:2px solid var(--accent); border-right:2px solid var(--accent); }
  .pf-bl { bottom:-7px; left:-7px; border-bottom:2px solid var(--accent); border-left:2px solid var(--accent); }
  .pf-br { bottom:-7px; right:-7px; border-bottom:2px solid var(--accent); border-right:2px solid var(--accent); }
  .pf-cam { position: absolute; inset: 0; border-radius: 50%; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; color: #fff; opacity: 0; transition: opacity .15s; }
  .pf-avatar-wrap:hover .pf-cam { opacity: 1; }
  .pf-meta { display: flex; flex-direction: column; gap: 6px; }
  .pf-name { font-size: 18px; font-weight: 700; color: var(--text); line-height: 1.2; }
  .pf-uid-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .pf-uid { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: var(--text-3); letter-spacing: .5px; }
  .pf-rows { padding: 0; }
  .pf-row { display: grid; grid-template-columns: 16px 110px 1fr; align-items: center; gap: 12px; padding: 11px 20px; border-bottom: 1px solid var(--border); }
  .pf-row:last-child { border-bottom: none; }
  .pf-row-icon { color: var(--text-3); display: flex; align-items: center; }
  .pf-key { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .7px; color: var(--text-3); }
  .pf-val { font-size: 13px; font-weight: 500; color: var(--text); }
  .pf-empty { color: var(--text-3); }
  .pf-status { display: flex; align-items: center; gap: 7px; }
  .pf-status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .afl-head { display: flex; align-items: center; justify-content: space-between; padding: 11px 20px; border-bottom: 1px solid var(--border); }
  .afl-title { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .7px; color: var(--text-3); }
  .afl-count { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-3); }
  .afl-body { max-height: 340px; overflow-y: auto; }
  .afl-row { display: grid; grid-template-columns: 80px 48px 1fr 52px 16px; align-items: center; gap: 10px; padding: 8px 20px; border-bottom: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: 11px; cursor: default; transition: background .1s; }
  .afl-row:last-child { border-bottom: none; }
  .afl-row.has-changes { cursor: pointer; }
  .afl-row.has-changes:hover { background: var(--surface-2); }
  .afl-ts { color: var(--text-3); white-space: nowrap; }
  .afl-action { font-weight: 700; }
  .afl-action.act-create { color: var(--green); }
  .afl-action.act-update { color: var(--yellow); }
  .afl-action.act-delete { color: var(--red); }
  .afl-action.act-login { color: var(--accent-2); }
  .afl-action.act-other { color: var(--text-2); }
  .afl-desc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); font-size: 10.5px; }
  .afl-model { color: var(--text-3); }
  .afl-ref { color: var(--text); }
  .afl-co { color: var(--text-3); font-size: 10px; text-align: right; }
  .afl-chevron { color: var(--text-3); display: flex; align-items: center; justify-content: center; transition: transform .15s; }
  .afl-row.open .afl-chevron { transform: rotate(180deg); }
  .afl-detail { display: none; background: var(--surface-2); border-bottom: 1px solid var(--border); padding: 8px 20px 10px calc(20px + 80px + 48px + 20px); font-family: 'JetBrains Mono', monospace; font-size: 10.5px; }
  .afl-detail.open { display: block; }
  .afl-ch { display: flex; align-items: baseline; gap: 8px; line-height: 1.9; }
  .afl-ch-label { color: var(--text-3); min-width: 90px; flex-shrink: 0; }
  .afl-ch-before { color: var(--red); text-decoration: line-through; opacity: .7; }
  .afl-ch-arrow { color: var(--text-3); flex-shrink: 0; }
  .afl-ch-after { color: var(--green); }
  .afl-empty { padding: 24px; text-align: center; color: var(--text-3); font-size: 12px; }
  .pf-section-label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .7px; color: var(--text-3); padding: 11px 20px 8px; border-bottom: 1px solid var(--border); }
`;
