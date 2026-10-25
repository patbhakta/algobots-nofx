import { createRequire } from 'node:module'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { randomBytes } from 'node:crypto'
const require = createRequire('/root/repos/huible-frontend/node_modules/')
const { chromium } = require('playwright')
const [base, out, inviteFile] = process.argv.slice(2)
mkdirSync(out, {recursive:true})
const browser = await chromium.launch()
const ctx = await browser.newContext({viewport:{width:1600,height:1200}})
const page = await ctx.newPage()
try {
  await page.goto(`${base}/register`)
  await page.locator('input[type="email"]').fill(`paper-loop-qa-${Date.now()}@example.com`)
  const pw = `${randomBytes(16).toString('base64url')}!Aa9`
  await page.locator('form input[type="password"]').nth(0).fill(pw)
  await page.locator('form input[type="password"]').nth(1).fill(pw)
  await page.locator('form input').last().fill(readFileSync(inviteFile,'utf8').trim())
  await page.locator('form button[type="submit"]').click()
  await page.waitForURL(/\/(dashboard|strategy)/, {timeout:30000})
  await page.goto(`${base}/strategy`)
  await page.getByLabel('Paper strategy').waitFor({timeout:30000})
  await page.getByText('order-coin', {exact:true}).count() // no synthetic receipts
  await page.getByTestId('workers-card').getByText('coin', {exact:true}).waitFor()
  await page.getByLabel('Paper strategy').selectOption('coin')
  const panel = page.getByTestId('paper-loop-panel')
  await panel.scrollIntoViewIfNeeded()
  await page.screenshot({path:`${out}/01-live-coin.png`})
  const first = await page.evaluate(async () => {
    const r=await fetch('/api/nofx/studio/live', {headers:{Authorization:`Bearer ${localStorage.getItem('auth_token')}`}})
    return r.json()
  })
  await page.waitForResponse(r=>r.url().endsWith('/api/nofx/studio/live') && r.status()===200, {timeout:30000})
  const second = await page.evaluate(async () => {
    const r=await fetch('/api/nofx/studio/live', {headers:{Authorization:`Bearer ${localStorage.getItem('auth_token')}`}})
    return r.json()
  })
  await page.screenshot({path:`${out}/02-live-coin-refreshed.png`})
  const summary={base, first_as_of:first.as_of, second_as_of:second.as_of, feed:second.feed,
    workers:second.workers.map(w=>({account:w.account,state:w.state,orders:w.orders_submitted,fills:w.orders_filled,positions:w.open_positions,pnl:w.funds?.strategy_pnl})),
    polling_updated:second.as_of>first.as_of, fills_increased:second.workers.some(w=>w.orders_filled>first.workers.find(x=>x.account===w.account)?.orders_filled)}
  writeFileSync(`${out}/summary.json`,JSON.stringify(summary,null,2))
  console.log(JSON.stringify(summary))
  await page.evaluate(async()=>{await fetch('/api/logout',{method:'POST',headers:{Authorization:`Bearer ${localStorage.getItem('auth_token')}`}});localStorage.clear()})
} finally { await browser.close() }
