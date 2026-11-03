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
let prefetching = 0;
window.addEventListener("vite:preloadError", (event) => {
  // A background prefetch that fails is ignored: the page is reloaded only
  // when the reader actually opens a page whose code is gone.
  if (prefetching) return;
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

// Once the first screen is up, fetch the other pages' code while the browser
// is idle (cached a year by name), so moving between pages waits only for the
// page's data. Skipped when the reader asked to save data; landing excluded.
// Once per build: after that every chunk sits in the browser cache, and a
// full reload need not evaluate them all again.
const PREFETCH_KEY = "konoz:prefetched";
function prefetchPages() {
  if (navigator.connection?.saveData) return;
  try {
    if (localStorage.getItem(PREFETCH_KEY) === import.meta.url) return;
    localStorage.setItem(PREFETCH_KEY, import.meta.url);
  } catch {
    return;
  }
  const loads = Object.entries(pages).filter(([path]) => !path.includes("/Landing/")).map(([, load]) => load);
  prefetching = loads.length;
  for (const load of loads) load().catch(() => {}).finally(() => { prefetching -= 1; });
}
if ("requestIdleCallback" in window) window.requestIdleCallback(prefetchPages, { timeout: 5000 });
else window.setTimeout(prefetchPages, 3000);
