import { useEffect, useState } from "react";
import { usePage } from "@inertiajs/react";

export default function Toast() {
  const { props } = usePage();
  const flash = props.flash || {};
  const [items, setItems] = useState([]);

  useEffect(() => {
    const next = [];
    if (flash.success) next.push({ id: Date.now() + "s", kind: "success", msg: flash.success });
    if (flash.error) next.push({ id: Date.now() + "e", kind: "error", msg: flash.error });
    if (!next.length) return;
    setItems((cur) => [...cur, ...next]);
    const t = setTimeout(() => {
      setItems((cur) => cur.filter((i) => !next.some((n) => n.id === i.id)));
    }, 3200);
    return () => clearTimeout(t);
  }, [flash.success, flash.error]);

  if (!items.length) return null;
  return (
    <div style={{ position: "fixed", top: 64, right: 16, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((i) => (
        <div key={i.id} className={"badge " + (i.kind === "error" ? "badge-red" : "badge-green")}
          style={{ padding: "10px 14px", fontSize: 13, boxShadow: "var(--shadow, 0 4px 16px rgba(0,0,0,.25))", borderRadius: "var(--r-sm, 8px)", maxWidth: 320 }}>
          {i.msg}
        </div>
      ))}
    </div>
  );
}
