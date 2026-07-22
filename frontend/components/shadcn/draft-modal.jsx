import { useEffect, useState } from "react";
import { Icon } from "../icons.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "./toast.jsx";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog.jsx";

// shadcn Dialog-based rebuild of ../shell/DraftModal.jsx — business logic
// (fetch/send) is unchanged; only the modal chrome moved to shadcn's Dialog,
// which owns focus trap + Escape + the close button (so the old manual
// close button and keydown listener are both gone).
export default function DraftModal() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ kind: "loading" }); // loading | ready | error
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const [pk, setPk] = useState(null);
  const [waSend, setWaSend] = useState(null);
  const [targetKind, setTargetKind] = useState("manual");
  const [manualTarget, setManualTarget] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [withPdf, setWithPdf] = useState(true);

  useEffect(() => {
    async function onOpen(e) {
      const { type, pk, waSend } = e.detail || {};
      setOpen(true);
      setCopied(false);
      setSendError("");
      setManualTarget("");
      setWithPdf(true);
      setPk(pk);
      setWaSend(waSend || null);
      setTargetKind(waSend?.has_wa ? "client_wa" : waSend?.has_group ? "client_group" : "manual");
      setState({ kind: "loading" });
      try {
        const data = await fetchJson("/ai/draft/", { method: "POST", json: { type, pk } });
        setText(data.message || "");
        setState({ kind: "ready" });
      } catch {
        setState({ kind: "error" });
      }
    }
    window.addEventListener("open-draft", onOpen);
    return () => window.removeEventListener("open-draft", onOpen);
  }, []);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const send = async () => {
    setSending(true);
    setSendError("");
    try {
      const data = await fetchJson("/billing/send/", {
        method: "POST",
        json: { pk, message: text, target_kind: targetKind, manual_target: manualTarget, with_pdf: withPdf },
      });
      if (data.ok) {
        showToast("Pesan masuk antrean");
        setOpen(false);
      } else {
        setSendError(data.message || "Gagal mengirim pesan");
      }
    } catch {
      setSendError("Gagal mengirim pesan");
    } finally {
      setSending(false);
    }
  };

  const radio = (kind, label, disabled) => (
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: disabled ? "var(--muted-foreground)" : "var(--foreground)", cursor: disabled ? "not-allowed" : "pointer" }}>
      <input type="radio" name="wa-target" checked={targetKind === kind} disabled={disabled} onChange={() => setTargetKind(kind)} />
      {label}
    </label>
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="message" size={16} /> Billing Message
          </DialogTitle>
        </DialogHeader>
        <div style={{ minHeight: 120 }}>
          {state.kind === "loading" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--muted-foreground)", fontSize: 13 }}>Generating message…</div>}
          {state.kind === "error" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--destructive)", fontSize: 13 }}>Failed to reach the server.</div>}
          {state.kind === "ready" && (
            <>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={8}
                style={{ width: "100%", fontFamily: "inherit", fontSize: 13, lineHeight: 1.7, color: "var(--foreground)", background: "transparent", border: "1px solid var(--border)", borderRadius: 8, padding: 10, resize: "vertical" }}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--foreground)", cursor: "pointer", marginBottom: 14 }}>
                  <input type="checkbox" checked={withPdf} onChange={(e) => setWithPdf(e.target.checked)} />
                  Lampirkan PDF invoice
                </label>
                {radio("client_wa", `WA Client${waSend?.client_wa ? ` — ${waSend.client_wa}` : ""}`, !waSend?.has_wa)}
                {radio("client_group", "WA Group Client", !waSend?.has_group)}
                {radio("manual", "Nomor lain", false)}
                {targetKind === "manual" && (
                  <input
                    type="text"
                    value={manualTarget}
                    onChange={(e) => setManualTarget(e.target.value)}
                    placeholder="628xxx atau ID group (…@g.us)"
                    style={{ fontSize: 13, padding: "8px 10px", border: "1px solid var(--border)", borderRadius: 8, background: "transparent", color: "var(--foreground)" }}
                  />
                )}
              </div>
              {sendError && <div style={{ color: "var(--destructive)", fontSize: 12, marginTop: 10 }}>{sendError}</div>}
            </>
          )}
        </div>
        {state.kind === "ready" && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              <Icon name="copy" size={13} /> {copied ? "Copied!" : "Copy"}
            </button>
            <button className="btn btn-primary btn-sm" onClick={send} disabled={sending}>
              <Icon name="message" size={13} /> {sending ? "Mengirim…" : "Kirim WA"}
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
