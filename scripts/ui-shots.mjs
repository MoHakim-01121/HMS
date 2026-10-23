// Screenshots of the key app pages, per role and viewport, for checking that
// the Tailwind migration leaves every page looking the same.
//
//   node scripts/ui-shots.mjs baseline            -> ui-shots/baseline/*.png
//   node scripts/ui-shots.mjs current --compare   -> ui-shots/current/*.png + diff report
//   node scripts/ui-shots.mjs current --only=dash  (substring filter on shot names)
//
// Needs the local dev stack running (runserver :8000 + vite :5173) and logs in
// through sessions minted by scripts/ui_shots_sessions.py.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, existsSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BASE = process.env.UI_SHOTS_URL || "http://localhost:8000";
const [name = "current", ...flags] = process.argv.slice(2);
const compare = flags.includes("--compare");
const only = (flags.find((f) => f.startsWith("--only=")) || "").slice(7);
const outDir = join(ROOT, "ui-shots", name);
mkdirSync(outDir, { recursive: true });

const py = join(ROOT, ".venv-linux/bin/python3");
const meta = JSON.parse(
  execFileSync(py, ["manage.py", "shell"], { cwd: ROOT, input: readFileSync(join(ROOT, "scripts/ui_shots_sessions.py")) })
    .toString().trim().split("\n").pop(),
);
const id = meta.ids;

// [shot name, role, path]
const PAGES = [
  ["dash-admin", "admin", "/dashboard/"],
  ["dash-manager", "manager", "/dashboard/"],
  ["dash-finance", "finance", "/dashboard/"],
  ["dash-staff", "staff", "/dashboard/"],
  ["cl-list", "admin", "/cl/"],
  ["cl-new", "admin", "/cl/new/"],
  ["cl-detail", "admin", `/cl/${id.cl}/`],
  ["invoice-list", "admin", "/invoice/"],
  ["invoice-new", "admin", "/invoice/new/"],
  ["invoice-detail", "admin", `/invoice/${id.invoice}/`],
  ["payment-list", "admin", "/finance/payments/"],
  ["payment-detail", "admin", `/finance/payments/${id.payment}/`],
  ["expense-list", "admin", "/finance/expenses/"],
  ["expense-detail", "admin", `/finance/expenses/${id.expense}/`],
  ["client-list", "admin", "/clients/"],
  ["client-detail", "admin", `/clients/${id.client}/`],
  ["hotel-list", "admin", "/hotels/"],
  ["hotel-new", "admin", "/hotels/new/"],
  ["hotel-detail", "admin", `/hotels/${id.hotel}/`],
  ["bank-accounts", "admin", "/finance/bank-accounts/"],
  ["branch-report", "admin", "/finance/branch-report/"],
  ["ar-aging", "admin", "/finance/ar-aging/"],
  ["remittance-list", "admin", "/remittance/"],
  ["remittance-detail", "admin", `/remittance/${id.remittance}/`],
  ["role-new", "admin", "/roles/new/"],
  ["profile", "admin", "/account/profile/"],
  ["calendar", "admin", "/calendar/"],
  ["client-new", "admin", "/clients/new/"],
  ["credit-notes", "admin", "/finance/credit-notes/"],
  ["exchanges", "admin", "/finance/exchanges/"],
  ["fund-flow", "admin", "/finance/fund-flow/"],
  ["journal", "admin", "/finance/journal/"],
  ["statements", "admin", "/finance/statements/"],
  ["trial-balance", "admin", "/finance/trial-balance/"],
  ["claims", "admin", "/finance/claims/"],
  ["penalties", "admin", "/finance/penalties/"],
  ["periods", "admin", "/finance/periods/"],
  ["reconciliation", "admin", "/finance/reconciliation/"],
  ["roles", "admin", "/roles/"],
  ["users", "admin", "/users/"],
  ["cl-edit", "admin", `/cl/${id.cl}/edit/`],
  ["invoice-edit", "admin", `/invoice/${id.invoice}/edit/`],
  ["credit-note-new", "admin", `/finance/invoices/${id.invoice}/credit-notes/new/`],
  ["client-refund", "admin", `/finance/clients/${id.client}/refund/`],
  ["deposit-transfer", "admin", `/finance/clients/${id.client}/deposit-transfer/`],
  ["expense-record", "admin", "/finance/expenses/record/"],
  ["payment-record", "admin", "/finance/payments/record/"],
  ["exchange-new", "admin", "/finance/exchanges/new/"],
  ["remittance-new", "admin", "/remittance/new/"],
  ["remittance-edit", "admin", `/remittance/${id.remittance}/edit/`],
  ["bank-account-new", "admin", "/finance/bank-accounts/new/"],
  ["user-new", "admin", "/users/new/"],
  ["claim-new", "admin", "/finance/claims/new/"],
].filter(([, , path]) => !path.includes("/null/")); // no such record locally

