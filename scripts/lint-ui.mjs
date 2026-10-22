// Guards the UI standard in CLAUDE.md: pages and components style themselves
// with Tailwind utilities, not with classes from our own CSS files.
//
//   node scripts/lint-ui.mjs            check (exit 1 on new violations)
//   node scripts/lint-ui.mjs --report   list every file with its counts
//   node scripts/lint-ui.mjs --shrink   lower allowlist counts to today's (never raises)
//
// A violation is: a <style> block in JSX, an import of a .css file (outside
// main.jsx), or a class name in className/cn() that has a selector in
// frontend/styles/*.css. Files still being migrated are listed in
// scripts/lint-ui-allowlist.json with their current count; that count may only
// go down.
import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const FE = join(ROOT, "frontend");
const ALLOW = join(ROOT, "scripts/lint-ui-allowlist.json");
const SKIP = [/^frontend\/pages\/Landing\//, /^frontend\/components\/landing\//, /^frontend\/main\.jsx$/];

const walk = (dir) => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  return statSync(p).isDirectory() ? walk(p) : [p];
});

// Every class that has a selector in our own stylesheets.
const custom = new Set();
for (const css of walk(join(FE, "styles")).filter((p) => p.endsWith(".css"))) {
  const src = readFileSync(css, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{[^{}]*\}/g, "{}");
  for (const m of src.matchAll(/\.(-?[a-zA-Z_][\w-]*)/g)) custom.add(m[1]);
}

// Real Tailwind utilities that our CSS also mentions (e.g. `.animate-spin` in
// the reduced-motion guard) are not custom: take the utilities layer of the
// latest build and drop its class names from the set.
const dist = join(ROOT, "hw/static/dist/assets");
const built = existsSync(dist) && readdirSync(dist).filter((f) => /^main-.*\.css$/.test(f))
  .map((f) => join(dist, f)).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
if (built) {
  const css = readFileSync(built, "utf8");
  const at = css.indexOf("@layer utilities{");
  if (at >= 0) {
    let depth = 0, i = css.indexOf("{", at);
    const start = i;
    for (; i < css.length; i++) { if (css[i] === "{") depth++; else if (css[i] === "}" && --depth === 0) break; }
    for (const m of css.slice(start, i).replace(/\{[^{}]*\}/g, "{}").matchAll(/\.(-?[a-zA-Z_][\w-]*)(?![\\\w-])/g)) custom.delete(m[1]);
  }
}

// String literals inside className={...} / className="..." / cn(...) / clsx(...).
function classTokens(src) {
  src = src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[\s;{}(,])\/\/.*$/gm, "$1");
  const out = [];
  for (const m of src.matchAll(/className=|\bcn\(|\bclsx\(/g)) {
    let i = m.index + m[0].length, expr = "";
    if (src[i] === '"' || src[i] === "'") {
      const q = src[i], end = src.indexOf(q, i + 1);
      expr = src.slice(i, end + 1);
    } else {
      let depth = m[0] === "className=" ? 0 : 1;
      const start = i;
      for (; i < src.length; i++) {
        const c = src[i];
        if (c === "{" || c === "(") depth++;
        else if (c === "}" || c === ")") { depth--; if (depth <= 0) break; }
      }
      expr = src.slice(start, i + 1);
    }
    for (const s of expr.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g)) {
      const str = (s[1] ?? s[2] ?? s[3]).replace(/\$\{[^}]*\}/g, " ");
      out.push(...str.split(/\s+/).filter(Boolean));
    }
  }
  return out;
}

const results = {};
for (const file of walk(FE).filter((p) => p.endsWith(".jsx") || p.endsWith(".js"))) {
  const rel = relative(ROOT, file);
  if (SKIP.some((r) => r.test(rel))) continue;
  const src = readFileSync(file, "utf8");
  const styles = (src.match(/<style[\s>]/g) || []).length;
  const imports = (src.match(/^\s*import\s+["'][^"']+\.css["']/gm) || []).length;
  const classes = classTokens(src).filter((t) => custom.has(t));
  const total = styles + imports + classes.length;
  if (total) results[rel] = { total, styles, imports, classes: classes.length, sample: [...new Set(classes)].slice(0, 6) };
}

const allow = existsSync(ALLOW) ? JSON.parse(readFileSync(ALLOW, "utf8")) : {};
const args = process.argv.slice(2);

if (args.includes("--report")) {
  const rows = Object.entries(results).sort((a, b) => b[1].total - a[1].total);
  for (const [f, r] of rows) console.log(`${String(r.total).padStart(4)}  ${f}  (style ${r.styles}, css ${r.imports}, class ${r.classes}: ${r.sample.join(" ")})`);
  console.log(`\n${rows.length} files, ${rows.reduce((n, [, r]) => n + r.total, 0)} violations`);
  process.exit(0);
}

if (args.includes("--shrink") || args.includes("--init")) {
  const next = {};
  for (const [f, r] of Object.entries(results)) {
    if (args.includes("--init")) next[f] = r.total;
    else if (f in allow) next[f] = Math.min(allow[f], r.total);
  }
  writeFileSync(ALLOW, JSON.stringify(Object.fromEntries(Object.entries(next).sort()), null, 2) + "\n");
  console.log(`allowlist: ${Object.keys(next).length} files, ${Object.values(next).reduce((a, b) => a + b, 0)} violations`);
  process.exit(0);
}

const errors = [];
for (const [f, r] of Object.entries(results)) {
  if (!(f in allow)) errors.push(`${f}: ${r.total} new violation(s) (style ${r.styles}, css ${r.imports}, class ${r.classes}: ${r.sample.join(" ")})`);
  else if (r.total > allow[f]) errors.push(`${f}: ${r.total} violations, allowlist says ${allow[f]} (${r.sample.join(" ")})`);
}
const done = Object.keys(allow).filter((f) => !(f in results) || results[f].total < allow[f]);
const left = Object.values(results).reduce((n, r) => n + r.total, 0);
if (errors.length) {
  console.error("lint:ui — styling outside the standard (see CLAUDE.md):\n" + errors.join("\n"));
  process.exit(1);
}
console.log(`lint:ui ok — ${left} legacy violations left in ${Object.keys(results).length} files` + (done.length ? `; ${done.length} file(s) improved, run with --shrink` : ""));
