import { useEffect, useState } from "react";
import { Icon } from "../icons.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog.jsx";

// Message generator. The app never sends WhatsApp itself — this modal only
// produces the message text for the operator to copy and send by hand (a
// wa.me deep link is offered when a number is known).
//
// Opened via a window "open-draft" CustomEvent, two shapes:
//   { type, pk, waSend }        → fetch the text from /ai/draft/ (billing)
//   { message, title, waNumber } → show a pre-built message as-is (recap, reminder)
export default function DraftModal() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ kind: "loading" }); // loading | ready | error
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const [title, setTitle] = useState("");
  const [waNumber, setWaNumber] = useState("");

  useEffect(() => {
    async function onOpen(e) {
      const { type, pk, waSend, message, title: customTitle, waNumber: num } = e.detail || {};
      setOpen(true);
      setCopied(false);
      setTitle(customTitle || t("Billing Message"));

      if (message != null) {
        setText(message);
        setWaNumber(num || "");
        setState({ kind: "ready" });
        return;
      }

      setWaNumber(waSend?.client_wa || "");
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
  }, [t]);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const waHref = waNumber
    ? `https://wa.me/${String(waNumber).replace(/[^\d]/g, "")}?text=${encodeURIComponent(text)}`
    : null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[480px] hms-dialog">
        <DialogHeader>
          <DialogTitle style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="message" size={16} /> {title}
          </DialogTitle>
        </DialogHeader>
        <div style={{ minHeight: 120 }}>
          {state.kind === "loading" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--muted-foreground)", fontSize: 13 }}>{t("Generating message…")}</div>}
          {state.kind === "error" && <div style={{ display: "flex", minHeight: 120, alignItems: "center", justifyContent: "center", color: "var(--destructive)", fontSize: 13 }}>{t("Failed to reach the server.")}</div>}
          {state.kind === "ready" && (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={10}
              style={{ width: "100%", fontFamily: "inherit", fontSize: 13, lineHeight: 1.7, color: "var(--foreground)", background: "transparent", border: "1px solid var(--border)", borderRadius: 8, padding: 10, resize: "vertical" }}
            />
          )}
        </div>
        {state.kind === "ready" && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              <Icon name="copy" size={13} /> {copied ? t("Copied!") : t("Copy")}
            </button>
            {waHref && (
              <a className="btn btn-primary btn-sm" href={waHref} target="_blank" rel="noreferrer">
                <Icon name="message" size={13} /> {t("Open in WhatsApp")}
              </a>
            )}
          </div>
        )}
        {state.kind === "ready" && !waHref && (
          <p style={{ display: "flex", alignItems: "center", gap: 6, margin: "12px 2px 0", fontSize: 11.5, color: "var(--muted-foreground)", lineHeight: 1.5 }}>
            <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="9" />
              <path strokeLinecap="round" d="M12 11v5M12 8h.01" />
            </svg>
            {t("No WhatsApp number on file — copy the message and send it manually.")}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
