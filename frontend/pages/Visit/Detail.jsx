import { useState } from "react";
import { router } from "@inertiajs/react";
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
import { RvBack, RvHero, RvFigure, RvSteps, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";

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

const fmtDay = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

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

  const steps = visit.status === "COMPLETED"
    ? [{ label: t("Scheduled"), state: "done" }, { label: t("Result"), state: "done" }, { label: t("Done"), state: "done" }]
    : visit.status === "CANCELLED"
      ? [{ label: t("Scheduled"), state: "todo" }, { label: t("Result"), state: "todo" }, { label: t("Done"), state: "todo" }]
      : [{ label: t("Scheduled"), state: "done" }, { label: t("Result"), state: "now" }, { label: t("Done"), state: "todo" }];

  const note =
    visit.status === "CANCELLED"
      ? { icon: <Icon name="alert-circle" size={13} strokeWidth={2} />, iconBg: "var(--red)", title: t("Cancelled"), text: t("This visit appointment was cancelled.") }
      : visit.status === "COMPLETED"
        ? {
            icon: <Icon name="check" size={12} strokeWidth={2.4} />,
            iconBg: "var(--green)",
            title: visit.outcome_label || t("Completed"),
            text: t("This visit is complete."),
          }
        : {
            icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
            iconBg: "var(--yellow)",
            title: t("Planned"),
            text: t("This visit is scheduled but has not happened yet."),
          };

  const detailCells = [];
  detailCells.push(
    <div key="time">
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--muted-foreground)" }}>{t("Time slot")}</div>
      <div style={{ fontSize: 13.5, fontWeight: 500, marginTop: 4 }}>{visit.time || t("Not set")}</div>
    </div>,
  );
  detailCells.push(
    <div key="purpose">
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--muted-foreground)" }}>{t("Purpose")}</div>
      <div style={{ fontSize: 13.5, fontWeight: 500, marginTop: 4 }}>{visit.purpose}</div>
    </div>,
  );
  if (visit.next_follow_up_date) {
    detailCells.push(
      <div key="next">
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--muted-foreground)" }}>{t("Next follow-up")}</div>
        <div style={{ fontSize: 13.5, fontWeight: 500, marginTop: 4 }}>{visit.next_follow_up_date}</div>
      </div>,
    );
  }

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

  const sections = [
    {
      title: t("Details"),
      body: (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
          {detailCells}
        </div>
      ),
    },
  ];
  if (visit.status === "COMPLETED") {
    sections.push({
      title: t("Visit Result"),
      body: (
        <>
          <p style={{ marginTop: 0 }}>{visit.result_notes}</p>
          <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginBottom: 12 }}>
            {t("Checked in")}: {visit.visited_at}
            {visit.distance_meters != null && (
              <span> – {visit.distance_meters} m {t("from client's recorded location")}</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            {visit.outcome && outcomeBadge(visit.outcome)}
            {visit.pic_name && (
              <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("PIC")}: <strong style={{ color: "var(--foreground)" }}>{visit.pic_name}</strong>{visit.pic_phone ? ` – ${visit.pic_phone}` : ""}</span>
            )}
            {visit.estimated_value != null && (
              <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("Estimated value")}: <strong style={{ color: "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>{fmt(visit.estimated_value)} SAR</strong></span>
            )}
            {perms.can("visits", "export") && (
              <a href={`/visits/${visit.id}/pdf/`} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{t("Report PDF")}</a>
            )}
          </div>
          <VisitMap
            clientLat={visit.client?.lat} clientLng={visit.client?.lng}
            checkinLat={visit.checkin_lat} checkinLng={visit.checkin_lng}
          />
        </>
      ),
    });
  }
  sections.push({
    title: t("Photos"),
    body: <VisitPhotos visitId={visit.id} initial={photos} canEdit={canEdit} bare />,
  });

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/visits/" label={t("Back")} />

      <RvHero
        badge={{ label: t(hero.label), tone: hero.tone }}
        title={visit.client ? visit.client.name : t("No client")}
        facts={[
          visit.staff_name ? { k: t("Staff"), v: visit.staff_name } : null,
          fmtDay(visit.scheduled_date) ? { k: t("Date"), v: fmtDay(visit.scheduled_date) } : null,
          visit.time ? { k: t("Time"), v: visit.time } : null,
        ].filter(Boolean)}
        mainExtra={<RvSteps steps={steps} />}
        side={
          visit.status === "COMPLETED" && visit.estimated_value != null ? (
            <RvFigure
              label={t("Estimated value")}
              value={fmt(visit.estimated_value)}
              unit="SAR"
              color="var(--green)"
            />
          ) : null
        }
        note={note}
        actions={
          visit.status === "PLANNED" && canEdit ? (
            <>
              <button type="button" className="hms-rv-btn" onClick={() => openForm(`/visits/${visit.id}/edit/`)}>{t("Edit")}</button>
              <button type="button" className="hms-rv-btn primary" onClick={() => setShowComplete(true)}>{t("Complete Visit")}</button>
              <button type="button" className="hms-rv-btn danger" onClick={cancelVisit}>{t("Cancel")}</button>
            </>
          ) : (
            perms.can("visits", "export") && (
              <a className="hms-rv-btn" href={`/visits/${visit.id}/pdf/`} target="_blank" rel="noreferrer">{t("Report PDF")}</a>
            )
          )
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {sections.map((s, i) => (
              <RvSection key={s.title} title={s.title} first={i === 0}>
                {s.body}
              </RvSection>
            ))}
          </RvCard>
        </div>

        <RvRail
          rows={[
            visit.client
              ? { k: t("Client"), v: <a href={`/clients/${visit.client.id}/`}>{visit.client.name}</a> }
              : null,
            fmtDay(visit.scheduled_date) ? { k: t("Date"), v: fmtDay(visit.scheduled_date) } : null,
            visit.time ? { k: t("Time"), v: visit.time } : null,
            visit.purpose ? { k: t("Purpose"), v: visit.purpose } : null,
            visit.next_follow_up_date ? { k: t("Next follow-up"), v: visit.next_follow_up_date } : null,
            visit.status === "COMPLETED" && visit.visited_at ? { k: t("Checked in"), v: visit.visited_at } : null,
            visit.status === "COMPLETED" && visit.distance_meters != null ? { k: t("Distance"), v: `${visit.distance_meters} m` } : null,
          ].filter(Boolean)}
        />
      </div>

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