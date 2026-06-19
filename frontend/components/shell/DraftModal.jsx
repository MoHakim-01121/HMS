import { useEffect, useState } from "react";
import { Icon } from "../icons.jsx";
import { fetchJson } from "../../utils/fetchJson.js";

// AI "Pesan Tagihan" draft modal. Opened from anywhere via:
//   window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk } }))
export default function DraftModal() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ kind: "loading" }); // loading | ready | error
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function onOpen(e) {
      const { type, pk } = e.detail || {};
      setOpen(true);
      setCopied(false);
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
        <div style={{ padding: 20, minHeight: 120, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {state.kind === "loading" && <span style={{ color: "var(--text-3)", fontSize: 13 }}>Generating message…</span>}
          {state.kind === "error" && <span style={{ color: "var(--red)", fontSize: 13 }}>Failed to reach the server.</span>}
          {state.kind === "ready" && (
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13, lineHeight: 1.7, color: "var(--text)", margin: 0, width: "100%" }}>{text}</pre>
          )}
        </div>
        {state.kind === "ready" && (
          <div style={{ display: "flex", padding: "12px 20px", borderTop: "1px solid var(--border)", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Close</button>
            <button className="btn btn-primary btn-sm" onClick={copy}>
              <Icon name="copy" size={13} /> {copied ? "Copied!" : "Copy"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
