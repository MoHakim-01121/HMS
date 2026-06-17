import { useEffect, useState } from "react";

// Dark default + light toggle, persisted in localStorage — same behaviour as
// the inline script in the old _base.html.
export function useTheme() {
  const [theme, setTheme] = useState(
    () => (typeof localStorage !== "undefined" && localStorage.getItem("theme")) || "dark"
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  return { theme, toggle };
}
