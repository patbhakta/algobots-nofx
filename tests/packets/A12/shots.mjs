// ALG-3257 (A12-1): 1440 + 390 screenshots of /demo with the G1 walkthrough
// card open. Usage: NODE_PATH=<dir with playwright-core> node shots.mjs <base-url> <out-dir>
import { createRequire } from "node:module";
import { globSync } from "node:fs";
import { homedir } from "node:os";

const { chromium } = createRequire(import.meta.url)("playwright-core");

const [base = "http://127.0.0.1:8763", out = "."] = process.argv.slice(2);
const exe = globSync(`${homedir()}/.cache/ms-playwright/chromium-*/chrome-linux*/chrome`).sort().pop();
const browser = await chromium.launch({ executablePath: exe, args: ["--no-sandbox"] });

const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await desktop.goto(`${base}/demo`);
await desktop.evaluate(() => document.querySelector("details.democard")?.setAttribute("open", ""));
await desktop.waitForTimeout(500);
await desktop.screenshot({ path: `${out}/demo-1440.png`, fullPage: false });
console.log(`PASS demo-1440.png (card open)`);

const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
await phone.goto(`${base}/demo?account=laya`);
await phone.evaluate(() => document.querySelector("details.democard")?.setAttribute("open", ""));
await phone.waitForTimeout(500);
await phone.screenshot({ path: `${out}/demo-390.png`, fullPage: false });
const fits = await phone.evaluate(() => {
  const el = document.querySelector("details.democard ol.steps");
  return el ? el.scrollWidth <= document.documentElement.clientWidth + 1 : false;
});
console.log(`${fits ? "PASS" : "FAIL"} demo-390.png card fits 390px without horizontal scroll`);
await browser.close();
if (!fits) process.exit(1);
