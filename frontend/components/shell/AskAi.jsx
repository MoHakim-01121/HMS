import { useEffect, useRef, useState } from "react";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";

// Ask AI (canvas "Record View HMS", AskAI): a floating panel on the dashboard.
// It lives in the shell and renders nothing on other pages, so the conversation
// is still there on coming back to it. The assistant gets invoice and CL totals only, no names or
// document numbers (hw/ai.py), so the suggestions stick to those.
const SUGGESTIONS = [
  { text: "Unpaid invoices", module: "invoice" },
  { text: "Invoices issued this month", module: "invoice" },
  { text: "Check-ins in the next 7 days", module: "cl" },
];

export const canAskAi = (perms) => ["invoice", "cl"].some((m) => (perms[m] || []).includes("view"));

export function SparkIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true" className="flex-none">
      <path d="M12 3.5c.5 3.9 2.6 6 6.5 6.5-3.9.5-6 2.6-6.5 6.5-.5-3.9-2.6-6-6.5-6.5 3.9-.5 6-2.6 6.5-6.5z" />
      <path d="M18.5 15.5c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5z" />
    </svg>
  );
}

// The reply as blocks: paragraphs and bullet lists.
export function parseReply(text) {
  const blocks = [];
  const last = (type) => {
    const tail = blocks[blocks.length - 1];
    if (tail?.type === type) return tail;
    const block = { type, items: [] };
    blocks.push(block);
    return block;
  };
  for (const line of String(text || "").split("\n")) {
    if (/^\s*[-•*]\s+/.test(line)) last("list").items.push(line.replace(/^\s*[-•*]\s+/, ""));
    else if (line.trim()) blocks.push({ type: "text", text: line.trim() });
  }
  return blocks;
}

function Inline({ text }) {
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i} className="font-semibold">{part}</strong> : part));
}

function Answer({ text }) {
  return (
    <div className="flex flex-col gap-3 text-[14px] leading-[1.6]">
      {parseReply(text).map((block, i) => {
        if (block.type === "text") return <p key={i} className="m-0 text-pretty"><Inline text={block.text} /></p>;
        return <ul key={i} className="m-0 flex list-disc flex-col gap-1 pl-5">{block.items.map((item, j) => <li key={j}><Inline text={item} /></li>)}</ul>;
      })}
    </div>
  );
}

const QUIET_BTN = "cursor-pointer rounded-full border-0 bg-transparent font-sans text-muted-foreground transition-[background-color,color] duration-[120ms] ease-[ease] hover:bg-secondary hover:text-foreground";
// Visible at once on the way in (a hidden panel cannot take focus), hidden only
// once it has faded on the way out.
const MOTION_IN = "transition-[opacity,translate,scale] duration-[180ms] ease-out-quint";
const MOTION_OUT = "transition-[opacity,translate,scale,visibility] duration-[150ms] ease-in-quick";

