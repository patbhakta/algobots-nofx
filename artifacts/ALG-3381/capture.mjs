// Usage: node capture.mjs <baseURL> <outDir>  — screenshots + rendered-text checks of the share-out.
import { chromium } from '/root/repos/huible-frontend/node_modules/playwright/index.mjs';
import { writeFileSync } from 'node:fs';
const [,, base, out] = process.argv;
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1000, height: 900 } });
const external = [];
p.on('request', r => { if (!r.url().startsWith(base)) external.push(r.url()); });
const res = {};
for (const page of ['', 'coinflip.html']) {
  const r = await p.goto(base + page);
  const text = await p.innerText('body');
  await p.screenshot({ path: `${out}/${page || 'index'}.png`, fullPage: true });
  res[page || 'index'] = { status: r.status(), auth: r.headers()['www-authenticate'] ?? null,
    svg: await p.locator('svg.chart').count(), notRecordedCells: await p.locator('td.na').count(),
    tableRows: await p.locator('table tr').count(), text: text.slice(0, 400) };
}
res.externalRequests = external;
writeFileSync(`${out}/summary.json`, JSON.stringify(res, null, 2));
console.log(JSON.stringify(res, null, 2));
await b.close();
