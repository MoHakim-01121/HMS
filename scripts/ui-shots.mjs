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
];
const VIEWPORTS = [["d", { width: 1280, height: 900 }], ["m", { width: 390, height: 844 }]];

const exe = join(homedir(), ".cache/ms-playwright/chromium-1148/chrome-linux/chrome");
const browser = await chromium.launch(existsSync(exe) ? { executablePath: exe } : {});
const failed = [];
for (const [vp, viewport] of VIEWPORTS) {
  const contexts = {};
  const pageFor = async (role) => {
    if (!contexts[role]) {
      contexts[role] = await browser.newContext({ viewport, reducedMotion: "reduce", locale: "id-ID" });
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
      const da = px(ia), db = px(ib);
      let diff = 0;
      for (let i = 0; i < da.length; i += 4) if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 24) diff++;
      return { diff, pct: (100 * diff / (da.length / 4)).toFixed(3) };
    }, ["data:image/png;base64," + readFileSync(a).toString("base64"), "data:image/png;base64," + readFileSync(b).toString("base64")]);
    // Sub-pixel bar edges and text anti-aliasing move a few hundred pixels at
    // most between identical renders; anything above 0.05% is a real change.
    const verdict = r.size ? "CHANGED size " + r.size : !r.diff ? "same" : r.pct <= 0.05 ? `noise ${r.diff}px` : `CHANGED ${r.diff}px (${r.pct}%)`;
    rows.push(`${file}\t${verdict}`);
  }
  writeFileSync(join(outDir, "diff.txt"), rows.join("\n") + "\n");
  const changed = rows.filter((r) => r.includes("CHANGED"));
  console.log(`\n${rows.length} compared, ${changed.length} changed` + (changed.length ? "\n" + changed.join("\n") : ""));
}
await browser.close();
if (failed.length) { console.error("\nFAILED\n" + failed.join("\n")); process.exit(1); }
