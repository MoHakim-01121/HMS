import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons.jsx";

const TYPE_LABEL = { CL: "Conf. Letter", INV: "Invoice Hotel", SVC: "Invoice Services" };

// Port of the #search-overlay markup + behaviour from _base.html.
export default function SearchOverlay({ open, onClose }) {
  const [q, setQ] = useState("");
  const [state, setState] = useState({ kind: "quick" }); // quick | loading | results | error
  const inputRef = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setState({ kind: "quick" });
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
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

  return (
    <div id="search-overlay" className="open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="search-panel">
        <div className="search-input-row">
          <Icon name="search" size={15} className="search-icon" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Cari nomor, tamu, atau hotel…"
            autoComplete="off"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
            }}
          />
          {q && (
            <button className="search-clear" aria-label="Hapus" onClick={() => setQ("")}>
              <Icon name="close" size={10} strokeWidth={2.5} />
            </button>
          )}
        </div>

        <div id="search-results">
          {state.kind === "quick" && (
            <div className="s-empty-state">
              <Icon name="search" size={32} strokeWidth={1.5} />
              <span className="s-empty-title">Ketik untuk mencari</span>
              <span className="s-empty-sub">nomor dokumen, nama tamu, atau hotel</span>
            </div>
          )}
          {state.kind === "loading" && (
            <div className="search-dots"><span></span><span></span><span></span></div>
          )}
          {state.kind === "error" && (
            <div style={{ padding: 16, textAlign: "center", color: "var(--red)", fontSize: 13 }}>
              Gagal mencari.
            </div>
          )}
          {state.kind === "results" && <Results data={state.data} />}
        </div>

        <div id="search-hints">
          <span className="search-hint-item"><kbd className="search-hint-kbd">↑↓</kbd> navigasi</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">↵</kbd> pilih</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">Esc</kbd> tutup</span>
          <span className="search-hint-item"><kbd className="search-hint-kbd">/</kbd> cari</span>
        </div>
      </div>
    </div>
  );
}

function Results({ data }) {
  if (!data.results.length) {
    return (
      <div className="s-empty-state">
        <Icon name="search" size={32} strokeWidth={1.5} />
        <span className="s-empty-title">Tidak ada hasil</span>
        <span className="s-empty-sub">untuk &ldquo;{data.q}&rdquo;</span>
      </div>
    );
  }
  const groups = {};
  const order = [];
  data.results.forEach((r) => {
    if (!groups[r.type]) { groups[r.type] = []; order.push(r.type); }
    groups[r.type].push(r);
  });
  return (
    <>
      {order.map((type) => (
        <div key={type}>
          <div className="s-section-header" data-type={type}>
            {TYPE_LABEL[type] || type}
            <span className="s-section-count">{groups[type].length}</span>
          </div>
          {groups[type].map((r, i) => (
            <a key={i} href={r.url} className="s-row">
              <span className="s-label">{r.label}</span>
              <span className="s-sub">{r.sub}</span>
              <span className="s-meta">{r.meta}</span>
            </a>
          ))}
        </div>
      ))}
    </>
  );
}
