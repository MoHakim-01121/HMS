import { useEffect, useState } from "react";

// Dark default + light toggle, persisted in localStorage — same behaviour as
// the inline script in base_inertia.html. The browser bar on a phone takes
// the canvas colour (--background) through <meta name="theme-color">.
const BAR = { light: "#F2F3EC", dark: "#111310" };
export function useTheme() {
  const [theme, setTheme] = useState(
    () => (typeof localStorage !== "undefined" && localStorage.getItem("theme")) || "dark"
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BAR[theme] || BAR.dark);
    localStorage.setItem("theme", theme);
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  return { theme, toggle };
}
