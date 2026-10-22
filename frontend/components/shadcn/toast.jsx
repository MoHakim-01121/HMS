import { useEffect } from "react";
import { usePage } from "@inertiajs/react";
import { toast } from "sonner";
import { Toaster } from "./ui/sonner.jsx";

// An error usually says why something was refused and what to do instead —
// too much to read in Sonner's default 4 s. It stays 10 s and can be closed.
export function showToast(msg, kind = "success") {
  if (kind === "error") toast.error(msg, { duration: 10000, closeButton: true });
  else toast.success(msg);
}

// shadcn/Sonner rebuild of ../shell/Toast.jsx — same showToast() signature,
// same behavior of also surfacing Django flash.success/flash.error on mount.
export default function Toast() {
  const { props } = usePage();
  const flash = props.flash || {};

  useEffect(() => {
    if (flash.success) showToast(flash.success, "success");
    if (flash.error) showToast(flash.error, "error");
  }, [flash.success, flash.error]);

  return <Toaster />;
}
