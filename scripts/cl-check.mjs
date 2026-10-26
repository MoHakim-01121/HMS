// One-off visual check for the Client Statement migration: the period picker
// popover and the pagination strip sit behind a click or below the default
// 900px viewport, so the standard ui-shots run does not cover them.
//   node scripts/cl-check.mjs <outdir>
// Output: ui-shots/<outdir>/cl-check-pop.png and cl-check-pag.png (the
// pagination one is skipped when the ledger fits one page).
import { execFileSync } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const [outDir] = process.argv.slice(2);
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(join(ROOT, "ui-shots", outDir), { recursive: true });

const meta = JSON.parse(
  execFileSync(join(ROOT, ".venv-linux/bin/python3"), ["manage.py", "shell"], { cwd: ROOT, input: readFileSync(join(ROOT, "scripts/ui_shots_sessions.py")) })
    .toString().trim().split("\n").pop(),
);
const exe = join(process.env.HOME, ".cache/ms-playwright/chromium-1148/chrome-linux/chrome");
const browser = await chromium.launch({ executablePath: exe });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: "reduce", locale: "id-ID" });
await ctx.addInitScript((t) => localStorage.setItem("theme", t), "dark");
await ctx.addCookies([{ name: meta.cookie, value: meta.sessions.admin, url: "http://localhost:8000" }]);
const page = await ctx.newPage();

const url = `http://localhost:8000/finance/clients/${meta.ids.client}/statement/`;
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);

// 1. the period picker popover
const trigger = page.locator('[aria-haspopup="dialog"]').first();
await trigger.scrollIntoViewIfNeeded();
await trigger.click();
await page.waitForTimeout(400);
const pop = page.locator('[data-slot="popover-content"]').first();
await pop.screenshot({ path: join(ROOT, "ui-shots", outDir, "cl-check-pop.png") });
await page.keyboard.press("Escape");
await page.waitForTimeout(200);

// 2. the pagination strip at the bottom of the card — only when it renders
//    (it returns null when the ledger fits one page).
const pag = page.locator("nav[aria-label='Pagination']");
if (await pag.count()) {
  await pag.scrollIntoViewIfNeeded();
  await page.waitForTimeout(150);
  await pag.screenshot({ path: join(ROOT, "ui-shots", outDir, "cl-check-pag.png") });
  console.log("pagination: shot");
} else {
  console.log("pagination: not rendered (one page)");
}

console.log("done:", outDir);
await browser.close();
