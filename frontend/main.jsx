import axios from "axios";
import { createInertiaApp } from "@inertiajs/react";
import { createRoot } from "react-dom/client";
import AppLayout from "./layouts/AppLayout.jsx";

// Make Inertia's axios send Django's CSRF header/cookie names.
axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.xsrfCookieName = "csrftoken";

const pages = import.meta.glob("./pages/**/*.jsx", { eager: true });

createInertiaApp({
  resolve: (name) => {
    const page = pages[`./pages/${name}.jsx`].default;
    page.layout = page.layout || ((p) => <AppLayout>{p}</AppLayout>);
    return page;
  },
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />);
  },
});
