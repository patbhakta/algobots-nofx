// ALG-3414 funder walkthrough on the deployed NoFX Studio (:8201).
//
//   node funder-walkthrough.mjs <baseURL> <outDir> <secretsDir>
//
// <secretsDir> holds owner_pw (and receives the UI-minted invite code); it is a
// run-scratch directory, never an artifact. Minted codes are redacted in the
// DOM before any screenshot, and no credential is written to <outDir>.
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'

const require = createRequire('/root/repos/huible-frontend/node_modules/')
const { chromium } = require('playwright')

const [base, out, sec] = process.argv.slice(2)
mkdirSync(out, { recursive: true })
const OWNER = 'pat@bhakta.us'
const ownerPw = readFileSync(`${sec}/owner_pw`, 'utf8')
const funderEmail = `funder-ui-${Date.now()}@example.com`
const funderPw = `${randomBytes(12).toString('base64url')}!Aa9`
const steps = []
const step = (name, ok, detail = {}) => {
  steps.push({ name, ok, ...detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`, JSON.stringify(detail))
}

const redactCode = (page) =>
  page.evaluate(() =>
    document.querySelectorAll('[data-testid="minted-code"]').forEach((el) => {
      el.textContent = '[invite code redacted from evidence]'
    })
  )

async function mint(page) {
  await page.getByRole('button', { name: /Mint funder invite/ }).click()
  const code = page.getByTestId('minted-code')
  await code.waitFor({ timeout: 15000 })
  return (await code.textContent()).trim()
}

async function register(page, email, code) {
  await page.goto(`${base}/register`)
  await page.locator('input[type="email"]').fill(email)
  const pw = page.locator('form input[type="password"]')
  await pw.nth(0).fill(funderPw)
  await pw.nth(1).fill(funderPw)
  await page.locator('form input').last().fill(code)
  await page.locator('form button[type="submit"]').click()
}

const browser = await chromium.launch()
try {
  // 1. Owner signs in through the NoFX login form (A03 gate behind it).
  const ownerCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const owner = await ownerCtx.newPage()
  await owner.goto(`${base}/login`)
  await owner.locator('input[type="email"]').fill(OWNER)
  await owner.locator('input[type="password"]').fill(ownerPw)
  await owner.locator('button[type="submit"]').click()
  await owner.waitForURL(/\/strategy/, { timeout: 20000 })
  await owner.getByTestId('paper-loop-panel').waitFor({ timeout: 20000 })
  await owner.getByTestId('decision-row').first().waitFor({ timeout: 20000 })
  await owner.screenshot({ path: `${out}/01-owner-studio.png`, fullPage: true })
  step('owner login lands on Strategy Studio with the paper loop', true, { url: owner.url() })

  // 2. Owner mints a funder invite in the UI.
  const code = await mint(owner)
  writeFileSync(`${sec}/invite_ui`, code, { mode: 0o600 })
  await redactCode(owner)
  await owner.getByTestId('invites-card').screenshot({ path: `${out}/02-owner-minted-invite.png` })
  step('owner mints a single-use funder invite', /^ALG-/.test(code), { code_prefix: code.slice(0, 4) })

  // 3. Funder redeems it on /register and lands in the Studio — no second login.
  const funderCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const funder = await funderCtx.newPage()
  await register(funder, funderEmail, code)
  await funder.waitForURL(/\/strategy/, { timeout: 20000 })
  await funder.getByTestId('decision-row').first().waitFor({ timeout: 20000 })
  await funder.screenshot({ path: `${out}/03-funder-studio.png`, fullPage: true })
  const feedText = (await funder.getByTestId('feed-card').innerText()).replace(/\s+/g, ' ')
  step('invited funder registers and sees the Studio', true, { email: funderEmail, feed: feedText.slice(0, 240) })

  // 4. A decision correlated with its actual Nautilus receipt, and a risk block.
  const filled = funder.getByTestId('decision-row').filter({ hasText: /O-2026\d{4}-\d{6}-/ }).first()
  await filled.scrollIntoViewIfNeeded()
  await filled.screenshot({ path: `${out}/04-decision-with-nautilus-receipt.png` })
  const filledText = (await filled.innerText()).replace(/\s+/g, ' ')
  step('decision row shows its Nautilus fill receipt', /O-2026/.test(filledText), { row: filledText })
  const blocked = funder.getByTestId('decision-row').filter({ hasText: /daily-loss/ }).first()
  const blockedCount = await blocked.count()
  if (blockedCount) {
    await blocked.scrollIntoViewIfNeeded()
    await blocked.screenshot({ path: `${out}/05-decision-risk-blocked.png` })
  }
  step('risk-blocked decision shows its reason', blockedCount > 0, {
    row: blockedCount ? (await blocked.innerText()).replace(/\s+/g, ' ') : null,
  })
  const pageText = await funder.locator('body').innerText()
  step('paper / sandbox labelling is visible', /paper/i.test(pageText) && /sandbox/i.test(pageText))
  step('funder does not get the owner invite controls', (await funder.getByTestId('invites-card').count()) === 0)

  // 4b. Studio configuration controls work against AlgoBots (tenant-scoped,
  // config-only): create, save + activate, survives a reload.
  await funder.getByRole('button', { name: /Create a strategy config/ }).click()
  const nameInput = funder.locator('input[value="Studio strategy config"]')
  await nameInput.waitFor({ timeout: 15000 })
  const [put, act] = await Promise.all([
    funder.waitForResponse((r) => /\/api\/strategies\/[^/]+$/.test(r.url()) && r.request().method() === 'PUT'),
    funder.waitForResponse((r) => /\/activate$/.test(r.url())),
    funder.getByRole('button', { name: /Save configuration/ }).click(),
  ])
  await funder.reload()
  await nameInput.waitFor({ timeout: 15000 })
  await funder.screenshot({ path: `${out}/04b-funder-studio-config.png`, fullPage: true })
  const saved = await funder.evaluate(async () => {
    const r = await fetch('/api/strategies/active', {
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
    })
    const j = await r.json()
    return { status: r.status, name: j.name, execution: j.execution, active: j.is_active }
  })
  step('Studio config saves, activates and persists in AlgoBots', put.status() === 200 && act.status() === 200 && saved.active, {
    put: put.status(),
    activate: act.status(),
    saved,
  })

  // 5. Owner revokes the funder: deactivated, sessions killed.
  await owner.reload()
  const row = owner.getByTestId('invites-card').locator('tr', { hasText: funderEmail })
  await row.getByRole('button', { name: /Revoke/ }).click()
  await row.getByText('revoked').waitFor({ timeout: 15000 })
  await owner.getByTestId('invites-card').screenshot({ path: `${out}/06-owner-revoked-funder.png` })
  const status = await funder.evaluate(async () => {
    const r = await fetch('/api/nofx/studio/live', {
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
    })
    return r.status
  })
  step('revoked funder session is refused', status === 401, { status })
  await funder.reload()
  await funder.waitForTimeout(3000)
  await funder.screenshot({ path: `${out}/07-funder-after-revoke.png`, fullPage: true })
  const relogin = await funder.evaluate(
    async ([email, pw]) => {
      const r = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pw }),
      })
      return { status: r.status, body: await r.json() }
    },
    [funderEmail, funderPw]
  )
  step('revoked funder cannot sign in again', relogin.status === 401, relogin)

  // 6. An expired (revoked-before-use) invite is refused at registration.
  const dead = await mint(owner)
  await redactCode(owner)
  await owner.reload()
  await owner
    .getByTestId('invites-card')
    .locator('tr', { hasText: dead.slice(0, 8) })
    .getByRole('button', { name: /Revoke/ })
    .click()
  await owner.waitForTimeout(1500)
  const lateCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const late = await lateCtx.newPage()
  await register(late, `funder-late-${Date.now()}@example.com`, dead)
  await late.waitForTimeout(3000)
  await late.screenshot({ path: `${out}/08-expired-invite-refused.png`, fullPage: true })
  step('expired invite is refused', !/\/strategy/.test(late.url()), { url: late.url() })
} catch (err) {
  step('walkthrough aborted', false, { error: String(err).slice(0, 400) })
} finally {
  await browser.close()
  writeFileSync(`${out}/summary.json`, JSON.stringify({ base, at: new Date().toISOString(), steps }, null, 2))
}
process.exit(steps.every((s) => s.ok) ? 0 : 1)
