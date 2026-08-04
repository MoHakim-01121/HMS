// Shared remittance table styles, used by both Form.jsx and Edit.jsx.
// Single source of truth so the two views stay visually identical
// (previously each page redefined .rem-table / .rem-input / .rem-total-*
// with drifting fonts and spacing).
// Header/cell tokens mirror ui/table.jsx's TableHead/TableCell — the
// originui "complex table made with TanStack Table" reference (21st.dev,
// pinned 2026-07-27): text-muted-foreground, font-medium, no uppercase/mono
// tracking. Kept as plain CSS (not the shared Table components) because
// these rows also carry an inline <input>/proof-link cell shape the shared
// Table wrapper doesn't model — but the surface language now matches.
// Shared remittance form styles — modal sizing so the form gets the same room
// the invoice and services forms do (both widen the shared dialog to 1024px,
// scoped via :has() on their own root class). The reservations table is ten
// columns wide, so at the dialog's default 768px it runs squeezed behind a
// horizontal scrollbar; 1024px minus ~84px of dialog chrome leaves it room.
// :has() scopes the widening to this form — FormModal's DialogContent is shared
// by every form page.
export const REM_FORM_CSS = `
@media (min-width: 1080px) {
  .form-modal-content:has(.rem-form) { max-width: 1024px; }
}
`;

export const REM_TABLE_CSS = `
.rem-table { width:100%; border-collapse:collapse; }
.rem-table th {
  font-size:13px; font-weight:500; color:var(--muted-foreground);
  padding:12px; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--border);
}
.rem-table th.r { text-align:right; }
.rem-table td { padding:12px; border-bottom:1px solid var(--border); font-size:13px; vertical-align:middle; color:var(--foreground); }
.rem-table tbody tr:last-child td { border-bottom:none; }
.rem-table tbody tr:hover { background:var(--muted); }

.rem-input {
  width:110px; background:transparent;
  border:1px solid var(--input); border-radius:calc(var(--radius) - 4px);
  color:var(--foreground); font-size:13px;
  padding:6px 10px; text-align:right;
  transition:border-color .12s;
  display:block; margin-left:auto;
}
.rem-input:focus { outline:none; border-color:var(--ring); }

.rem-total-bar {
  display:flex; align-items:center; justify-content:space-between;
  padding:13px 16px; border-top:1px solid var(--border);
}
.rem-total-label { font-size:13px; font-weight:500; color:var(--muted-foreground); }
.rem-total-val { font-size:18px; font-weight:700; color:var(--foreground); }

.rem-input:disabled { opacity:.5; cursor:not-allowed; }

/* aksi per baris di Edit: hapus reservasi dari transfer, atau batalkan */
.rem-linkbtn {
  background:none; border:none; padding:0; cursor:pointer;
  font-size:12px; color:var(--muted-foreground);
  text-decoration:underline; text-underline-offset:2px;
}
.rem-linkbtn:hover { color:var(--foreground); }
.rem-linkbtn.danger { color:var(--destructive); }
.rem-linkbtn.danger:hover { opacity:.8; }

/* peringatan saat mengedit transfer yang sudah ditandai Received */
.rem-received-note {
  font-size:12.5px; line-height:1.6; color:var(--foreground);
  background:var(--muted); border:1px solid var(--border);
  border-radius:calc(var(--radius) - 2px);
  padding:10px 12px;
}
`;
