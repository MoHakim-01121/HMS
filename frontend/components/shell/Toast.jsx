import { useEffect, useState } from "react";
import { usePage } from "@inertiajs/react";

export function showToast(msg, kind = "success") {
  window.dispatchEvent(new CustomEvent("show-toast", { detail: { msg, kind } }));
}

export default function Toast() {
  const { props } = usePage();
  const flash = props.flash || {};
  const [items, setItems] = useState([]);

  const addItem = (kind, msg) => {
    const item = { id: Date.now() + Math.random(), kind, msg };
    setItems((cur) => [...cur, item]);
    setTimeout(() => setItems((cur) => cur.filter((i) => i.id !== item.id)), 3200);
  };

  useEffect(() => {
    if (flash.success) addItem("success", flash.success);
    if (flash.error)   addItem("error",   flash.error);
  }, [flash.success, flash.error]);

  useEffect(() => {
    const handler = (e) => addItem(e.detail.kind, e.detail.msg);
    window.addEventListener("show-toast", handler);
    return () => window.removeEventListener("show-toast", handler);
  }, []);

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
