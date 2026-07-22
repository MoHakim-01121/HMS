import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent } from "./ui/dialog.jsx";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command.jsx";

const TYPE_LABEL = { CL: "Conf. Letter", INV: "Invoice Hotel", SVC: "Invoice Services" };

// shadcn/cmdk rebuild of ../shell/SearchOverlay.jsx — same open/onClose props.
// Command owns arrow-key navigation, highlight, and Enter-to-select natively,
// so the manual rowRefs/onPanelKeyDown logic the old version needed (added to
// fix the "hints are decorative, arrows don't work" bug) is gone entirely.
// shouldFilter={false} because results still come from the debounced
// /search/ fetch below, not cmdk's own client-side fuzzy filter.
export default function SearchOverlay({ open, onClose }) {
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
      <DialogContent className="overflow-hidden p-0" style={{ maxWidth: 560 }}>
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search number, guest, or hotel…"
            value={q}
            onValueChange={setQ}
          />
          <CommandList>
            {state.kind === "quick" && (
              <div className="s-empty-state">
                <span className="s-empty-title">Type to search</span>
                <span className="s-empty-sub">document number, guest name, or hotel</span>
              </div>
            )}
            {state.kind === "loading" && (
              <div className="search-dots"><span></span><span></span><span></span></div>
            )}
            {state.kind === "error" && (
              <div style={{ padding: 16, textAlign: "center", color: "var(--destructive)", fontSize: 13 }}>
                Search failed.
              </div>
            )}
            {state.kind === "results" && state.data.results.length === 0 && (
              <div className="s-empty-state">
                <span className="s-empty-title">No results</span>
                <span className="s-empty-sub">for &ldquo;{state.data.q}&rdquo;</span>
              </div>
            )}
            {state.kind === "results" && order.map((type) => (
              <CommandGroup key={type} heading={`${TYPE_LABEL[type] || type} (${groups[type].length})`}>
                {groups[type].map((r, i) => (
                  <CommandItem key={i} value={`${type}-${i}`} onSelect={() => { window.location.href = r.url; }}>
                    <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                      <span className="s-label">{r.label}</span>
                      <span className="s-sub">{r.sub}</span>
                    </div>
                    <span className="s-meta" style={{ marginLeft: "auto" }}>{r.meta}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
          <div id="search-hints">
            <span className="search-hint-item"><kbd className="search-hint-kbd">↑↓</kbd> navigate</span>
            <span className="search-hint-item"><kbd className="search-hint-kbd">↵</kbd> select</span>
            <span className="search-hint-item"><kbd className="search-hint-kbd">Esc</kbd> close</span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
