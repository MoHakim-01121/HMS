import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent } from "./ui/dialog.jsx";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command.jsx";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";

const TYPE_LABEL = { CL: "Conf. Letter", INV: "Invoice Hotel" };
// Group label in caps over 46px rows, a hairline between groups.
const GROUP = "p-0 [&_[cmdk-group-heading]]:border-t [&_[cmdk-group-heading]]:border-hairline [&_[cmdk-group-heading]]:px-[18px] [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-[7px] [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[.13em] first:[&_[cmdk-group-heading]]:border-t-0";

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
        const data = await fetchJson("/search/?q=" + encodeURIComponent(query));
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
        className="overflow-hidden p-0 rounded-[20px] shadow-palette border border-border bg-card max-w-[min(520px,calc(100%-2rem))] top-[64px] translate-y-0 sm:top-[64px] sm:translate-y-0 phone:top-[64px] phone:translate-y-0"
        showCloseButton={false}
      >
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={t("Search number, guest, or hotel…")}
            value={q}
            onValueChange={setQ}
            wrapperClassName="h-[54px] px-[18px]"
            right={
              <kbd
                className="mr-1.5 inline-flex h-[22px] shrink-0 items-center rounded-[8px] bg-secondary text-[11px] font-semibold text-muted-foreground"
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
                <span className="size-1 animate-pulse rounded-full bg-muted-foreground motion-reduce:animate-none" style={{ animationDelay: "0ms" }} />
                <span className="size-1 animate-pulse rounded-full bg-muted-foreground motion-reduce:animate-none" style={{ animationDelay: "150ms" }} />
                <span className="size-1 animate-pulse rounded-full bg-muted-foreground motion-reduce:animate-none" style={{ animationDelay: "300ms" }} />
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
              <CommandGroup key={type} className={GROUP} heading={`${t(TYPE_LABEL[type] || type)} (${groups[type].length})`}>
                {groups[type].map((r, i) => (
                  <CommandItem key={i} className="min-h-[46px] gap-3 rounded-none px-[18px] py-0" value={`${type}-${i}`} onSelect={() => { window.location.href = r.url; }}>
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
          <div className="flex items-center gap-3.5 border-t border-hairline px-[18px] py-[11px] phone:hidden">
            <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <kbd className="flex h-5 items-center rounded-[8px] bg-secondary px-1.5 text-[10.5px] font-semibold leading-none text-muted-foreground">↑↓</kbd> {t("navigate")}
            </span>
            <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <kbd className="flex h-5 items-center rounded-[8px] bg-secondary px-1.5 text-[10.5px] font-semibold leading-none text-muted-foreground">Enter</kbd> {t("open")}
            </span>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {state.kind === "results"
                ? t("{n} results across modules", { n: state.data.results.length })
                : t("across all modules")}
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
