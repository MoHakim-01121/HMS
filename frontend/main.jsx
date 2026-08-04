import "./styles/tailwind.css";
import axios from "axios";
import { createInertiaApp } from "@inertiajs/react";
import { createRoot } from "react-dom/client";
import AppLayout from "./layouts/AppLayout.jsx";
import { LocaleProvider } from "./utils/i18n.jsx";

axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.xsrfCookieName = "csrftoken";

const pages = import.meta.glob("./pages/**/*.jsx", { eager: true });

createInertiaApp({
  resolve: (name) => {
    const page = pages[`./pages/${name}.jsx`].default;
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
