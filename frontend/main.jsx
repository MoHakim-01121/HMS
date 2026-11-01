import "./styles/tailwind.css";
import axios from "axios";
import { createInertiaApp } from "@inertiajs/react";
import { createRoot } from "react-dom/client";
import { ErrorBoundary, PageErrorBoundary } from "./components/shell/ErrorBoundary.jsx";
import AppLayout from "./layouts/AppLayout.jsx";
import { LocaleProvider } from "./utils/i18n.jsx";

axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.xsrfCookieName = "csrftoken";

// A page chunk that will not load usually means a deploy replaced it: reload for
// the new build, at most once a minute so a real outage cannot loop.
const RELOAD_KEY = "konoz:chunk-reload";
window.addEventListener("vite:preloadError", (event) => {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY)) || 0;
    if (Date.now() - last < 60_000) return;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    return;
  }
  event.preventDefault();
  window.location.reload();
});

// Lazy: each page is its own chunk, so the first screen does not download
// every other screen's code. Inertia accepts a promise from `resolve`.
const pages = import.meta.glob("./pages/**/*.jsx");

createInertiaApp({
  resolve: async (name) => {
    const page = (await pages[`./pages/${name}.jsx`]()).default;
    page.layout = page.layout || ((p) => (
      <LocaleProvider>
        <AppLayout><PageErrorBoundary>{p}</PageErrorBoundary></AppLayout>
      </LocaleProvider>
    ));
    return page;
  },
  setup({ el, App, props }) {
    createRoot(el).render(<ErrorBoundary><App {...props} /></ErrorBoundary>);
  },
});
