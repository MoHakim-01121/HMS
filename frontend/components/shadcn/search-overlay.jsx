import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent } from "./ui/dialog.jsx";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const TYPE_LABEL = { CL: "Conf. Letter", INV: "Invoice Hotel", SVC: "Invoice Services" };

// shadcn/cmdk rebuild of ../shell/SearchOverlay.jsx — same open/onClose props.
// Command owns arrow-key navigation, highlight, and Enter-to-select natively,
// so the manual rowRefs/onPanelKeyDown logic the old version needed (added to
// fix the "hints are decorative, arrows don't work" bug) is gone entirely.
// shouldFilter={false} because results still come from the debounced
// /search/ fetch below, not cmdk's own client-side fuzzy filter.
export default function SearchOverlay({ open, onClose }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [state, setState] = useState({ kind: "quick" }); // quick | loading | results | error
  const timer = useRef(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setState({ kind: "quick" });
    }
  }, [open]);

  useEffect(() => {
    clearTimeout(timer.current);
    const query = q.trim();
    if (query.length < 2) {
      if (open) setState({ kind: "quick" });
      return;
    }
    setState({ kind: "loading" });
    timer.current = setTimeout(async () => {
      try {
        const res = await fetch("/search/?q=" + encodeURIComponent(query));
        const data = await res.json();
        setState({ kind: "results", data });
      } catch {
        setState({ kind: "error" });
      }
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q, open]);

  const groups = {};
  const order = [];
  if (state.kind === "results") {
    state.data.results.forEach((r) => {
      if (!groups[r.type]) { groups[r.type] = []; order.push(r.type); }
      groups[r.type].push(r);
    });
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      {/* Radius 24px / 2px border / shadow-2xl / bg-card + blurred overlay —
          measured off Homlu's live ⌘K command palette (rounded-3xl,
          border-stroke2, shadow-2xl, backdrop-blur-xs) via
          inspect-homlu-search2.js in this session's scratchpad. The overlay
          blur is no longer set here — DialogOverlay carries it for every
          overlay in the app now (see dialog.jsx). */}
      <DialogContent
        className="overflow-hidden p-0 rounded-[24px] border-2 border-border shadow-2xl bg-card"
        showCloseButton={false}
        style={{ maxWidth: 576 }}
      >
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={t("Search number, guest, or hotel…")}
            value={q}
            onValueChange={setQ}
            right={
              <kbd
                className="shrink-0 rounded-lg border border-border bg-secondary px-2 py-1 text-[11px] font-semibold text-foreground"
                style={{ marginRight: 6 }}
              >
                Esc
              </kbd>
            }
          />
          <CommandList>
            {state.kind === "quick" && (
              <div data-slot="command-state-empty" className="flex flex-col items-center justify-center gap-1 px-6 py-12 text-center">
                <span className="text-[13px] font-semibold text-foreground">{t("Type to search")}</span>
                <span className="text-xs text-muted-foreground">{t("document number, guest name, or hotel")}</span>
              </div>
            )}
            {state.kind === "loading" && (
              <div data-slot="command-state-loading" className="flex items-center justify-center gap-1.5 py-8">
                <span className="size-1 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "0ms" }} />
                <span className="size-1 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "150ms" }} />
                <span className="size-1 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "300ms" }} />
              </div>
            )}
            {state.kind === "error" && (
              <div data-slot="command-state-error" className="px-4 py-4 text-center text-[13px] text-destructive">{t("Search failed.")}</div>
            )}
            {state.kind === "results" && state.data.results.length === 0 && (
              <div data-slot="command-state-empty" className="flex flex-col items-center justify-center gap-1 px-6 py-12 text-center">
                <span className="text-[13px] font-semibold text-foreground">{t("No results")}</span>
                <span className="text-xs text-muted-foreground">{t("for “{q}”", { q: state.data.q })}</span>
              </div>
            )}
            {/* Plain Tailwind here on purpose, not design.css's .s-label/.s-sub —
                those were sized (fixed 140px) and fonted (Fira Code) for the old
                shell/SearchOverlay's horizontal row, and force stale warm-toned
                tokens (--text-2 etc) that clash with this dialog's neutral palette. */}
            {state.kind === "results" && order.map((type) => (
              <CommandGroup key={type} heading={`${t(TYPE_LABEL[type] || type)} (${groups[type].length})`}>
                {groups[type].map((r, i) => (
                  <CommandItem key={i} value={`${type}-${i}`} onSelect={() => { window.location.href = r.url; }}>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm font-medium text-foreground">{r.label}</span>
                      <span className="truncate text-xs text-muted-foreground">{r.sub}</span>
                    </div>
                    <span className="ml-auto max-w-[140px] shrink-0 truncate text-right text-[11px] text-muted-foreground">{r.meta}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
          <div className="flex items-center gap-3.5 border-t border-border bg-secondary/40 px-4 py-[7px] max-[600px]:hidden">
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <kbd className="flex size-5 items-center justify-center rounded-md border border-border bg-secondary text-[11px] font-semibold leading-none text-foreground">↑↓</kbd> {t("navigate")}
            </span>
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <kbd className="flex size-5 items-center justify-center rounded-md border border-border bg-secondary text-[11px] font-semibold leading-none text-foreground">↵</kbd> {t("select")}
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
