import { useEffect, useState } from "react";
import { Icon } from "../icons.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog.jsx";
import { Button } from "./ui/button.jsx";
import { Textarea } from "./ui/textarea.jsx";

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
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex min-h-[120px] min-w-0 flex-col">
          {state.kind === "loading" && <div className="flex min-h-[120px] items-center justify-center text-[13px] text-muted-foreground">{t("Generating message…")}</div>}
          {state.kind === "error" && <div className="flex min-h-[120px] items-center justify-center text-[13px] text-destructive">{t("Failed to reach the server.")}</div>}
          {state.kind === "ready" && (
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={10}
              aria-label={title} className="field-sizing-fixed h-[min(340px,calc(100dvh-16rem))] min-h-[140px] resize-none leading-[1.7]" />
          )}
        </div>
        {state.kind === "ready" && (
          <DialogFooter>
            <Button variant="outline" onClick={copy}>
              <Icon name="copy" size={14} /> {copied ? t("Copied!") : t("Copy")}
            </Button>
            {waHref && (
              <Button asChild>
                <a href={waHref} target="_blank" rel="noreferrer">
                  <Icon name="message" size={14} /> {t("Open in WhatsApp")}
                </a>
              </Button>
            )}
          </DialogFooter>
        )}
        {state.kind === "ready" && !waHref && (
          <p className="mx-0.5 -mt-1 flex items-center gap-1.5 text-[12px] leading-normal text-muted-foreground">
            <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" className="shrink-0">
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