// Open overlays (menus, selects, dialogs): [shot name, role, path, clicks].
// Shot at viewport size, since overlays are fixed to it. Nothing here submits:
// "Delete" only opens the confirmation, which is never confirmed.
const ROW_MENU = '[data-slot="popover-trigger"] >> nth=-1';
const ACTIONS = [
  ["open-select", "admin", "/clients/new/", ['[data-slot="select-trigger"] >> nth=0']],
  ["open-branch-select", "admin", "/finance/branch-report/", ['[data-slot="select-trigger"]']],
  ["open-picker", "admin", "/cl/new/", ['[data-slot="popover-trigger"] >> nth=0']],
  ["open-row-menu", "admin", "/users/", [ROW_MENU]],
  ["dialog-reset-password", "admin", "/users/", [ROW_MENU, "text=Reset password"]],
  ["dialog-access", "admin", "/users/", [ROW_MENU, "text=Manage access"]],
  ["dialog-access-select", "admin", "/users/", [ROW_MENU, "text=Manage access", '[role="dialog"] [data-slot="select-trigger"]']],
  ["dialog-confirm-delete", "admin", "/users/", [ROW_MENU, "text=Delete"]],
  ["search-overlay", "admin", "/cl/", ['#m-top-bar [aria-label="Search"]'], "m"],
  ["list-filter", "admin", "/cl/", ['button:has-text("Filter")']],
  ["form-dates", "admin", "/cl/new/", ['button[aria-haspopup="dialog"]:has-text("Check-in")']],
  ["form-date", "admin", "/finance/payments/record/", ['button[aria-haspopup="dialog"] >> nth=0']],
  ["form-cell-picker", "admin", `/cl/${id.cl}/edit/`, ['button[aria-label="Room type"]']],
  ["list-export", "admin", "/invoice/", ['button:has-text("Export")']],
  ["list-year", "admin", "/cl/", ['button[aria-haspopup="menu"]:has-text("2026")']],
  ["list-perpage", "admin", "/cl/", ['button[aria-haspopup="menu"]:has-text("10")']],
  ["list-kpi-flip", "admin", "/finance/payments/", ['button[aria-label^="Cash received"]']],
  ["list-kpi-press", "admin", "/finance/payments/", ['button[aria-pressed]:has-text("Unapplied cash")']],
];
// [suffix, viewport, theme]: dark is what the app ships with; light desktop
// catches the light-only token rules.
const VIEWPORTS = [["d", { width: 1280, height: 900 }, "dark"], ["m", { width: 390, height: 844 }, "dark"], ["dl", { width: 1280, height: 900 }, "light"]];

