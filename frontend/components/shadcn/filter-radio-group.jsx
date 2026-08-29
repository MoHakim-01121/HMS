import { useRef } from "react";
import { useI18n } from "../../utils/i18n.jsx";

// Single-select option list used inside the list pages' filter panel.
// Implements the WAI-ARIA radiogroup keyboard pattern: one tab stop for the
// whole group (roving tabindex), Arrow keys move + select, Home/End jump to
// the ends. Replaces the copy-pasted markup that put tabIndex={0} on every
// option and only handled Enter/Space.
//
//   options: [{ val, label, cls }]  — `cls` is the per-option colour class
//   value:   currently selected `val`
//   onChange(val)
//   dot:     render the leading `.fp-status-dot` (Hotel / Remittance style)
export default function FilterRadioGroup({ label, options, value, onChange, dot = false }) {
  const { t } = useI18n();
  const refs = useRef([]);

  const move = (from, delta) => {
    const next = (from + delta + options.length) % options.length;
    refs.current[next]?.focus();
    onChange(options[next].val);
  };

  const onKeyDown = (e, i) => {
    switch (e.key) {
      case "ArrowDown":
      case "ArrowRight":
        e.preventDefault();
        move(i, 1);
        break;
      case "ArrowUp":
      case "ArrowLeft":
        e.preventDefault();
        move(i, -1);
        break;
      case "Home":
        e.preventDefault();
        refs.current[0]?.focus();
        onChange(options[0].val);
        break;
      case "End":
        e.preventDefault();
        refs.current[options.length - 1]?.focus();
        onChange(options[options.length - 1].val);
        break;
      case " ":
      case "Enter":
        e.preventDefault();
        onChange(options[i].val);
        break;
      default:
        break;
    }
  };

  // Roving tabindex: the selected option is the tab stop; if nothing is
  // selected yet, the first option is.
  const activeIndex = Math.max(0, options.findIndex((o) => o.val === value));

  return (
    <div className="fp-status-group" role="radiogroup" aria-label={label}>
      {options.map((o, i) => {
        const selected = value === o.val;
        return (
          <div
            key={o.val}
            ref={(el) => { refs.current[i] = el; }}
            className={`fp-status-opt ${o.cls}${selected ? " selected" : ""}`}
            role="radio"
            aria-checked={selected}
            tabIndex={i === activeIndex ? 0 : -1}
            onClick={() => onChange(o.val)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {dot && <span className="fp-status-dot" />}
            <span className="fp-status-opt-label">{t(o.label)}</span>
          </div>
        );
      })}
    </div>
  );
}
