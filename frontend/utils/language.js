import axios from "axios";
import { router } from "@inertiajs/react";

// Persist the account's language and reload the current Inertia page, so the
// server re-renders every prop (including `locale`) in the new language.
// Shared by the account menu, the language switcher, and the profile page.
export async function saveLanguage(language, reloadOptions) {
  await axios.post("/account/language/", new URLSearchParams({ language }));
  router.reload(reloadOptions);
}
