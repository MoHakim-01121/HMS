import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const TYPE_LABEL = { CL: "Conf. Letter", INV: "Invoice Hotel", SVC: "Invoice Services" };

// Port of the #search-overlay markup + behaviour from _base.html.
export default function SearchOverlay({ open, onClose }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [state, setState] = useState({ kind: "quick" }); // quick | loading | results | error
  const inputRef = useRef(null);
  const timer = useRef(null);
  const rowRefs = useRef([]);

  useEffect(() => {
    if (open) {
      setQ("");
      setState({ kind: "quick" });
      const timeoutId = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(timeoutId);
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

  if (!open) return null;

  // Centralized so both the input and the result rows share one Escape/Arrow/Enter
  // path — matches the ↑↓/↵ hints shown below instead of leaving them decorative.
  const onPanelKeyDown = (e) => {
    if (e.key === "Escape") { onClose(); return; }
    if (state.kind !== "results") return;
    const els = rowRefs.current.filter(Boolean);
    if (!els.length) return;
    const idx = els.indexOf(document.activeElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      els[idx === -1 ? 0 : Math.min(idx + 1, els.length - 1)].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (idx === -1) els[els.length - 1].focus();
      else if (idx === 0) inputRef.current?.focus();
      else els[idx - 1].focus();
    } else if (e.key === "Enter" && document.activeElement === inputRef.current) {
      e.preventDefault();
      els[0].click();
    }
  };

  rowRefs.current = [];

  return (
    <div id="search-overlay" className="open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="search-panel" onKeyDown={onPanelKeyDown}>
        <div className="search-input-row">
          <Icon name="search" size={15} className="search-icon" />
          <input
            ref={inputRef}
            type="text"
            placeholder={t("Search number, guest, or hotel…")}
            autoComplete="off"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button className="search-clear" aria-label={t("Clear")} onClick={() => setQ("")}>
              <Icon name="close" size={10} strokeWidth={2.5} />
            </button>
          )}
        </div>

        <div id="search-results">
          {state.kind === "quick" && (
            <div className="s-empty-state">
              <Icon name="search" size={32} strokeWidth={1.5} />
              <span className="s-empty-title">{t("Type to search")}</span>
              <span className="s-empty-sub">{t("document number, guest name, or hotel")}</span>
            </div>
          )}
          {state.kind === "loading" && (
            <div className="search-dots"><span></span><span></span><span></span></div>
          )}
          {state.kind === "error" && (
            <div style={{ padding: 16, textAlign: "center", color: "var(--red)", fontSize: 13 }}>
              {t("Search failed.")}
            </div>
          )}
          {state.kind === "results" && <Results data={state.data} registerRef={(i, el) => (rowRefs.current[i] = el)} />}
        </div>

        <div id="search-hints">
          <span className="search-hint-item"><kbd className="search-hint-kbd">↑↓</kbd> {t("navigate")}</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">↵</kbd> {t("select")}</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">Esc</kbd> {t("close")}</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">/</kbd> {t("search")}</span>
        </div>
      </div>
    </div>
  );
}

function Results({ data, registerRef }) {
  const { t } = useI18n();
  if (!data.results.length) {
    return (
      <div className="s-empty-state">
        <Icon name="search" size={32} strokeWidth={1.5} />
        <span className="s-empty-title">{t("No results")}</span>
        <span className="s-empty-sub">{t("for “{q}”", { q: data.q })}</span>
      </div>
    );
  }
  const groups = {};
  const order = [];
  data.results.forEach((r) => {
    if (!groups[r.type]) { groups[r.type] = []; order.push(r.type); }
    groups[r.type].push(r);
  });
  let flatIdx = -1;
  return (
    <>
      {order.map((type) => (
        <div key={type}>
          <div className="s-section-header" data-type={type}>
            {t(TYPE_LABEL[type] || type)}
            <span className="s-section-count">{groups[type].length}</span>
          </div>
          {groups[type].map((r, i) => {
            const idx = ++flatIdx;
            return (
              <a key={i} href={r.url} className="s-row" ref={(el) => registerRef(idx, el)}>
                <span className="s-label">{r.label}</span>
                <span className="s-sub">{r.sub}</span>
                <span className="s-meta">{r.meta}</span>
              </a>
            );
          })}
        </div>
      ))}
    </>
  );
}
