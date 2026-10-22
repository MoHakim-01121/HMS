import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { DPage, DTop, DHead, DCard, DPill } from "../../components/shadcn/detail-a.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtStay } from "../../utils/format.js";

// Client detail, the "Client Detail" artboard on the Record View HMS canvas:
// identity in the head card, Contact and Location side by side, then the
// reservation history and notes. Money for this client lives under Finance.

const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;
const REMINDER = { PIC: "PIC", GROUP: "Group", BOTH: "PIC & Group" };
const STATUS = {
  DEFINITE: { label: "Definite", tone: "green" },
  TENTATIVE: { label: "Tentative", tone: "amber" },
  CANCELLED: { label: "Cancelled", tone: "red" },
};

function PinMap({ lat, lng, label }) {
  const ref = useRef(null);
  useEffect(() => {
    let map, observer;
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !ref.current) return;
      map = L.map(ref.current, { zoomControl: false, scrollWheelZoom: false, attributionControl: false }).setView([lat, lng], 15);
      const url = () => basemapUrl(document.documentElement.getAttribute("data-theme"));
      const tiles = L.tileLayer(url(), basemapOptions).addTo(map);
      observer = new MutationObserver(() => tiles.setUrl(url()));
      observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });
      const icon = L.divIcon({
        className: "",
        html: '<div style="width:12px;height:12px;border-radius:50%;background:var(--foreground);box-shadow:0 0 0 4px var(--card)"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      });
      // Leaflet renders a string tooltip as HTML; a text node keeps the name plain.
      L.marker([lat, lng], { icon }).bindTooltip(document.createTextNode(label), { permanent: true, direction: "top", offset: [0, -8] }).addTo(map);
    });
    return () => {
      cancelled = true;
      if (observer) observer.disconnect();
      if (map) map.remove();
    };
  }, [lat, lng, label]);
  return <div ref={ref} />;
}

