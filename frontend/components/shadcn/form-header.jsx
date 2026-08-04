import { useContext, useEffect, useRef } from "react";
import { FormModalContext } from "./form-modal.jsx";

export default function FormHeader({ kicker, title, sub }) {
  const ctx = useContext(FormModalContext);
  const inModal = ctx?.inModal;
  const setHeader = ctx?.setHeader;

  // In Homlu's overlay layout the title lives in a fixed header bar above the
  // scrolling body, so inside a dialog this doesn't draw itself — it hands the
  // text up to FormModalProvider, which renders it there. (Before, it simply
  // returned null and the modal opened with no title at all, just a bare stack
  // of fields.) Full-page forms are unaffected and still render below.
  //
  // `sub` is usually an inline fragment — <>{guest_name} — {confirmation}</> —
  // a fresh object on every render, so it can't sit in the dependency array
  // without looping. It only changes when the record does, which is also when
  // title/kicker change, so key the effect on those and read sub off a ref.
  const latest = useRef(null);
  latest.current = { title, sub };

  useEffect(() => {
    if (!inModal || !setHeader) return undefined;
    setHeader(latest.current);
    return () => setHeader(null);
  }, [inModal, setHeader, title, kicker]);

  if (inModal) return null;

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--muted-foreground)" }}>{kicker}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 600, color: "var(--foreground)", letterSpacing: "-0.01em", marginTop: 4 }}>{title}</div>
      {sub && <div style={{ fontSize: 14, color: "var(--muted-foreground)", marginTop: 6 }}>{sub}</div>}
    </div>
  );
}
