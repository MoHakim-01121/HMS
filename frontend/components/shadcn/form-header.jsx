import { useContext, useEffect, useRef } from "react";
import { FormModalContext } from "./form-modal.jsx";

// `layout`: "a" for the approved CL/Invoice form layout (form-a.jsx), which
// the dialog frames a little differently.
export default function FormHeader({ kicker, title, sub, layout }) {
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
  latest.current = { title, sub, layout };

  useEffect(() => {
    if (!inModal || !setHeader) return undefined;
    setHeader(latest.current);
    return () => setHeader(null);
  }, [inModal, setHeader, title, kicker, layout]);

  if (inModal) return null;

  return (
    <div>
      <div className="text-[13px] font-medium text-muted-foreground">{kicker}</div>
      <div className="mt-1 font-display text-[32px] font-semibold tracking-[-0.01em] text-foreground">{title}</div>
      {sub && <div className="mt-1.5 text-[14px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
