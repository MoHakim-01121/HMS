import { getCsrf } from "./csrf.js";

// Thin wrapper for the JSON endpoints that stay on Django
// (global_search, ai_draft_message, attachments, map data).
export async function fetchJson(url, { method = "GET", body, json } = {}) {
  const headers = { "X-CSRFToken": getCsrf() };
  let payload = body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(json);
  }
  const res = await fetch(url, { method, headers, body: payload });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
