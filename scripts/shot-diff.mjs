// Localize screenshot differences as text: bands of rows where the two PNGs
// differ, with the x-range inside each band. Usage:
//   node scripts/shot-diff.mjs ui-shots/head/dash-manager-d.png ui-shots/current/dash-manager-d.png
import { readFileSync } from "node:fs";
import { chromium } from "playwright";
import { homedir } from "node:os";
import { join } from "node:path";
import { existsSync } from "node:fs";

const [a, b] = process.argv.slice(2);
const exe = join(homedir(), ".cache/ms-playwright/chromium-1148/chrome-linux/chrome");
const browser = await chromium.launch(existsSync(exe) ? { executablePath: exe } : {});
const page = await browser.newPage();
const out = await page.evaluate(async ([a, b]) => {
  const load = (src) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = src; });
  const [ia, ib] = await Promise.all([load(a), load(b)]);
  const W = Math.min(ia.width, ib.width), H = Math.min(ia.height, ib.height);
  const px = (img) => { const c = document.createElement("canvas"); c.width = W; c.height = H; const x = c.getContext("2d"); x.drawImage(img, 0, 0); return x.getImageData(0, 0, W, H).data; };
  const da = px(ia), db = px(ib);
  const rowHits = new Array(H).fill(0);
  const xs = new Array(H).fill(null);
  let total = 0;
  for (let y = 0; y < H; y++) {
    let n = 0, xmin = W, xmax = 0;
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 24) {
        n++; if (x < xmin) xmin = x; if (x > xmax) xmax = x;
      }
    }
    total += n;
    rowHits[y] = n; xs[y] = n ? [xmin, xmax] : null;
  }
  // Group rows with hits into bands, allowing gaps of 6 rows.
  const bands = [];
  let start = -1, gap = 0;
  for (let y = 0; y <= H; y++) {
    const hit = y < H && rowHits[y] > 0;
    if (hit) { if (start < 0) start = y; gap = 0; }
    else if (start >= 0 && ++gap > 6) { bands.push([start, y - gap]); start = -1; gap = 0; }
  }
  if (start >= 0) bands.push([start, H - 1]);
  return {
    sizes: [`${ia.width}x${ia.height}`, `${ib.width}x${ib.height}`],
    total,
    bands: bands.map(([y0, y1]) => {
      let xmin = W, xmax = 0, n = 0;
      for (let y = y0; y <= y1; y++) { n += rowHits[y]; if (xs[y]) { xmin = Math.min(xmin, xs[y][0]); xmax = Math.max(xmax, xs[y][1]); } }
      return `rows ${y0}-${y1} (${y1 - y0 + 1}h)  x ${xmin}-${xmax}  ${n} px`;
    }),
  };
}, ["data:image/png;base64," + readFileSync(a).toString("base64"), "data:image/png;base64," + readFileSync(b).toString("base64")]);
console.log(out.sizes.join(" -> "));
console.log("raw diff px:", out.total);
for (const b of out.bands) console.log(b);
await browser.close();
