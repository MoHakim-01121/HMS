import { useState } from "react";
import { router } from "@inertiajs/react";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import Section from "../../components/shadcn/section.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import VisitMap from "../../components/ui/VisitMap.jsx";
import VisitPhotos from "../../components/ui/VisitPhotos.jsx";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import StatusPill from "../../components/shadcn/status-pill.jsx";

const OUTCOMES = [
  ["ORDER", "Order received"],
  ["PROSPECT", "Prospect / follow-up needed"],
  ["NO_INTEREST", "No interest"],
  ["NOT_MET", "Client not met"],
];

const OUTCOME_TONE = {
  ORDER: "green",
  PROSPECT: "blue",
  NO_INTEREST: "yellow",
  NOT_MET: "red",
};

function outcomeBadge(s) {
  const label = OUTCOMES.find(([k]) => k === s)?.[1] || s || "";
  return <StatusPill tone={OUTCOME_TONE[s] || "yellow"} label={label} />;
}

function heroPill(s) {
  if (s === "COMPLETED") return { label: "Completed", tone: "green" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "red" };
  return { label: "Planned", tone: "yellow" };
}

const FLOW_STEPS = [
  { key: "scheduled", label: "Scheduled" },
  { key: "result", label: "Result" },
  { key: "done", label: "Done" },
];

function StatusStepper({ status }) {
  const { t } = useI18n();
  let current;
  if (status === "COMPLETED") current = "done";
  else if (status === "CANCELLED") current = "cancelled";
  else current = "result";
  const index = FLOW_STEPS.findIndex((s) => s.key === current);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 16px", padding: "10px 14px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--card)" }}>
      {FLOW_STEPS.map((s, i) => {
        const reached = current === "cancelled" ? false : i <= index;
        const done = current === "cancelled" ? false : i < index;
        return (
          <div key={s.key} style={{ display: "flex", alignItems: "center", flex: 1, gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                width: 22, height: 22, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 600, flexShrink: 0,
                background: done ? "var(--green)" : reached ? "var(--accent-2)" : "var(--muted)",
                color: done || reached ? "#fff" : "var(--muted-foreground)",
              }}>{done ? "✓" : i + 1}</span>
              <span style={{ fontSize: 12, fontWeight: reached ? 600 : 500, color: reached ? "var(--foreground)" : "var(--muted-foreground)" }}>
                {t(s.label)}
              </span>
            </div>
            {i < FLOW_STEPS.length - 1 && (
              <div style={{ flex: 1, height: 2, borderRadius: 1, background: i < index ? "var(--green)" : "var(--border)" }} />
            )}
          </div>
        );
      })}
      {current === "cancelled" && (
        <span style={{ flexShrink: 0 }}><StatusPill tone="red" label={t("Cancelled")} /></span>
      )}
    </div>
  );
}

