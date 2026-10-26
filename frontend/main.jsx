import "./styles/tailwind.css";
import axios from "axios";
import { createInertiaApp } from "@inertiajs/react";
import { createRoot } from "react-dom/client";
import AppLayout from "./layouts/AppLayout.jsx";
import { LocaleProvider } from "./utils/i18n.jsx";

axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.xsrfCookieName = "csrftoken";

// Lazy: each page is its own chunk, so the first screen does not download
// every other screen's code. Inertia accepts a promise from `resolve`.
const pages = import.meta.glob("./pages/**/*.jsx");

createInertiaApp({
  resolve: async (name) => {
    const page = (await pages[`./pages/${name}.jsx`]()).default;
    page.layout = page.layout || ((p) => (
      <LocaleProvider>
        <AppLayout>{p}</AppLayout>
      </LocaleProvider>
    ));
    return page;
  },
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />);
  },
});