export default function AskAi({ shown, open, onOpen, onClose, perms }) {
  const { t } = useI18n();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const inputRef = useRef(null);
  const bodyRef = useRef(null);
  const returnTo = useRef(null);
  const latest = useRef(0);
  // Nothing opened from the keyboard animates.
  const viaKeys = useRef(false);

  useEffect(() => {
    const onKey = () => { viaKeys.current = true; };
    const onPointer = () => { viaKeys.current = false; };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer, true);
    return () => { document.removeEventListener("keydown", onKey, true); document.removeEventListener("pointerdown", onPointer, true); };
  }, []);

  // Opening puts the cursor in the box, except where that would raise a phone
  // keyboard over the suggestions. Closing hands focus back.
  useEffect(() => {
    if (open) {
      returnTo.current = document.activeElement;
      if (!window.matchMedia?.("(pointer: coarse)").matches) inputRef.current?.focus({ preventScroll: true });
      return undefined;
    }
    const el = returnTo.current;
    returnTo.current = null;
    if (el?.isConnected) el.focus({ preventScroll: true });
    return undefined;
  }, [open]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, busy, failed]);

  // The server remembers the last exchanges per session: a conversation that
  // starts empty here (new chat, reloaded page) must not inherit them.
  const ask = async (text, fresh) => {
    const id = ++latest.current;
    setBusy(true);
    setFailed(false);
    try {
      if (fresh) await fetchJson("/ai/chat/reset/", { method: "POST" });
      const data = await fetchJson("/ai/chat/", { method: "POST", json: { message: text } });
      if (id === latest.current) setMessages((m) => [...m, { from: "ai", text: data.reply }]);
    } catch {
      if (id === latest.current) setFailed(true);
    } finally {
      if (id === latest.current) setBusy(false);
    }
  };
  const send = (raw) => {
    const text = raw.trim();
    if (!text || busy) return;
    setDraft("");
    setMessages((m) => [...m, { from: "me", text }]);
    ask(text, messages.length === 0);
  };
  const retry = () => ask(messages[messages.length - 1].text, messages.length === 1);
  const newChat = () => {
    latest.current += 1;
    setMessages([]);
    setBusy(false);
    setFailed(false);
    setDraft("");
    inputRef.current?.focus({ preventScroll: true });
  };

  if (!shown) return null;

  const canSend = !!draft.trim() && !busy;
  const motion = (showing) => (viaKeys.current ? "transition-none" : showing ? MOTION_IN : MOTION_OUT);
  const suggestions = SUGGESTIONS.filter((s) => (perms[s.module] || []).includes("view"));

  return (
    <>
      <button type="button" onClick={onOpen} aria-haspopup="dialog" aria-expanded={open}
        className={cn(
          motion(!open),
          "fixed right-6 bottom-6 z-[var(--z-sticky,200)] hidden h-11 origin-bottom-right cursor-pointer items-center gap-2 rounded-full border-0 bg-primary pr-5 pl-4 font-sans text-[13.5px] leading-[normal] font-semibold tracking-[-0.005em] text-primary-foreground shadow-fab hover:bg-primary-hover desk:inline-flex print:hidden",
          open && "pointer-events-none invisible scale-90 opacity-0",
        )}>
        <SparkIcon />{t("Ask AI")}
      </button>

      <section role="dialog" aria-label={t("Ask AI")} aria-hidden={!open} ref={(el) => { if (el) el.inert = !open; }}
        className={cn(
          motion(open),
          // Below desk it sits exactly over the floating bottom nav.
          "fixed right-[max(10px,env(safe-area-inset-right))] bottom-[calc(10px_+_env(safe-area-inset-bottom))] left-[max(10px,env(safe-area-inset-left))] z-[calc(var(--z-sticky,200)_+_1)] flex h-[min(85dvh,calc(100dvh_-_32px))] origin-bottom-right flex-col overflow-hidden rounded-[20px] border border-border bg-card font-sans text-[14px] leading-[1.55] text-foreground shadow-palette desk:right-6 desk:bottom-6 desk:left-auto desk:h-[min(620px,calc(100dvh_-_48px))] desk:w-[440px] print:hidden",
          !open && "pointer-events-none invisible translate-y-3 scale-[.96] opacity-0",
        )}>
        <div className="flex flex-none items-center gap-1 pt-3.5 pr-3 pb-2.5 pl-5">
          <div className="min-w-0 flex-1">
            <h2 className="m-0 text-[15px] leading-[1.3] font-semibold tracking-[-0.01em]">{t("Ask AI")}</h2>
            <p className="mt-px mb-0 text-[12px] leading-[1.4] text-muted-foreground">{t("Reads only the data you're allowed to see")}</p>
          </div>
          {messages.length > 0 && <button type="button" onClick={newChat} className={cn(QUIET_BTN, "h-[30px] px-3 text-[12.5px] leading-[normal] font-medium")}>{t("New chat")}</button>}
          <button type="button" onClick={onClose} aria-label={t("Close")} className={cn(QUIET_BTN, "grid size-[30px] flex-none place-content-center")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div ref={bodyRef} aria-live="polite"
          className="scrollbar-quiet flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-contain px-5 pt-4 pb-5 [mask-image:linear-gradient(to_bottom,transparent_0,#000_16px,#000_calc(100%_-_20px),transparent_100%)]">
          {messages.length === 0 && (
            <div className="mt-auto">
              <h3 className="m-0 text-[19px] leading-[1.3] font-semibold tracking-[-0.015em]">{t("What do you want to know?")}</h3>
              <p className="mt-1.5 mb-0 text-[13px] leading-[1.55] text-pretty text-muted-foreground">{t("Answers use invoice and CL totals only; client names are not sent to the AI. Leave client details out of your question.")}</p>
              <div className="-mx-2.5 mt-4 flex flex-col gap-0.5">
                {suggestions.map((s) => (
                  <button key={s.text} type="button" onClick={() => send(t(s.text))}
                    className="group/sug flex min-h-10 cursor-pointer items-center justify-between gap-3 rounded-[10px] border-0 bg-transparent px-2.5 text-left font-sans text-[13.5px] leading-[normal] font-medium text-foreground transition-[background-color] duration-[120ms] ease-[ease] hover:bg-secondary">
                    {t(s.text)}
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="flex-none text-muted-foreground transition-[translate,color] duration-[160ms] ease-out-quint group-hover/sug:translate-x-[3px] group-hover/sug:text-foreground"><path d="M5 12h13M12 6l6 6-6 6" /></svg>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.from === "me"
              ? <div key={i} className="max-w-[78%] self-end rounded-[18px_18px_6px_18px] bg-secondary px-3.5 py-2 text-[13.5px] leading-[1.5] text-pretty break-words">{m.text}</div>
              : <Answer key={i} text={m.text} />
          ))}
          {busy && (
            <div role="status" className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
              <span className="inline-flex gap-1" aria-hidden="true">
                {["", "[animation-delay:150ms]", "[animation-delay:300ms]"].map((delay) => <i key={delay} className={cn("size-[5px] animate-pulse rounded-full bg-muted-foreground", delay)} />)}
              </span>
              {t("Reading your records…")}
            </div>
          )}
          {failed && (
            <div role="alert" className="flex flex-col items-start gap-2.5 text-[13.5px] leading-[1.55] text-muted-foreground">
              <div><b className="block font-semibold text-danger-text">{t("Couldn't get an answer.")}</b> {t("The server did not respond.")}</div>
              <button type="button" onClick={retry}
                className="h-8 cursor-pointer rounded-full border border-input bg-card px-3.5 font-sans text-[12.5px] leading-[normal] font-semibold text-foreground transition-[border-color] duration-[120ms] ease-[ease] hover:border-foreground">{t("Try again")}</button>
            </div>
          )}
        </div>

        <div className="flex flex-none flex-col gap-2 px-5 pb-3.5">
          <label className="flex cursor-text items-end gap-2 rounded-[18px] border border-input bg-card py-1.5 pr-1.5 pl-3 shadow-float transition-[border-color] duration-[140ms] ease-[ease] focus-within:border-foreground">
            <span className="sr-only">{t("Your question")}</span>
            <textarea ref={inputRef} rows={1} value={draft} placeholder={t("Ask about invoice or CL totals")}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(draft); } }}
              className="max-h-[120px] min-h-[22px] w-full min-w-0 flex-1 resize-none border-0 bg-transparent py-[5px] font-sans text-[14px] leading-[1.5] text-foreground outline-none [field-sizing:content] placeholder:text-muted-foreground focus-visible:outline-none" />
            <button type="button" aria-label={t("Send")} aria-disabled={!canSend} onClick={() => send(draft)}
              className={cn("grid size-8 flex-none cursor-pointer place-content-center rounded-full border-0 bg-primary text-primary-foreground transition-[background-color,color] duration-[120ms] ease-[ease]", !canSend && "cursor-default bg-secondary text-muted-foreground")}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
            </button>
          </label>
          <p className="m-0 text-center text-[11px] leading-[1.4] text-muted-foreground">{t("Answers can be wrong. Check the figures on the list pages.")}</p>
        </div>
      </section>
    </>
  );
}