// Built on the same Dialog/DialogContent primitives as ui/dialog.jsx (Radix),
// not a hand-rolled overlay — there is no ".modal"/".modal-overlay" styling
// anywhere in this codebase to hang a custom markup on.
function CompleteDialog({ visitId, open, onOpenChange, onDone }) {
  const { t } = useI18n();
  const [outcome, setOutcome] = useState("");
  const [estimatedValue, setEstimatedValue] = useState("");
  const [picName, setPicName] = useState("");
  const [picPhone, setPicPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [nextFollowUp, setNextFollowUp] = useState("");
  const [coords, setCoords] = useState(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const captureLocation = () => {
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setLocating(false); },
      () => { showToast(t("Could not get your location"), "error"); setLocating(false); },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  const submit = async () => {
    if (!outcome) { showToast(t("Please choose a visit outcome"), "error"); return; }
    if (!notes.trim()) { showToast(t("Please describe the visit outcome"), "error"); return; }
    setSubmitting(true);
    try {
      const res = await fetchJson(`/visits/${visitId}/complete/`, {
        method: "POST",
        json: {
          checkin_lat: coords?.lat ?? null,
          checkin_lng: coords?.lng ?? null,
          outcome,
          estimated_value: estimatedValue || null,
          pic_name: picName,
          pic_phone: picPhone,
          result_notes: notes,
          next_follow_up_date: nextFollowUp || null,
        },
      });
      if (res.ok) { onDone(); router.reload(); }
    } catch {
      showToast(t("Failed to complete visit"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("Complete Visit")}</DialogTitle>
        </DialogHeader>

        <Button type="button" variant="secondary" onClick={captureLocation} disabled={locating}>
          {locating ? t("Locating…") : coords ? t("Location captured ✓") : t("Capture GPS location")}
        </Button>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">{t("Visit outcome")}</label>
          <Select value={outcome || undefined} onValueChange={setOutcome}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("Choose outcome…")} />
            </SelectTrigger>
            <SelectContent>
              {OUTCOMES.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {(outcome === "ORDER" || outcome === "PROSPECT") && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">{t("Estimated value (SAR, optional)")}</label>
            <Input type="number" min="0" value={estimatedValue} onChange={(e) => setEstimatedValue(e.target.value)} />
          </div>
        )}

        <div className="fg-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">{t("PIC met")}</label>
            <Input type="text" value={picName} onChange={(e) => setPicName(e.target.value)} placeholder={t("Contact person")} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">{t("PIC phone")}</label>
            <Input type="tel" value={picPhone} onChange={(e) => setPicPhone(e.target.value)} placeholder="+966 …" inputMode="tel" />
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">{t("Result notes")}</label>
          <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">{t("Next follow-up date (optional)")}</label>
          <Input type="date" value={nextFollowUp} onChange={(e) => setNextFollowUp(e.target.value)} />
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("Cancel")}</Button>
          <Button type="button" onClick={submit} disabled={submitting}>{t("Submit")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Detail({ visit, photos }) {
  const perms = usePerms();
  const { t } = useI18n();
  const openForm = useFormModal();
  const [showComplete, setShowComplete] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const canEdit = perms.can("visits", "edit");
  const hero = heroPill(visit.status);

  // useConfirm() (components/shadcn/confirm-dialog.jsx) is the house pattern
  // for a destructive-ish action confirmation — the same hook Cl/List.jsx
  // uses for delete — not a native window.confirm().
  const cancelVisit = () => {
    confirm({
      title: t("Cancel visit"),
      message: t("Cancel this visit appointment?"),
      onConfirm: () => router.post(`/visits/${visit.id}/cancel/`),
    });
  };

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/visits/" />
      <StatusStepper status={visit.status} />
      <DetailCard
        crumbs={[{ label: t("Visits"), href: "/visits/" }]}
        kicker={visit.scheduled_date}
        title={visit.client ? visit.client.name : t("(no client)")}
        sub={visit.staff_name}
        pill={{ ...hero, label: t(hero.label) }}
        actions={
          visit.status === "PLANNED" && canEdit ? (
            <>
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/visits/${visit.id}/edit/`)}>{t("Edit")}</button>
              <button type="button" className="hms-dv-act" onClick={() => setShowComplete(true)}>{t("Complete Visit")}</button>
              <button type="button" className="hms-dv-act" onClick={cancelVisit}>{t("Cancel")}</button>
            </>
          ) : (
            perms.can("visits", "export") && (
              <a className="hms-dv-act" href={`/visits/${visit.id}/pdf/`} target="_blank" rel="noreferrer">{t("Report PDF")}</a>
            )
          )
        }
      >
        <DetailGrid
          rows={[
            { label: t("Time slot"), icon: "clock", value: visit.time || t("—") },
            { label: t("Purpose"), icon: "tag", value: visit.purpose },
            visit.next_follow_up_date && { label: t("Next follow-up"), icon: "calendar", value: visit.next_follow_up_date },
          ]}
        />
      </DetailCard>

      {visit.status === "COMPLETED" && (
        <Section label={t("Visit Result")} icon="check">
          <p style={{ marginTop: 0 }}>{visit.result_notes}</p>
          <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginBottom: 12 }}>
            {t("Checked in")}: {visit.visited_at}
            {visit.distance_meters != null && (
              <span> · {visit.distance_meters > 500 ? "⚠ " : ""}{visit.distance_meters} m {t("from client's recorded location")}</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            {visit.outcome && outcomeBadge(visit.outcome)}
            {visit.pic_name && (
              <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("PIC")}: <strong style={{ color: "var(--foreground)" }}>{visit.pic_name}</strong>{visit.pic_phone ? ` · ${visit.pic_phone}` : ""}</span>
            )}
            {visit.estimated_value != null && (
              <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("Estimated value")}: <strong style={{ color: "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>{fmt(visit.estimated_value)} SAR</strong></span>
            )}
            {perms.can("visits", "export") && (
              <a href={`/visits/${visit.id}/pdf/`} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{t("Report PDF")} ↓</a>
            )}
          </div>
          <VisitMap
            clientLat={visit.client?.lat} clientLng={visit.client?.lng}
            checkinLat={visit.checkin_lat} checkinLng={visit.checkin_lng}
          />
        </Section>
      )}

      <VisitPhotos visitId={visit.id} initial={photos} canEdit={canEdit} />

      <CompleteDialog
        visitId={visit.id}
        open={showComplete}
        onOpenChange={setShowComplete}
        onDone={() => setShowComplete(false)}
      />
      {confirmDialog}
    </div>
  );
}
