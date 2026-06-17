// Read Django's CSRF token from the cookie for fetch() POSTs.
export function getCsrf() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}
