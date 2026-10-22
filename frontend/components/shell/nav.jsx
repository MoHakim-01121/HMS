// Shell navigation: Home and Calendar on top, then groups that fold (canvas
// "SidebarTree"). `perm` gates an item on the user's module permissions.

const P = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const NAV_ICONS = {
  home: <path d="M3 11l9-7 9 7M5 10v10h5v-6h4v6h5V10" />,
  calendar: <path d="M4 6h16v14H4zM4 10h16M8 3v4M16 3v4" />,
  cl: <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 14l2 2 4-4" />,
  invoice: <path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6" />,
  clients: <path d="M9 11a4 4 0 100-8 4 4 0 000 8zM2 21c0-4 3-6 7-6s7 2 7 6M16 3.5a4 4 0 010 7.5M18 15c2.5.5 4 2.5 4 6" />,
  hotels: <path d="M4 21V5l8-2v18M12 9h8v12M8 8v.01M8 12v.01M8 16v.01M16 13v.01M16 17v.01M2 21h20" />,
  services: <path d="M4 7h16v13H4zM9 7V4h6v3M4 12h16" />,
  payments: <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v3h16v-3" />,
  expenses: <path d="M3 12V4h8l10 10-8 8zM7.5 8.5v.01" />,
  remittance: <path d="M12 15V3m0 0l-4 4m4-4l4 4M4 17v3h16v-3" />,
  exchanges: <path d="M4 8h14m0 0l-4-4m4 4l-4 4M20 16H6m0 0l4-4m-4 4l4 4" />,
  credit_notes: <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 15h6" />,
  statements: <path d="M5 4h11a3 3 0 013 3v13H8a3 3 0 01-3-3zM5 17a3 3 0 013-3h11" />,
  bank_accounts: <path d="M3 10l9-6 9 6M5 10v8M10 10v8M14 10v8M19 10v8M3 21h18" />,
  reconciliation: <path d="M4 12a8 8 0 0114-5.3M20 12a8 8 0 01-14 5.3M18 3v4h-4M6 21v-4h4" />,
  fund_flow: <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />,
  branch_report: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  ar_aging: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  penalties: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5v5M12 16v.01" /></>,
  journal: <path d="M5 4h14v16H5zM9 8h6M9 12h6M9 16h4" />,
  trial_balance: <path d="M12 4v16M6 20h12M4 7h16M6 7l-3 6h6zM18 7l-3 6h6z" />,
  periods: <path d="M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M9 14h2M13 14h2M9 17h2" />,
  users: <path d="M9 11a4 4 0 100-8 4 4 0 000 8zM2 21c0-4 3-6 7-6s7 2 7 6M16 3.5a4 4 0 010 7.5M18 15c2.5.5 4 2.5 4 6" />,
  roles: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />,
  // Group rows in the sidebar.
  grp_ops: <path d="M4 7h16v13H4zM9 7V4h6v3M4 12h16" />,
  grp_fin: <path d="M3 7h18v12H3zM3 7l3-3h12l3 3M16 13h2" />,
  grp_rep: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  grp_books: <path d="M4 5a2 2 0 012-2h14v16H6a2 2 0 00-2 2zM4 21V5M9 8h6" />,
  grp_data: <path d="M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />,
  grp_adm: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9.5 12l2 2 3.5-4" />,
};

export function NavIcon({ name }) {
  return <svg {...P}>{NAV_ICONS[name]}</svg>;
}

export const NAV_TOP = [
  { key: "home", label: "Home", href: "/dashboard/" },
  { key: "calendar", label: "Calendar", href: "/calendar/", perm: "calendar" },
];

// Grouped by what the work is (as Xero, Odoo and Zoho Books do): the daily work
// from CL to a client's payment, the branch's own money, reports to read, the
// books Finance keeps, master data, admin. Each group has its own icon.
export const NAV_GROUPS = [
  { id: "ops", heading: "Operations", icon: "grp_ops", items: [
    { key: "cl", label: "Confirmation Letter", href: "/cl/", perm: "cl" },
    { key: "invoice", label: "Invoice", href: "/invoice/", perm: "invoice" },
    { key: "payments", label: "Payments", href: "/finance/payments/", perm: "payments" },
    { key: "credit_notes", label: "Credit Notes", href: "/finance/credit-notes/", perm: "invoice" },
    { key: "statements", label: "Client Ledger", href: "/finance/statements/", perm: "statements" },
    { key: "penalties", label: "Penalties", href: "/finance/penalties/", perm: "penalty" },
  ] },
  { id: "fin", heading: "Finance", icon: "grp_fin", items: [
    { key: "bank_accounts", label: "Bank and Cash", href: "/finance/bank-accounts/", perm: "bank" },
    { key: "expenses", label: "Expenses", href: "/finance/expenses/", perm: "expenses" },
    { key: "exchanges", label: "Transfer and Exchange", href: "/finance/exchanges/", perm: "bank" },
    { key: "remittance", label: "Remittance", href: "/remittance/", perm: "remittance" },
    { key: "reconciliation", label: "Bank Reconciliation", href: "/finance/reconciliation/", perm: "bank" },
  ] },
  { id: "rep", heading: "Reports", icon: "grp_rep", items: [
    { key: "branch_report", label: "Branch report", href: "/finance/branch-report/", perm: "branch_report" },
    { key: "fund_flow", label: "Fund Flow", href: "/finance/fund-flow/", perm: "statements" },
    { key: "ar_aging", label: "AR Aging", href: "/finance/ar-aging/", perm: "statements" },
    { key: "trial_balance", label: "Trial Balance", href: "/finance/trial-balance/", perm: "journal" },
  ] },
  { id: "books", heading: "Books", icon: "grp_books", items: [
    { key: "journal", label: "Journal Entries", href: "/finance/journal/", perm: "journal" },
    { key: "periods", label: "Financial Periods", href: "/finance/periods/", perm: "periods" },
  ] },
  { id: "data", heading: "Data", icon: "grp_data", items: [
    { key: "clients", label: "Clients", href: "/clients/", perm: "clients" },
    { key: "hotels", label: "Hotels", href: "/hotels/", perm: "hotels" },
  ] },
  { id: "adm", heading: "Admin", icon: "grp_adm", items: [
    { key: "users", label: "Users", href: "/users/", perm: "users" },
    { key: "roles", label: "Roles", href: "/roles/", perm: "users" },
  ] },
];

export const DEFAULT_OPEN = { ops: true, fin: true, rep: false, books: false, data: false, adm: false };

export const allowed = (perms) => (it) => !it.perm || (perms[it.perm] || []).length > 0;

// Every page the user may open, for the search's "Pages" group.
export function navPages(perms) {
  const ok = allowed(perms);
  return [...NAV_TOP, ...NAV_GROUPS.flatMap((g) => g.items)].filter(ok);
}
