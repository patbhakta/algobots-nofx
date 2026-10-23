// ALG-3418 browser walkthrough on the deployed NoFX Studio (:8201): the
// Backtest button runs the strategy's compiled artifact on a frozen
// KXBTC15M recorder dataset (Nautilus BacktestEngine) and renders the result.
//
//   node alg3418-studio-backtest-walkthrough.mjs <baseURL> <outDir> <inviteFile>
//
// <inviteFile> holds a single-use platform invite; it is never written to
// <outDir>. A fresh QA user registers with it, so the run is tenant-isolated.
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'

const require = createRequire('/root/repos/huible-frontend/node_modules/')
const { chromium } = require('playwright')

const [base, out, inviteFile] = process.argv.slice(2)
mkdirSync(out, { recursive: true })
const invite = readFileSync(inviteFile, 'utf8').trim()
const email = `studio-qa-${Date.now()}@example.com`
const pw = `${randomBytes(12).toString('base64url')}!Aa9`
const steps = []
const step = (name, ok, detail = {}) => {
  steps.push({ name, ok, ...detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`, JSON.stringify(detail))
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
const page = await ctx.newPage()
const backtestPost = (r) => /\/api\/studio\/strategies\/[^/]+\/backtest$/.test(r.url()) && r.request().method() === 'POST'

try {
  await page.goto(`${base}/register`)
  await page.locator('input[type="email"]').fill(email)
  const pws = page.locator('form input[type="password"]')
  await pws.nth(0).fill(pw)
  await pws.nth(1).fill(pw)
  await page.locator('form input').last().fill(invite)
  await page.locator('form button[type="submit"]').click()
  await page.waitForURL(/\/(dashboard|strategy)/, { timeout: 30000 })
  await page.goto(`${base}/strategy`)
  await page.getByTestId('studio-backtest-panel').waitFor({ timeout: 30000 })
  step('QA user registers and lands in the Studio', true, { email })

  const hash = await page.getByTestId('studio-artifact-hash').innerText()
  const impl = await page.getByTestId('studio-implementation').innerText()
  const button = page.getByTestId('studio-backtest-button')
  step('seeded momentum strategy is compiled; Backtest is enabled', impl === 'kalshi_momentum.v1' && await button.isEnabled(), { implementation: impl, artifact: hash })
  await page.getByTestId('studio-backtest-panel').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${out}/01-before-backtest.png` })

  const t0 = Date.now()
  const [resp] = await Promise.all([page.waitForResponse(backtestPost, { timeout: 280000 }), button.click()])
  const body = await resp.json()
  await page.getByTestId('studio-backtest-result').waitFor({ timeout: 30000 })
  const shown = {
    dataset: await page.getByTestId('studio-backtest-dataset').innerText(),
    pnl: await page.getByTestId('studio-backtest-pnl').innerText(),
    hit_rate: await page.getByTestId('studio-backtest-hit-rate').innerText(),
    brier: await page.getByTestId('studio-backtest-brier').innerText(),
  }
  await page.getByTestId('studio-backtest-result').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${out}/02-backtest-result.png` })
  const m = body.metrics || {}
  step('Backtest returns a Nautilus result tied to a named dataset', resp.status() === 201 &&
    body.executor?.startsWith('NautilusTrader') && body.artifact?.artifact_hash.startsWith(hash) &&
    shown.dataset === body.dataset?.name && shown.pnl.replace('+', '') === m.pnl, {
    status: resp.status(), seconds: (Date.now() - t0) / 1000, executor: body.executor,
    artifact_hash: body.artifact?.artifact_hash, dataset: body.dataset, metrics: m, shown,
    curve_points: body.equity_curve?.length, result_id: body.id,
  })
  const curve = await page.locator('[aria-label="Backtest equity curve"] .recharts-line-curve').count()
  step('equity curve renders', curve === 1, { line_paths: curve })

  // Stored result survives a reload (GET .../backtests), same id.
  await page.reload()
  await page.getByTestId('studio-backtest-result').waitFor({ timeout: 30000 })
  const again = await page.getByTestId('studio-backtest-dataset').innerText()
  await page.getByTestId('studio-backtest-result').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${out}/03-result-after-reload.png`, fullPage: false })
  step('stored result reloads for the same artifact', again === shown.dataset, { dataset: again })

  // An unsaved edit disables Backtest: it always runs the compiled artifact.
  await page.getByRole('button', { name: '4h', exact: true }).click()
  step('unsaved edit disables Backtest', !(await button.isEnabled()))
} catch (err) {
  step('walkthrough aborted', false, { error: String(err).slice(0, 500) })
  await page.screenshot({ path: `${out}/99-error.png`, fullPage: true }).catch(() => {})
} finally {
  await browser.close()
  const ok = steps.every((s) => s.ok)
  writeFileSync(`${out}/summary.json`, JSON.stringify({ base, ok, steps }, null, 2))
  process.exit(ok ? 0 : 1)
}
