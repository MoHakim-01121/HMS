import { useMemo, useState } from "react";
import { router, useForm } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import AvatarUploader from "../../components/shadcn/avatar-uploader.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

function relTime(iso, t) {
  if (!iso) return "";
  const dt = new Date(iso);
  const diff = Math.floor((new Date() - dt) / 1000);
  if (diff < 60) return t("Just now");
  if (diff < 3600) return t("{m} min ago", { m: Math.floor(diff / 60) });
  if (diff < 86400) return t("{h} hours ago", { h: Math.floor(diff / 3600) });
  if (diff < 2592000) return t("{d} days ago", { d: Math.floor(diff / 86400) });
  return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

const clockTime = (iso) =>
  iso
    ? new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";

const ACTION_BADGE = { create: "badge-green", edit: "badge-yellow", delete: "badge-red" };
const actionLabel = (a, t) => (a ? t(a[0].toUpperCase() + a.slice(1)) : t("Other"));

const ROLE_BADGE = { admin: "badge-blue", manager: "badge-green", staff: "badge-gray", viewer: "badge-yellow" };

const TIME_RANGES = [
  { value: "all", label: "All activity" },
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

// Preset ranges and explicit From/To dates share one entry point; the date
// fields take precedence over the preset when either is filled.
function inTimeRange(timestamp, range, from, to) {
  const t = new Date(timestamp);
  if (from || to) {
    if (from && t < new Date(from + "T00:00:00")) return false;
    if (to && t > new Date(to + "T23:59:59.999")) return false;
    return true;
  }
  if (range === "all") return true;
  const start = new Date();
  if (range === "today") start.setHours(0, 0, 0, 0);
  else if (range === "7d") start.setDate(start.getDate() - 7);
  else if (range === "30d") start.setDate(start.getDate() - 30);
  return t >= start;
}

// Account settings rows: title + description in the left 4/10, the control in
// the right 6/10, separated from its neighbours by a hairline — the account
// settings shape, rendered with the app's own tokens (FormSection-style title,
// .col-dim description, hairline border).
function SectionRow({ title, description, children }) {
  const { t } = useI18n();
  return (
    <div className="grid grid-cols-1 gap-x-10 gap-y-3 md:grid-cols-10" style={{ padding: "24px 20px" }}>
      <div className="md:col-span-4">
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--foreground)" }}>{t(title)}</div>
        {description ? <div className="col-dim" style={{ fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>{t(description)}</div> : null}
      </div>
      <div className="md:col-span-6">{children}</div>
    </div>
  );
}

const Hairline = () => <div style={{ borderTop: "1px solid var(--border)" }} />;

function ActivityRow({ a, open, onToggle, t }) {
  const hasChanges = Array.isArray(a.changes) && a.changes.length > 0;
  return (
    <div>
      <button
        type="button"
        onClick={hasChanges ? onToggle : undefined}
        className={
          "flex w-full items-center gap-3 border-0 bg-transparent text-left text-sm transition-colors" +
          (hasChanges ? " cursor-pointer hover:bg-secondary/50" : " cursor-default")
        }
        style={{ padding: "10px 20px" }}
      >
        <Icon
          name="chevron"
          size={14}
          strokeWidth={2}
          className={
            "shrink-0 text-muted-foreground transition-transform duration-200" +
            (hasChanges ? (open ? " rotate-180" : "") : " opacity-0")
          }
        />
        <span className={"badge " + (ACTION_BADGE[a.action] || "badge-gray")}>{actionLabel(a.action, t)}</span>
        <p className="min-w-0 flex-1 truncate text-muted-foreground">
          {[a.model_name, a.object_ref].filter(Boolean).join(" ") || t("No details")}
        </p>
        <span className="col-bold shrink-0 truncate" style={{ maxWidth: 160 }}>{a.company}</span>
        <time className="shrink-0 text-xs tabular-nums text-muted-foreground" title={clockTime(a.timestamp)}>
          {relTime(a.timestamp, t)}
        </time>
      </button>
      {hasChanges && open ? (
        <div style={{ borderTop: "1px solid var(--border)", background: "var(--muted)", padding: "12px 20px 14px 36px" }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--muted-foreground)", marginBottom: 8 }}>{t("Changes")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {a.changes.map((ch, i) => (
              <div key={i} className="flex flex-wrap items-baseline gap-2" style={{ fontSize: 12 }}>
                <span className="w-24 shrink-0 text-muted-foreground">{t(ch.label)}</span>
                <span style={{ color: "var(--red)", textDecoration: "line-through", opacity: 0.7 }}>{ch.before}</span>
                <Icon name="arrow-right" size={10} strokeWidth={2} className="text-muted-foreground" />
                <span style={{ color: "var(--green)" }}>{ch.after}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FilterChips({ title, options, selected, onToggle, format = (v) => v, t }) {
  if (options.length < 2) return null;
  return (
    <div>
      <div className="col-dim" style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>{t(title)}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {options.map((opt) => {
          const active = selected.includes(opt);
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onToggle(opt)}
              aria-pressed={active}
              className={"badge " + (active ? "badge-blue" : "badge-gray")}
              style={{ cursor: "pointer", padding: "4px 10px", fontSize: 11 }}
            >
              <span>{t(format(opt))}</span>
              {active ? <Icon name="check" size={10} strokeWidth={2.5} /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// Search + toggle filter chips + expandable rows, on the app's own card
// surface with system tokens (badges, col-dim, muted detail strip) — the
// filter-bar chip idiom in place of the reference's slide-in panel.
function ActivityLog({ activities }) {
  const { t } = useI18n();
  const withId = useMemo(() => activities.map((a, i) => ({ ...a, _id: i })), [activities]);
  const [q, setQ] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [actionFilter, setActionFilter] = useState([]);
  const [companyFilter, setCompanyFilter] = useState([]);
  const [range, setRange] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const actionOptions = useMemo(() => Array.from(new Set(withId.map((a) => a.action).filter(Boolean))), [withId]);
  const companyOptions = useMemo(() => Array.from(new Set(withId.map((a) => a.company).filter(Boolean))), [withId]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return withId.filter((a) => {
      const hay = `${a.model_name || ""} ${a.object_ref || ""} ${a.company || ""}`.toLowerCase();
      const matchQ = !query || hay.includes(query);
      const matchAction = actionFilter.length === 0 || actionFilter.includes(a.action);
      const matchCo = companyFilter.length === 0 || companyFilter.includes(a.company);
      const matchDate = inTimeRange(a.timestamp, range, dateFrom, dateTo);
      return matchQ && matchAction && matchCo && matchDate;
    });
  }, [withId, q, actionFilter, companyFilter, range, dateFrom, dateTo]);

  const toggle = (list, setList, value) => setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  const activeFilters = actionFilter.length + companyFilter.length + (range !== "all" ? 1 : 0) + (dateFrom || dateTo ? 1 : 0);
  const clearFilters = () => {
    setActionFilter([]);
    setCompanyFilter([]);
    setRange("all");
    setDateFrom("");
    setDateTo("");
  };

  return (
    <div style={{ background: "var(--card)", borderRadius: "var(--radius-card)", marginTop: 20 }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--foreground)" }}>Activity Log</div>
          <div className="col-dim" style={{ fontSize: 12, marginTop: 2 }}>
            {filtered.length} of {activities.length} entries
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="relative" style={{ width: 260, maxWidth: "100%" }}>
            <Icon
              name="search"
              size={14}
              strokeWidth={2}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              placeholder={t("Search activity…")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ paddingLeft: 36 }}
            />
          </div>
          <Button
            type="button"
            variant={showFilters ? "default" : "outline"}
            size="icon"
            onClick={() => setShowFilters((v) => !v)}
            className="relative h-[40px] w-[40px]"
          >
            <Icon name="filter" size={15} strokeWidth={2} />
            {activeFilters > 0 ? (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
                {activeFilters}
              </span>
            ) : null}
          </Button>
        </div>
      </div>

{showFilters ? (
            <div style={{ borderBottom: "1px solid var(--border)", background: "var(--muted)", padding: "12px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <div className="col-dim" style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>{t("Time")}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {TIME_RANGES.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setRange(r.value)}
                      aria-pressed={range === r.value}
                      className={"badge " + (range === r.value ? "badge-blue" : "badge-gray")}
                      style={{ cursor: "pointer", padding: "4px 10px", fontSize: 11 }}
                    >
                      {t(r.label)}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span className="col-dim" style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>{t("From")}</span>
                <Input type="date" aria-label={t("From date")} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={{ width: 150, flex: "none", height: 36, fontSize: 13 }} />
                <span className="col-dim" style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>{t("To")}</span>
                <Input type="date" aria-label={t("To date")} value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={{ width: 150, flex: "none", height: 36, fontSize: 13 }} />
              </div>
<FilterChips title={t("Action")} options={actionOptions} selected={actionFilter} onToggle={(v) => toggle(actionFilter, setActionFilter, v)} format={actionLabel} t={t} />
<FilterChips title={t("Company")} options={companyOptions} selected={companyFilter} onToggle={(v) => toggle(companyFilter, setCompanyFilter, v)} t={t} />
              {activeFilters > 0 ? (
                <Button type="button" variant="ghost" size="sm" onClick={clearFilters} className="self-start text-xs">
                  {t("Clear filters")}
                </Button>
              ) : null}
            </div>
      ) : null}

      <div style={{ maxHeight: 420, overflowY: "auto" }}>
        <div className="divide-y divide-border">
          {filtered.length ? (
            filtered.map((a) => (
              <ActivityRow
                key={a._id}
                a={a}
                open={expandedId === a._id}
                onToggle={() => setExpandedId((cur) => (cur === a._id ? null : a._id))}
                t={t}
              />
            ))
          ) : (
            <div style={{ padding: "40px 20px", textAlign: "center", fontSize: 13, color: "var(--muted-foreground)" }}>
              {activities.length ? t("No activity matches your search or filters.") : t("No activity recorded")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Profile({ profile, account, activities, errors: serverErrors }) {
  const { t } = useI18n();
  const isAdmin = account.is_superuser;
  // Per-field saves, as before: each section posts only the fields it owns so
  // a Save on one never blanks out what another section manages.
  const nameForm = useForm({ full_name: account.full_name });
  const emailForm = useForm({ email: account.email || "" });
  const usernameForm = useForm({ username: account.username });
  const errors = { ...serverErrors, ...nameForm.errors, ...emailForm.errors, ...usernameForm.errors };

  const pickAvatar = (file) => {
    router.post("/account/avatar/upload/", { avatar: file }, { forceFormData: true });
  };

  const removeAvatar = () => {
    router.post("/account/avatar/delete/");
  };

  const saveName = (e) => {
    e.preventDefault();
    nameForm.post("/account/profile/update/");
  };

  const saveEmail = (e) => {
    e.preventDefault();
    emailForm.post("/account/profile/update/");
  };

  const saveUsername = (e) => {
    e.preventDefault();
    usernameForm.post("/account/profile/update/");
  };

  return (
    <div className="page shadcn-root">
      <div className="w-full max-w-4xl" style={{ marginLeft: "auto", marginRight: "auto" }}>
        <PageBack />

        <div className="page-header">
          <div>
            <div className="page-title">{t("Account Settings")}</div>
            <div className="page-sub">{t("Manage your account and personal information.")}</div>
          </div>
        </div>

        <div style={{ background: "var(--card)", borderRadius: "var(--radius-card)" }}>
          <SectionRow title="Your Avatar" description="An avatar is optional but strongly recommended.">
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <AvatarUploader onUpload={pickAvatar}>
                <button
                  type="button"
                  title={t("Change photo")}
                  className="group relative block h-[80px] w-[80px] shrink-0 cursor-pointer rounded-full border-0 bg-transparent p-0"
                >
                  <span className="block h-[80px] w-[80px] overflow-hidden rounded-full" style={{ boxShadow: "0 0 0 1px var(--border)" }}>
                    {profile.avatar_url ? (
                      <img src={profile.avatar_url} className="h-[80px] w-[80px] object-cover" alt="" />
                    ) : (
                      <span className="flex h-[80px] w-[80px] items-center justify-center rounded-full bg-secondary text-muted-foreground">
                        <Icon name="camera" size={28} strokeWidth={1.6} />
                      </span>
                    )}
                  </span>
                  <span
                    className="absolute bottom-0 right-0 flex h-[28px] w-[28px] items-center justify-center rounded-full bg-foreground text-background opacity-0 transition-opacity group-hover:opacity-100"
                    style={{ boxShadow: "0 0 0 3px var(--card)" }}
                  >
                    <Icon name="camera" size={13} strokeWidth={2} />
                  </span>
                </button>
              </AvatarUploader>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
                {profile.avatar_url ? (
                  <Button type="button" variant="ghost" size="sm" onClick={removeAvatar} style={{ color: "var(--destructive)" }}>
                    <Icon name="trash" size={14} strokeWidth={2} />
                    {t("Remove")}
                  </Button>
                ) : null}
                <span className="col-dim" style={{ fontSize: 12 }}>{t("Click your avatar to upload. PNG or JPG, square crop.")}</span>
              </div>
            </div>
          </SectionRow>

          <Hairline />

          <SectionRow
            title="Username"
            description={isAdmin ? "Change your login username." : "Only an administrator can change the username."}
          >
            {isAdmin ? (
              <form onSubmit={saveUsername} style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
                <div style={{ display: "flex", gap: 8, width: "100%" }}>
                  <Input
                    placeholder={t("Enter Your Username")}
                    aria-label={t("Username")}
                    value={usernameForm.data.username}
                    onChange={(e) => usernameForm.setData("username", e.target.value)}
                    aria-invalid={errors.username ? "true" : undefined}
                  />
                  <Button type="submit" variant="outline" size="lg" className="shrink-0" disabled={usernameForm.processing}>
                    {t("Save Changes")}
                  </Button>
                </div>
                {errors.username ? (
                  <span style={{ fontSize: 12, color: "var(--destructive)" }}>{errors.username}</span>
                ) : (
                  <span className="col-dim" style={{ fontSize: 12 }}>{t("Max 150 characters")}</span>
                )}
              </form>
            ) : (
              <div style={{ display: "flex", alignItems: "center", minHeight: 40 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "var(--foreground)" }}>{account.username}</span>
              </div>
            )}
          </SectionRow>

          <Hairline />

          <SectionRow title="Your Name" description="Please enter a display name you are comfortable with.">
            <form onSubmit={saveName} style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
              <div style={{ display: "flex", gap: 8, width: "100%" }}>
                <Input
                  placeholder={t("Enter Your Name")}
                  aria-label={t("Full name")}
                  value={nameForm.data.full_name}
                  onChange={(e) => nameForm.setData("full_name", e.target.value)}
                  aria-invalid={errors.full_name ? "true" : undefined}
                />
                <Button type="submit" variant="outline" size="lg" className="shrink-0" disabled={nameForm.processing}>
                  {t("Save Changes")}
                </Button>
              </div>
              {errors.full_name ? (
                <span style={{ fontSize: 12, color: "var(--destructive)" }}>{errors.full_name}</span>
              ) : (
                <span className="col-dim" style={{ fontSize: 12 }}>{t("Max 150 characters")}</span>
              )}
            </form>
          </SectionRow>

          <Hairline />

          <SectionRow title="Your Email" description="Please enter a primary email address.">
            <form onSubmit={saveEmail} style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
              <div style={{ display: "flex", gap: 8, width: "100%" }}>
                <Input
                  type="email"
                  placeholder={t("Enter Your Email")}
                  aria-label={t("Email")}
                  value={emailForm.data.email}
                  onChange={(e) => emailForm.setData("email", e.target.value)}
                  aria-invalid={errors.email ? "true" : undefined}
                />
                <Button type="submit" variant="outline" size="lg" className="shrink-0" disabled={emailForm.processing}>
                  {t("Save Changes")}
                </Button>
              </div>
              {errors.email ? <span style={{ fontSize: 12, color: "var(--destructive)" }}>{errors.email}</span> : null}
            </form>
          </SectionRow>

          <Hairline />

          <SectionRow title="Clearance" description="Access level for this account.">
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", minHeight: 40 }}>
              <span className={"badge " + (ROLE_BADGE[account.role] || "badge-gray")}>{account.role_badge}</span>
              <span className={account.is_active ? "badge badge-green" : "badge badge-gray"}>
                {account.is_active ? t("Active") : t("Inactive")}
              </span>
              {account.is_superuser ? <span className="badge badge-gray">{t("Superuser")}</span> : null}
            </div>
          </SectionRow>

          <Hairline />

          <SectionRow title="Password" description="Contact an admin to reset it.">
            <div style={{ display: "flex", alignItems: "center", minHeight: 40 }}>
              <span style={{ letterSpacing: 2, fontSize: 14, color: "var(--muted-foreground)" }}>••••••••</span>
            </div>
          </SectionRow>
        </div>

        <ActivityLog activities={activities} />
      </div>
    </div>
  );
}