export default function Detail({ client, cls }) {
  const { t } = useI18n();
  const c = client;
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const [copied, setCopied] = useState(false);
  const del = () => confirm({
    title: t("Delete client"),
    message: t("Delete client \"{name}\"?", { name: c.name }),
    detail: t("This cannot be undone. Deactivate it instead to keep its history."),
    danger: true,
    onConfirm: () => router.post(`/clients/${c.pk}/delete/`),
  });

  const address = [c.address, c.city, c.province].filter(Boolean).join(", ");
  const hasCoords = c.lat != null && c.lng != null;
  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard blocked — the address is still selectable */ }
  };

  const menu = [
    perms.can("cl", "create") && { label: t("Create CL"), icon: "plus", onClick: () => openForm(`/cl/new/?client=${c.pk}`) },
    perms.can("statements", "view") && { label: t("Client Finance"), icon: "wallet", href: `/finance/clients/${c.pk}/statement/` },
    perms.can("clients", "edit") && { label: t("Edit"), icon: "edit", separator: true, onClick: () => openForm(`/clients/${c.pk}/edit/`) },
    perms.can("clients", "edit") && (c.is_active
      ? { label: t("Deactivate"), icon: "close", onClick: () => router.post(`/clients/${c.pk}/active/`) }
      : { label: t("Activate"), icon: "check", onClick: () => router.post(`/clients/${c.pk}/active/`) }),
    perms.can("clients", "delete") && { label: t("Delete client…"), icon: "trash", danger: true, separator: true, onClick: del },
  ];

  const lastOrder = c.days_since_last_order == null ? t("No orders yet")
    : c.days_since_last_order === 0 ? t("Today")
      : t(c.days_since_last_order === 1 ? "1 day ago" : "{n} days ago", { n: c.days_since_last_order });

  return (
    <DPage>
      <DTop href="/clients/" />

      <DHead
        title={c.name}
        badge={c.is_active ? { label: t("Active"), tone: "green" } : { label: t("Inactive"), tone: "gray" }}
        menu={menu}
        cols={4}
        facts={[
          { k: t("Brand"), v: c.brand || t("Not set") },
          { k: t("Branch"), v: c.branch || t("Not set") },
          { k: t("Client since"), v: c.created_at || t("Not set") },
          { k: t("Last order"), v: lastOrder },
        ]}
      />

      <div className="da-pair">
        <DCard pad title={t("Contact")}>
          <dl className="da-kv">
            <dt>PIC</dt><dd>{c.pic || <span style={{ color: "var(--muted-foreground)", fontWeight: 400 }}>{t("Not set")}</span>}</dd>
            <dt>WhatsApp</dt>
            <dd className={c.wa ? undefined : "mut"}>{c.wa ? <a href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer">{c.wa}</a> : t("Not set")}</dd>
            <dt>{t("WhatsApp group")}</dt><dd className={c.wa_group ? undefined : "mut"}>{c.wa_group || t("Not set")}</dd>
            <dt>Email</dt><dd className={c.email ? undefined : "mut"}>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : t("Not set")}</dd>
            <dt>{t("Reminders to")}</dt><dd>{t(REMINDER[c.reminder_target] || c.reminder_target)}</dd>
            <dt>{t("Address")}</dt><dd className={address ? undefined : "mut"}>{address || t("Not set")}</dd>
          </dl>
          {needsWaGroup(c) ? (
            <div style={{ marginTop: "auto", paddingTop: 14 }}>
              <p style={{ margin: 0, paddingTop: 14, borderTop: "1px solid var(--border)", fontSize: 13, lineHeight: 1.5, color: "var(--danger-text)" }}>
                {t("Reminder is set to {target} but the WhatsApp Group is not set.", { target: c.reminder_target === "BOTH" ? t("PIC & Group") : t("Group") })}
              </p>
            </div>
          ) : null}
        </DCard>

        <DCard
          title={t("Location")}
          actions={hasCoords ? <a href={`https://www.google.com/maps?q=${c.lat},${c.lng}`} target="_blank" rel="noreferrer">{t("Open in Google Maps")} ↗</a> : null}
        >
          {hasCoords ? (
            <>
              <div className="da-map" role="img" aria-label={t("Map showing {name}", { name: c.name })} style={{ marginTop: 4 }}>
                <PinMap lat={c.lat} lng={c.lng} label={c.brand || c.name} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "14px 24px 18px", fontSize: 13 }}>
                <span style={{ color: "var(--muted-foreground)", fontVariantNumeric: "tabular-nums" }}>{c.lat.toFixed(4)}, {c.lng.toFixed(4)}</span>
                <span style={{ display: "flex", gap: 6 }}>
                  {address ? <button type="button" className="da-btn soft" onClick={copyAddress}>{copied ? t("Copied") : t("Copy address")}</button> : null}
                  <a className="da-btn soft" href="/clients/map/">{t("View on client map")}</a>
                </span>
              </div>
            </>
          ) : (
            <div className="da-empty">{t("Location not set. Add coordinates on the edit form to show this client on the map.")}</div>
          )}
        </DCard>
      </div>

      <DCard title={t("Reservation history")} meta={t(cls.length === 1 ? "1 reservation" : "{n} reservations", { n: cls.length })}>
        {cls.length ? (
          <div className="da-scroll">
            <table className="da-t">
              <thead><tr><th>{t("Reservation")}</th><th>{t("Hotel")}</th><th>{t("Stay")}</th><th className="n">{t("Nights")}</th><th className="n">{t("Pax")}</th><th>{t("Status")}</th></tr></thead>
              <tbody>
                {cls.map((cl) => {
                  const st = STATUS[cl.status] || STATUS.TENTATIVE;
                  return (
                    <tr key={cl.pk}>
                      <td><a href={`/cl/${cl.pk}/`}>{cl.confirmation_number}</a>{cl.guest_name && cl.guest_name !== c.name ? <span className="sub">{cl.guest_name}</span> : null}</td>
                      <td>{cl.hotel_name || t("Not set")}</td>
                      <td className="nw">{fmtStay(cl.check_in, cl.check_out) || t("Not set")}</td>
                      <td className="n">{cl.num_nights ?? ""}</td>
                      <td className="n">{cl.num_guests ?? ""}</td>
                      <td><DPill sm tone={st.tone}>{t(st.label)}</DPill></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <div className="da-empty">{t("No confirmation letters yet")}</div>}
      </DCard>

      {c.note ? (
        <DCard pad title={t("Notes")}>
          <p className="da-text">{c.note}</p>
        </DCard>
      ) : null}

      {confirmDialog}
    </DPage>
  );
}
