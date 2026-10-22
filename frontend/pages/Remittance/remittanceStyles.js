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

.rem-input:disabled { opacity:.5; cursor:not-allowed; }

/* peringatan saat mengedit transfer yang sudah ditandai Received */
.rem-received-note {
  font-size:13px; line-height:1.6; color:var(--foreground);
  background:var(--muted); border:1px solid var(--border);
  border-radius:calc(var(--radius) - 2px);
  padding:10px 12px;
}
`;

// Catat Penerimaan / Ubah alokasi (Receipt.jsx + AllocationTable.jsx).
// Pola dua panel yang sama dengan Invoice/CL form: kolom utama + rail 300px.
// Di bawah 1100px rail turun ke bawah dan menempel di dasar modal, jadi total
// alokasi + tombol simpan tetap terlihat saat menggulir daftar reservasi.
export const RECEIPT_CSS = `
@media (min-width: 1100px) {
  .form-modal-content:has(.rcp-form) { max-width: 1120px; }
}
.rcp-form form { margin-top: 22px; }
.hms-modal-body .rcp-form form { margin-top: 0; }

.rcp-card {
  display: flex; align-items: stretch;
  border: 1px solid var(--border); border-radius: var(--radius-card, 22px);
  background: var(--card);
}
.hms-modal-body .rcp-card { border: none; border-radius: 0; margin: -24px -20px; }
.rcp-main { flex: 1; min-width: 0; padding: 24px 28px; display: flex; flex-direction: column; gap: 22px; }

.rcp-alert {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; border-radius: 12px; font-size: 13px;
  color: var(--red); background: color-mix(in oklch, var(--red) 8%, var(--card));
  border: 1px solid color-mix(in oklch, var(--red) 30%, var(--border));
}

.rcp-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.rcp-fields [data-slot="form-field"] label,
.rcp-lbl {
  font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground);
}
.rcp-fixed { display: flex; flex-direction: column; gap: 6px; grid-column: 1 / -1; }
.rcp-fixed-v { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }

.rcp-alloc { display: flex; flex-direction: column; gap: 12px; }
.rcp-alloc-h { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.rcp-alloc-title { margin: 0; font-size: 13px; font-weight: 600; color: var(--foreground); }
.rcp-alloc-desc { margin: 3px 0 0; font-size: 12px; color: var(--muted-foreground); }
.rcp-alloc-tools { display: flex; align-items: center; gap: 6px; }
.rcp-alloc-tools .search-wrap { width: 250px; height: 36px; }
.rcp-tool {
  height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--card); font: inherit; font-size: 12px; font-weight: 600; color: var(--foreground); cursor: pointer;
}
.rcp-tool:hover { background: var(--muted); }
.rcp-tool:focus-visible, .rcp-cta:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }

