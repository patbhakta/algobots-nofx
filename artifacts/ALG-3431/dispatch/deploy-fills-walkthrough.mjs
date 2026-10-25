// ALG-3431 browser walkthrough on the deployed NoFX Studio (:8201): a fresh
// funder backtests (marimo evidence), deploys, and the live tab shows the
// gateway orders/fills of THAT deployment's own paper node.
//
//   node deploy-fills-walkthrough.mjs deploy <baseURL> <outDir> <inviteFile> <stateFile>
//   node deploy-fills-walkthrough.mjs live   <baseURL> <outDir> <stateFile> <tag>
//
// <inviteFile> (single-use) and <stateFile> (the QA session) live in run
// scratch and are never written to <outDir>.
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'

const require = createRequire('/root/repos/huible-frontend/node_modules/')
const { chromium } = require('playwright')

const [mode, base, out, ...rest] = process.argv.slice(2)
mkdirSync(out, { recursive: true })
const steps = []
const step = (name, ok, detail = {}) => {
  steps.push({ name, ok, ...detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`, JSON.stringify(detail))
}
const liveJson = (page) =>
  page.evaluate(async () => {
    const r = await fetch('/api/nofx/studio/live', {
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
    })
    return r.json()
  })

const browser = await chromium.launch()
const tag = mode === 'live' ? rest[1] : 'deploy'
let ctx
try {
  if (mode === 'deploy') {
    const [inviteFile, stateFile] = rest
    ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
    const page = await ctx.newPage()
    const email = `deploy-qa-${Date.now()}@example.com`
    const pw = `${randomBytes(12).toString('base64url')}!Aa9`
    await page.goto(`${base}/register`)
    await page.locator('input[type="email"]').fill(email)
    const pws = page.locator('form input[type="password"]')
    await pws.nth(0).fill(pw)
    await pws.nth(1).fill(pw)
    await page.locator('form input').last().fill(readFileSync(inviteFile, 'utf8').trim())
    await page.locator('form button[type="submit"]').click()
    await page.waitForURL(/\/(dashboard|strategy)/, { timeout: 30000 })
    await page.goto(`${base}/strategy`)
    await page.getByTestId('studio-backtest-panel').waitFor({ timeout: 30000 })
    const hash = await page.getByTestId('studio-artifact-hash').innerText()
    step('fresh funder lands in the Studio with a compiled artifact', true, { email, artifact: hash })
    await ctx.storageState({ path: stateFile })

    const [bt] = await Promise.all([
      page.waitForResponse(
        (r) => /\/api\/studio\/strategies\/[^/]+\/backtest$/.test(r.url()) && r.request().method() === 'POST',
        { timeout: 280000 },
      ),
      page.getByTestId('studio-backtest-button').click(),
    ])
    step('backtest runs', bt.status() === 201, { status: bt.status() })

    // The deploy gate needs the exact-hash marimo evidence; poll until it is published.
    const deployBtn = page.getByTestId('studio-deploy-button')
    let enabled = false
    for (let i = 0; i < 30 && !enabled; i++) {
      await page.getByTestId('studio-deploy-panel').waitFor({ timeout: 30000 })
      const create = page.getByTestId('studio-deploy-create-account')
      if (await create.count()) await create.click({ timeout: 10000 }).catch(() => {})
      await page.waitForTimeout(3000)
      enabled = await deployBtn.isEnabled()
      if (!enabled) {
        await page.waitForTimeout(7000)
        await page.reload()
      }
    }
    const reason = (await page.getByTestId('studio-deploy-reason').count())
      ? await page.getByTestId('studio-deploy-reason').innerText()
      : null
    step('marimo evidence gate opens Deploy', enabled, { reason })
    await page.getByTestId('studio-deploy-panel').scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${out}/01-before-deploy.png` })
    const [dep] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().endsWith('/api/deployments') && r.request().method() === 'POST',
        { timeout: 60000 },
      ),
      deployBtn.click(),
    ])
    const body = await dep.json()
    await page.getByTestId('studio-deploy-result').waitFor({ timeout: 30000 })
    await page.screenshot({ path: `${out}/02-deployed.png` })
    step('deploy returns RUNNING with frozen exact-hash evidence', dep.status() === 201 && body.status === 'running' &&
      body.frozen_spec?.studio_evidence?.artifact_hash === body.artifact_hash, {
      status: dep.status(), deployment_id: body.id, artifact_hash: body.artifact_hash, account_id: body.account_id,
    })
    await ctx.storageState({ path: stateFile })
    writeFileSync(`${out}/deployment.json`, JSON.stringify({ deployment_id: body.id, email }, null, 2))
  } else {
    const [stateFile] = rest
    ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 }, storageState: stateFile })
    const page = await ctx.newPage()
    await page.goto(`${base}/strategy`)
    await page.getByTestId('paper-loop-panel').waitFor({ timeout: 30000 })
    await page.waitForTimeout(3000)
    const card = page.getByTestId('deployments-card')
    const hasCard = (await card.count()) > 0
    if (hasCard) await card.scrollIntoViewIfNeeded()
    else await page.getByTestId('paper-loop-panel').scrollIntoViewIfNeeded()
    await page.screenshot({ path: `${out}/live-${tag}.png` })
    const live = await liveJson(page)
    const mine = (live.deployments || []).map((d) => ({
      deployment_id: d.deployment_id, status: d.status, node: d.node, fills: d.fills,
      orders: d.orders.map((o) => ({ id: o.client_order_id, side: o.side, qty: o.qty, limit_px: o.limit_px,
        status: o.status, filled_qty: o.filled_qty, avg_px: o.avg_px, submitted_at: o.submitted_at, fills: o.fills })),
    }))
    const rendered = hasCard ? await card.getAttribute('data-testid') && (await page.getByTestId('deployment-row').evaluateAll(
      (rows) => rows.map((r) => ({ fills: r.dataset.fills, text: r.innerText.slice(0, 300) })))) : []
    step('live tab renders the viewer deployments card', hasCard, { rendered })
    writeFileSync(`${out}/live-${tag}.json`, JSON.stringify({ as_of: live.as_of, deployments: mine,
      deployments_error: live.deployments_error ?? null, has_section: 'deployments' in live }, null, 2))
  }
} catch (err) {
  step('walkthrough aborted', false, { error: String(err).slice(0, 500) })
} finally {
  await browser.close()
  const ok = steps.every((s) => s.ok)
  writeFileSync(`${out}/summary-${tag}.json`, JSON.stringify({ base, mode, ok, steps }, null, 2))
  process.exit(ok ? 0 : 1)
}
