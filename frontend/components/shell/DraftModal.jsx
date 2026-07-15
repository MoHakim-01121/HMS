import { useEffect, useState } from "react";
import { Icon } from "../icons.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { showToast } from "./Toast.jsx";

// AI "Pesan Tagihan" draft modal. Opened from anywhere via:
//   window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }))
// waSend: { client_name, client_wa, has_wa, has_group } — dari props halaman detail.
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

  useEffect(() => {
    async function onOpen(e) {
      const { type, pk, waSend } = e.detail || {};
      setOpen(true);
      setCopied(false);
      setSendError("");
      setManualTarget("");
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

  if (!open) return null;

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
        json: { pk, message: text, target_kind: targetKind, manual_target: manualTarget },
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
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: disabled ? "var(--text-3)" : "var(--text)", cursor: disabled ? "not-allowed" : "pointer" }}>
      <input type="radio" name="wa-target" checked={targetKind === kind} disabled={disabled} onChange={() => setTargetKind(kind)} />
      {label}
    </label>
  );

  return (
    <div
      style={{ display: "flex", position: "fixed", inset: 0, zIndex: "var(--z-modal)", background: "rgba(0,0,0,.5)", alignItems: "center", justifyContent: "center", padding: 20 }}
      onClick={(e) => e.target === e.currentTarget && setOpen(false)}
    >
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, width: "100%", maxWidth: 480, overflow: "hidden", boxShadow: "0 24px 48px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
            <Icon name="message" size={16} /> Billing Message
          </div>
          <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 4 }}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <div style={{ padding: 20, minHeight: 120 }}>
          {state.kind === "loading" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--text-3)", fontSize: 13 }}>Generating message…</div>}
          {state.kind === "error" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--red)", fontSize: 13 }}>Failed to reach the server.</div>}
          {state.kind === "ready" && (
            <>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={8}
                style={{ width: "100%", fontFamily: "inherit", fontSize: 13, lineHeight: 1.7, color: "var(--text)", background: "transparent", border: "1px solid var(--border)", borderRadius: 8, padding: 10, resize: "vertical" }}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
                {radio("client_wa", `WA Client${waSend?.client_wa ? ` — ${waSend.client_wa}` : ""}`, !waSend?.has_wa)}
                {radio("client_group", "WA Group Client", !waSend?.has_group)}
                {radio("manual", "Nomor lain", false)}
                {targetKind === "manual" && (
                  <input
                    type="text"
                    value={manualTarget}
                    onChange={(e) => setManualTarget(e.target.value)}
                    placeholder="628xxx atau ID group (…@g.us)"
                    style={{ fontSize: 13, padding: "8px 10px", border: "1px solid var(--border)", borderRadius: 8, background: "transparent", color: "var(--text)" }}
                  />
                )}
              </div>
              {sendError && <div style={{ color: "var(--red)", fontSize: 12, marginTop: 10 }}>{sendError}</div>}
            </>
          )}
        </div>
        {state.kind === "ready" && (
          <div style={{ display: "flex", padding: "12px 20px", borderTop: "1px solid var(--border)", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Close</button>
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              <Icon name="copy" size={13} /> {copied ? "Copied!" : "Copy"}
            </button>
            <button className="btn btn-primary btn-sm" onClick={send} disabled={sending}>
              <Icon name="message" size={13} /> {sending ? "Mengirim…" : "Kirim WA"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
