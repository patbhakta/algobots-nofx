// ALG-3260 keyboard-only check + 390/1440 screenshots for /demo.
// Usage: NODE_PATH=<dir with playwright-core> node keyboard.mjs <base-url> <out-dir>
// Needs a running app (any feed) and a Chromium from the Playwright cache.
import { createRequire } from "node:module";
import { globSync } from "node:fs";
import { homedir } from "node:os";

const { chromium } = createRequire(import.meta.url)("playwright-core"); // resolved via NODE_PATH

const [base = "http://127.0.0.1:8763", out = "."] = process.argv.slice(2);
const exe = globSync(`${homedir()}/.cache/ms-playwright/chromium-*/chrome-linux*/chrome`).sort().pop();
const browser = await chromium.launch({ executablePath: exe, args: ["--no-sandbox"] });
const fail = [];
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) fail.push(msg); };

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`${base}/demo#nofocus`); // no autofocus: Tab starts from the top

// Tab reaches every pane control, each with a visible focus ring. A radio group is
// one Tab stop (its checked radio; arrows move within it); disabled controls are skipped.
const controls = await page.$$eval(".grid a, .grid button, .grid input, .grid select, .grid textarea, .grid [tabindex]",
  (els) => els.filter((e) => e.offsetParent && e.tabIndex >= 0 && !e.disabled
      && !(e.type === "radio" && !e.checked))
    .map((e, i) => { e.dataset.kb = String(i); return i; }).length);
const seen = new Set();
let unringed = 0;
for (let i = 0; i < 200; i++) {
  await page.keyboard.press("Tab");
  const f = await page.evaluate(() => {
    const e = document.activeElement;
    if (!e || e === document.body) return null;
    const s = getComputedStyle(e);
    const ring = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== "none";
    return { inGrid: e.dataset.kb !== undefined, id: e.dataset.kb, ring };
  });
  if (!f) break;
  if (f.inGrid) { if (!seen.has(f.id) && !f.ring) unringed++; seen.add(f.id); }
}
check(seen.size === controls && controls > 0, `Tab reached ${seen.size}/${controls} pane controls`);
check(unringed === 0, `visible focus ring on every pane control (${unringed} without)`);

// ↑/↓ + Enter switches account; the next render carries only that account.
await page.goto(`${base}/demo`);
await page.focus("tr.acct.sel");
await page.keyboard.press("ArrowDown");
const target = await page.evaluate(() => document.activeElement.dataset.account);
await Promise.all([page.waitForURL(/account=/), page.keyboard.press("Enter")]);
check(page.url().endsWith(`account=${target}`), `ArrowDown+Enter -> ?account=${target}`);
const foreign = await page.$$eval("[data-order]", (els, t) =>
  els.map((e) => e.dataset.order).filter((id) => !id.startsWith(`${t}:`)), target);
check(foreign.length === 0, `no other-account order ids after switch (${foreign.length})`);
await page.keyboard.press("ArrowUp");
check(await page.evaluate(() => document.activeElement.matches("tr.acct")), "ArrowUp keeps focus in Accounts");
await page.screenshot({ path: `${out}/demo-1440.png`, fullPage: false });

// 390px: active account and PAPER stay visible in the status bar.
const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
await phone.goto(`${base}/demo?account=${target}`);
const bar = await phone.$eval(".statusbar", (b) => {
  const vis = (sel) => { const e = b.querySelector(sel); if (!e) return false;
    const r = e.getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth + 1 && r.top < 80; };
  return { ctx: vis(".ctxbar"), paper: b.textContent.includes("PAPER") && vis(".ctxbar") };
});
check(bar.ctx && bar.paper, "390px status bar shows active account + PAPER");
await phone.screenshot({ path: `${out}/demo-390.png`, fullPage: false });
const denied = await phone.goto(`${base}/demo?account=nope`);
check(denied.status() === 404, "unknown account -> 404 page");
await phone.screenshot({ path: `${out}/demo-390-notfound.png` });

await browser.close();
if (fail.length) { console.error(`${fail.length} failed`); process.exit(1); }
console.log("keyboard check: all passed");