.rcp-table-wrap { border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.rcp-table { width: 100%; border-collapse: collapse; }
.rcp-table th { font-size: 12px; font-weight: 500; color: var(--muted-foreground); text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.rcp-table th.r { text-align: right; }
.rcp-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
.rcp-table tbody tr:last-child td { border-bottom: none; }
.rcp-table tr.is-on td { background: color-mix(in oklch, var(--muted) 45%, transparent); }
.rcp-table .rcp-group th {
  padding: 12px 12px 6px; font-size: 12px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase;
  background: color-mix(in oklch, var(--muted) 40%, var(--card));
}
.rcp-res-no { display: block; font-family: var(--font-mono); font-size: 12px; font-weight: 700; }
.rcp-sub { display: block; margin-top: 2px; font-size: 11px; font-weight: 400; color: var(--muted-foreground); white-space: nowrap; }
.rcp-client { font-size: 13px; color: var(--muted-foreground); }
.rcp-date { font-size: 13px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.rcp-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.rcp-in { text-align: right; }
.rcp-in .rem-input[aria-invalid] { border-color: var(--red); }
.rcp-err { display: block; margin-top: 3px; font-size: 11px; color: var(--red); }
.rcp-empty, .rcp-legacy {
  padding: 18px; text-align: center; font-size: 13px; color: var(--muted-foreground);
  border: 1px dashed var(--border); border-radius: 14px; margin: 0;
}

.rcp-rail {
  width: 300px; flex: none; display: flex; flex-direction: column; gap: 16px;
  padding: 24px; border-left: 1px solid var(--border);
  background: color-mix(in oklch, var(--muted) 38%, var(--card));
}
.rcp-rows { position: sticky; top: 0; display: flex; flex-direction: column; gap: 9px; font-size: 13px; }
.rcp-row { display: flex; justify-content: space-between; gap: 12px; color: var(--muted-foreground); }
.rcp-row .rcp-num { color: var(--foreground); font-weight: 500; }
.rcp-row-total { padding-top: 9px; border-top: 1px solid var(--border); color: var(--foreground); font-weight: 600; }
.rcp-row-total .rcp-num { font-size: 20px; font-weight: 600; letter-spacing: -.02em; }
.rcp-note { margin: 0; font-size: 12px; line-height: 1.5; padding: 9px 11px; border-radius: 10px; }
.rcp-note.is-muted { color: var(--muted-foreground); background: var(--card); border: 1px solid var(--border); }
.rcp-note.is-warn { color: var(--foreground); background: color-mix(in oklch, var(--muted) 55%, var(--card)); border: 1px solid var(--border); }
.rcp-note.is-err { color: var(--red); background: color-mix(in oklch, var(--red) 8%, var(--card)); border: 1px solid color-mix(in oklch, var(--red) 30%, var(--border)); }
/* Rail stretches as tall as the reservation list; keep Save in view at the
   bottom of the scroll area instead of at the end of that list. */
.rcp-actions {
  margin-top: auto; position: sticky; bottom: 0;
  margin-inline: -24px; margin-bottom: -24px; padding: 16px 24px 24px;
  background: color-mix(in oklch, var(--muted) 38%, var(--card));
}
.rcp-cta {
  width: 100%; height: 42px; border: none; border-radius: 12px;
  background: var(--primary); color: var(--primary-foreground);
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
}
.rcp-cta:hover { background: var(--primary-hover); }
.rcp-cta:disabled { opacity: .55; cursor: not-allowed; }

@media (max-width: 1099px) {
  .rcp-card { flex-direction: column; }
  .rcp-main { padding: 20px; }
  .rcp-rail {
    position: sticky; bottom: 0; z-index: 2; width: auto; gap: 10px; padding: 14px 20px;
    border-left: none; border-top: 1px solid var(--border);
  }
  .rcp-rows { position: static; }
  .rcp-actions { position: static; margin: 0; padding: 0; background: none; }
  .rcp-row-full { display: none; }
  .rcp-row-total { padding-top: 0; border-top: none; }
  .rcp-row-total .rcp-num { font-size: 17px; }
}
@media (max-width: 700px) {
  .rcp-fields { grid-template-columns: 1fr; }
  .rcp-rail { gap: 8px; padding: 12px 16px; }
  .rcp-rail .rcp-row:not(.rcp-row-total) { display: none; }
  .rcp-cta { height: 40px; }
  .rcp-alloc-tools { width: 100%; }
  .rcp-alloc-tools .search-wrap { flex: 1; width: auto; min-width: 0; }
  .rcp-table thead { display: none; }
  .rcp-table, .rcp-table tbody { display: block; }
  .rcp-table tr:not(.rcp-group) {
    display: grid; grid-template-columns: 1fr auto; gap: 2px 12px;
    padding: 10px 12px; border-bottom: 1px solid var(--border);
  }
  .rcp-table .rcp-group { display: block; }
  .rcp-table .rcp-group th { display: block; }
  .rcp-table td { padding: 0; border: none; }
  .rcp-table .rcp-res { grid-column: 1; }
  .rcp-table .rcp-num { grid-column: 2; grid-row: 1; }
  .rcp-table .rcp-client, .rcp-table .rcp-date { grid-column: 1; font-size: 12px; }
  .rcp-table .rcp-in { grid-column: 1 / -1; margin-top: 8px; }
  .rcp-table .rcp-in .rem-input { width: 100%; }
}
`;
