import { useEffect } from "react";
import { usePage } from "@inertiajs/react";
import { toast } from "sonner";
import { Toaster } from "./ui/sonner.jsx";

export function showToast(msg, kind = "success") {
  if (kind === "error") toast.error(msg);
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
