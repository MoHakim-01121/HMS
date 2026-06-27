// Shared remittance table styles, used by both Form.jsx and Edit.jsx.
// Single source of truth so the two views stay visually identical
// (previously each page redefined .rem-table / .rem-input / .rem-total-*
// with drifting fonts and spacing).
export const REM_TABLE_CSS = `
.rem-table { width:100%; border-collapse:collapse; }
.rem-table th {
  font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; color:var(--text-3);
  text-transform:uppercase; letter-spacing:.7px;
  padding:8px 12px; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--border);
  background:var(--surface-2);
}
.rem-table th.r { text-align:right; }
.rem-table td { padding:10px 12px; border-bottom:1px solid var(--border); font-size:13px; vertical-align:middle; }
.rem-table tbody tr:last-child td { border-bottom:none; }

.rem-input {
  width:110px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:var(--r);
  color:var(--text); font-size:13px; font-family:'JetBrains Mono',monospace;
  padding:6px 10px; text-align:right;
  transition:border-color .12s;
  display:block; margin-left:auto;
}
.rem-input:focus { outline:none; border-color:var(--accent); }

.rem-total-bar {
  display:flex; align-items:center; justify-content:space-between;
  padding:13px 16px; border-top:1px solid var(--border);
  background:var(--surface-2);
}
.rem-total-label { font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.7px; color:var(--text-3); }
.rem-total-val { font-family:'JetBrains Mono',monospace; font-size:18px; font-weight:700; color:var(--accent-2); }
`;