const exe = join(homedir(), ".cache/ms-playwright/chromium-1148/chrome-linux/chrome");
const browser = await chromium.launch(existsSync(exe) ? { executablePath: exe } : {});
const failed = [];
for (const [vp, viewport, theme] of VIEWPORTS) {
  const contexts = {};
  const pageFor = async (role) => {
    if (!contexts[role]) {
      contexts[role] = await browser.newContext({ viewport, reducedMotion: "reduce", locale: "id-ID" });
      await contexts[role].addInitScript((t) => localStorage.setItem("theme", t), theme);
      await contexts[role].addCookies([{ name: meta.cookie, value: meta.sessions[role], url: BASE }]);
    }
    return contexts[role].newPage();
  };
  for (const [shot, role, path] of PAGES) {
    const file = `${shot}-${vp}.png`;
    if (only && !file.includes(only)) continue;
    const page = await pageFor(role);
    try {
      const res = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 30000 });
      if (!res || res.status() >= 400 || new URL(page.url()).pathname.includes("login")) throw new Error(`HTTP ${res?.status()} at ${page.url()}`);
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the page instead of fullPage: fullPage stretches
      // the canvas past the viewport and uncovers sheets parked off-screen.
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.setViewportSize({ width: viewport.width, height: Math.max(viewport.height, height) });
      await page.waitForTimeout(300);
      await page.screenshot({ path: join(outDir, file) });
      console.log("shot", file);
    } catch (e) {
      failed.push(`${file}: ${e.message}`);
    } finally {
      await page.close();
    }
  }
  for (const [shot, role, path, clicks, onlyVp] of ACTIONS) {
    const file = `${shot}-${vp}.png`;
    if ((only && !file.includes(only)) || (onlyVp && onlyVp !== vp)) continue;
    const page = await pageFor(role);
    try {
      await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 30000 });
      await page.evaluate(() => document.fonts.ready);
      for (const sel of clicks) {
        await page.locator(sel).first().click({ timeout: 5000 });
        await page.waitForTimeout(350);
      }
      await page.mouse.move(0, 0);
      await page.waitForTimeout(150);
      await page.screenshot({ path: join(outDir, file) });
      console.log("shot", file);
    } catch (e) {
      failed.push(`${file}: ${e.message.split("\n")[0]}`);
    } finally {
      await page.close();
    }
  }
  for (const c of Object.values(contexts)) await c.close();
}

if (compare) {
  // Pixel diff in the browser: count pixels whose RGB differs by more than a
  // small tolerance (anti-aliasing), and size changes.
  const page = await browser.newPage();
  const rows = [];
  for (const [shot] of [...PAGES, ...ACTIONS]) for (const [vp] of VIEWPORTS) {
    const file = `${shot}-${vp}.png`;
    const a = join(ROOT, "ui-shots/baseline", file), b = join(outDir, file);
    if ((only && !file.includes(only)) || !existsSync(a) || !existsSync(b)) continue;
    const r = await page.evaluate(async ([a, b]) => {
      const load = (src) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = src; });
      const [ia, ib] = await Promise.all([load(a), load(b)]);
      if (ia.width !== ib.width || ia.height !== ib.height) return { size: `${ia.width}x${ia.height} -> ${ib.width}x${ib.height}` };
      const px = (img) => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; const x = c.getContext("2d"); x.drawImage(img, 0, 0); return x.getImageData(0, 0, c.width, c.height).data; };
      const da = px(ia), db = px(ib), W = ia.width, H = ia.height;
      let diff = 0;
      for (let i = 0; i < da.length; i += 4) if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 24) diff++;
      // Text rasterised a touch differently (another compositing layer, a
      // sub-pixel offset) differs at glyph edges only. A 3x3 box blur of the
      // grey levels removes that; what still differs by more than 40 is real.
      const grey = (d) => { const g = new Float32Array(W * H); for (let i = 0; i < W * H; i++) g[i] = (d[i * 4] * 0.3 + d[i * 4 + 1] * 0.59 + d[i * 4 + 2] * 0.11); return g; };
      const blur = (g) => { const o = new Float32Array(W * H); for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { let s = 0; for (let j = -1; j <= 1; j++) for (let k = -1; k <= 1; k++) s += g[(y + j) * W + x + k]; o[y * W + x] = s / 9; } return o; };
      let strong = 0;
      if (diff) { const ga = blur(grey(da)), gb = blur(grey(db)); for (let i = 0; i < W * H; i++) if (Math.abs(ga[i] - gb[i]) > 40) strong++; }
      return { diff, strong, pct: (100 * diff / (da.length / 4)).toFixed(3) };
    }, ["data:image/png;base64," + readFileSync(a).toString("base64"), "data:image/png;base64," + readFileSync(b).toString("base64")]);
    // Raw pixel differences that vanish once blurred are anti-aliasing.
    const verdict = r.size ? "CHANGED size " + r.size : !r.diff ? "same" : !r.strong ? `noise ${r.diff}px` : `CHANGED ${r.strong}px after blur (${r.diff}px raw)`;
    rows.push(`${file}\t${verdict}`);
  }
  writeFileSync(join(outDir, "diff.txt"), rows.join("\n") + "\n");
  const changed = rows.filter((r) => r.includes("CHANGED"));
  console.log(`\n${rows.length} compared, ${changed.length} changed` + (changed.length ? "\n" + changed.join("\n") : ""));
}
await browser.close();
if (failed.length) { console.error("\nFAILED\n" + failed.join("\n")); process.exit(1); }
