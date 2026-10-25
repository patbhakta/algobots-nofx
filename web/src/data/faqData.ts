import {
  BookOpen,
  Monitor,
  Shield,
  TrendingUp,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * FAQ content model. Answers are composed from typed blocks so the renderer
 * stays generic — no per-question JSX special cases. Inline `code` spans are
 * written with backticks and parsed by the renderer.
 */
export type FAQBlock =
  | { type: 'p'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'steps'; items: string[] }
  | { type: 'note'; text: string }
  | { type: 'links'; links: { label: string; href: string }[] }

export interface FAQItem {
  id: string
  question: string
  blocks: FAQBlock[]
}

export interface FAQCategory {
  id: string
  title: string
  icon: LucideIcon
  items: FAQItem[]
}

/** Plain text of an item, used by the search filter. */
export function faqItemSearchText(item: FAQItem): string {
  const parts: string[] = [item.question]
  for (const block of item.blocks) {
    if (block.type === 'p' || block.type === 'note') parts.push(block.text)
    else if (block.type === 'list' || block.type === 'steps')
      parts.push(block.items.join(' '))
    else if (block.type === 'links')
      parts.push(block.links.map((l) => l.label).join(' '))
  }
  return parts.join(' ').toLowerCase()
}

export const faqCategories: FAQCategory[] = [
  // ───────────────────────── Getting started ─────────────────────────
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: BookOpen,
    items: [
      {
        id: 'what-is-nofx',
        question: 'What is AlgoBots?',
        blocks: [
          {
            type: 'p',
            text: 'AlgoBots is a self-hosted AI trading terminal. Its flagship mode is AlgoBots Autopilot: an AI agent that combines Binance market data, Polymarket probabilities, and IBKR brokerage data, verifies candidates with Signal Lab and liquidation structure, confirms timing with raw candles, and sends the resulting orders to NautilusTrader for execution — all on a server you control, with your keys never leaving it.',
          },
          {
            type: 'p',
            text: 'Beyond the Autopilot you can build custom strategies in Strategy Studio, run multiple AI traders side by side, and compare them on the leaderboard.',
          },
        ],
      },
      {
        id: 'what-do-i-need',
        question: 'What do I need before launching the Autopilot?',
        blocks: [
          {
            type: 'p',
            text: 'One connected account and one strategy — the guided launch on the Config page walks you through both:',
          },
          {
            type: 'list',
            items: [
              'A paper or demo trading account you connect with your own credentials — Kalshi or Polymarket US for event contracts, IBKR paper for stocks, Binance for crypto market data.',
              'A strategy: start from the AlgoBots Autopilot preset, or build your own in Strategy Studio.',
            ],
          },
          {
            type: 'p',
            text: 'The launch button runs a server-side preflight that checks every prerequisite and points you at the exact step that is missing, so you cannot start a half-configured bot.',
          },
          {
            type: 'note',
            text: 'AlgoBots trades paper and demo accounts only. There is no wallet to fund and no deposit to make; enabling a live account is a separate decision per account, taken much later.',
          },
        ],
      },
      {
        id: 'which-markets',
        question: 'Which markets can it trade?',
        blocks: [
          {
            type: 'p',
            text: 'Prediction markets come first: Kalshi and Polymarket US event contracts are the priority venues, because that is where the strategies are being built today.',
          },
          {
            type: 'p',
            text: 'Crypto majors (BTC, ETH, SOL, …) stream from Binance public market data, and IBKR paper covers US stocks, indices and FX. Other US stock brokers sit at the end of the connector queue, behind the prediction-market work.',
          },
          {
            type: 'p',
            text: 'Whichever venue a strategy targets, the order path is the same: NautilusTrader executes and reconciles every fill.',
          },
        ],
      },
      {
        id: 'ai-models',
        question: 'Which AI models does it use? Do I need API keys?',
        blocks: [
          {
            type: 'p',
            text: 'AI access is included with your AlgoBots subscription. There is no separate per-call wallet to create or fund, and the terminal can access supported models on demand.',
          },
          {
            type: 'p',
            text: 'Power users can still plug in their own provider keys (OpenAI, Claude, Gemini, DeepSeek, Qwen, Grok, Kimi, or any OpenAI-compatible endpoint) under Config → Models.',
          },
        ],
      },
      {
        id: 'is-it-profitable',
        question: 'Will it make money?',
        blocks: [
          {
            type: 'p',
            text: 'No one can promise that, and you should distrust anyone who does. The AI trades a systematic process, but markets are adversarial and past performance never guarantees future results.',
          },
          {
            type: 'p',
            text: 'The dashboard is deliberately honest about performance: it separates realized from unrealized P/L, shows the fee-drag chain (gross − fees = net), profit factor, and max drawdown computed from your real starting balance. Watch those numbers, start small, and only trade money you can afford to lose.',
          },
          {
            type: 'note',
            text: 'Trading involves substantial risk of loss. AlgoBots is software, not investment advice.',
          },
        ],
      },
    ],
  },

  // ───────────────────────── Launch & accounts ─────────────────────────
  {
    id: 'launch-accounts',
    title: 'Launch & Accounts',
    icon: Zap,
    items: [
      {
        id: 'no-wallet-needed',
        question: 'Do I need a crypto wallet or a prepaid balance?',
        blocks: [
          {
            type: 'p',
            text: 'No. AI model calls and research data are covered by your AlgoBots subscription, so there is no per-call wallet to create, fund or back up.',
          },
          {
            type: 'p',
            text: 'Earlier builds asked for a prepaid on-chain balance to pay a data broker per call. That broker was dropped, and the prepaid balance went with it — AlgoBots now reads Binance, Polymarket and IBKR directly.',
          },
        ],
      },
      {
        id: 'account-authorization',
        question: 'How does connecting an account work? Is it safe?',
        blocks: [
          {
            type: 'p',
            text: 'You connect your own paper or demo account, and AlgoBots keeps only what it needs to trade it:',
          },
          {
            type: 'steps',
            items: [
              'Create API credentials at the venue with trading permission only — no withdrawal rights.',
              'Paste them into the guided setup on the Config page; they are encrypted (AES-256) in your own database.',
              'AlgoBots verifies the account is reachable and shows the balance it can see.',
              'Orders route through NautilusTrader, which owns the execution path and reconciles every fill.',
            ],
          },
          {
            type: 'p',
            text: 'Nothing in AlgoBots can move money out of an account: the credentials are trading-scoped, the account stays yours, and every connected account today is paper or demo.',
          },
        ],
      },
      {
        id: 'launch-preflight',
        question: 'What does the launch preflight check?',
        blocks: [
          {
            type: 'p',
            text: 'Before anything is created or changed, the server verifies the full chain with live data:',
          },
          {
            type: 'list',
            items: [
              'AI model is enabled and has a credential.',
              'The connected account is reachable and its saved credentials are still valid.',
              'The account is paper or demo — a live account is refused unless it was explicitly approved.',
              'The strategy config satisfies the hard risk controls (position cap, leverage caps, trade throttle).',
            ],
          },
          {
            type: 'p',
            text: 'Each failing check names the exact fix and deep-links into the guided setup. The same checks are enforced server-side on every start, so the UI cannot be bypassed accidentally.',
          },
        ],
      },
      {
        id: 'relaunch-behavior',
        question: 'What happens if I press Launch again?',
        blocks: [
          {
            type: 'p',
            text: 'Launching is idempotent. If an AlgoBots Autopilot already exists, the launcher updates it with the current strategy config and restarts it — it never creates a duplicate. A restart can take up to a minute if the bot is mid-cycle; the UI waits for it.',
          },
        ],
      },
      {
        id: 'balance-not-showing',
        question: 'My account balance shows zero or "unknown".',
        blocks: [
          {
            type: 'list',
            items: [
              "Zero: check the venue itself — a paper account that was reset there reports zero until you top it back up in the venue's own dashboard.",
              'Stale: balances are cached for ~30 seconds and the setup panel re-checks every few seconds. Use Refresh in the guided panel if in doubt.',
              'Unknown: the venue API did not answer. The panel deliberately shows unknown instead of zero so a strategy never sizes off a bad number — retry in a minute.',
            ],
          },
        ],
      },
    ],
  },

  // ───────────────────────── Trading & execution ─────────────────────────
  {
    id: 'trading',
    title: 'Trading & Execution',
    icon: TrendingUp,
    items: [
      {
        id: 'autopilot-pipeline',
        question: 'How does the Autopilot strategy work, step by step?',
        blocks: [
          {
            type: 'p',
            text: 'Every cycle runs the same four-stage funnel — each stage can reject a candidate, and only setups that survive all four get traded:',
          },
          {
            type: 'steps',
            items: [
              'Build the universe — combine Binance, Polymarket, and IBKR feeds and take the top candidates (default 10) across crypto majors and supported traditional markets, each with a direction bias and signal z-score.',
              'Verify each candidate — fetch its Signal Lab deep signal plus the cost/liquidation structure around price: liquidation clusters and cost bases show whether a move has fuel ahead of it or walls against it.',
              'Confirm timing — read the raw 15-minute OHLCV candles (30 bars) to check the entry is riding structure, not chasing an extended move.',
              "Decide and size — only setups clearing the confidence threshold (default `78/100`) with roughly `3:1` risk/reward become orders, sized by the strategy's risk controls and handed to NautilusTrader; closes always execute before opens, and both long and short books are considered every cycle.",
            ],
          },
          {
            type: 'p',
            text: 'A fifth layer sits outside the AI entirely: hard risk controls (position cap, leverage caps, margin ceiling, trade throttle) reject any decision that violates them, no matter how confident the model is.',
          },
        ],
      },
      {
        id: 'data-sources',
        question: 'What data does it use, and which parts are paid?',
        blocks: [
          {
            type: 'list',
            items: [
              'Connected signal data — the ranking board, per-symbol Signal Lab deep signals, and market net-flow sourced from Binance, Polymarket, and IBKR.',
              'Cost/liquidation heatmaps — aggregated position-cost and liquidation-cluster structure for each market.',
              'Venue market data — raw OHLCV candles and live order-book depth from Binance public endpoints and from the venue a strategy is trading.',
              'Your connected account — equity, available margin, open positions with PnL, read straight from the venue.',
              'Its own history — closed trades feed win rate, profit factor and drawdown back into the next prompt, so the AI knows its recent form.',
            ],
          },
          {
            type: 'note',
            text: 'The dashboard refreshes slower-changing cross-market signals every few minutes while price and execution panels stay live.',
          },
          {
            type: 'note',
            text: "Research feeds can disagree slightly with your broker. The broker's price is the source of truth for fills — the feeds exist for ranking, backtesting and strategy development.",
          },
        ],
      },
      {
        id: 'decision-cycle',
        question: 'How often does the AI make decisions?',
        blocks: [
          {
            type: 'p',
            text: 'The Autopilot runs a scan cycle every 5–15 minutes depending on how you launched it (configurable per trader, minimum 3 minutes). The first cycle starts right after launch; a single cycle usually takes 30–60 seconds because the AI reads the full market context before deciding.',
          },
        ],
      },
      {
        id: 'what-ai-sees',
        question: 'What information does the AI see each cycle?',
        blocks: [
          {
            type: 'list',
            items: [
              'Your account: equity, available margin, open positions with PnL.',
              'The cross-market ranking board: candidate universe with direction bias.',
              'Signal Lab deep signals and cost/liquidation structure per candidate.',
              'Raw OHLCV candles for timing confirmation.',
              'Its own track record: win rate, profit factor, drawdown, recent trades.',
            ],
          },
          {
            type: 'p',
            text: 'Every cycle is stored as a decision record — the Execution Log on the dashboard shows the reasoning chain, actions, and any blocked orders.',
          },
        ],
      },
      {
        id: 'leverage-and-risk',
        question: 'What leverage and risk controls does it use?',
        blocks: [
          {
            type: 'p',
            text: 'Leverage is always set explicitly by the strategy config rather than inherited from a venue default, and event contracts on Kalshi or Polymarket carry none at all. Hard risk controls run outside the AI and cannot be overridden by it:',
          },
          {
            type: 'list',
            items: [
              'Position-count cap from the strategy config — new opens are rejected at the cap.',
              'Leverage limits per asset class, where the venue offers leverage at all.',
              'A trade throttle blocks churn, e.g. closing a barely-moved position minutes after opening it.',
              'Safe mode (below) protects the book when the AI itself is failing.',
            ],
          },
        ],
      },
      {
        id: 'safe-mode',
        question: 'What is safe mode?',
        blocks: [
          {
            type: 'p',
            text: 'If the AI fails 3 cycles in a row (provider outage, rate limits, unusable responses), the trader enters safe mode: no new positions are opened, existing positions keep their protection, and the loop keeps retrying. It exits safe mode automatically on the next successful AI call.',
          },
          {
            type: 'p',
            text: 'Safe mode is shown as a banner on the dashboard together with the reason, so it never happens silently.',
          },
        ],
      },
      {
        id: 'ai-unavailable-mid-run',
        question: 'What happens if the AI is unavailable mid-run?',
        blocks: [
          {
            type: 'p',
            text: 'Calls start failing with a clear status, the dashboard shows a persistent red banner with the reason, and after three failed cycles the trader enters safe mode. Once the provider answers again the trader recovers on its own — no restart needed.',
          },
        ],
      },
      {
        id: 'trading-fees',
        question: 'What fees am I paying?',
        blocks: [
          {
            type: 'list',
            items: [
              "Venue trading fees on every order — simulated by Nautilus against the venue's real fee model while you are on paper, so paper P/L is not flattered.",
              'Nothing else: AI calls and research data are covered by your AlgoBots subscription, and there is no per-order platform fee.',
            ],
          },
          {
            type: 'p',
            text: 'Fees are the silent killer of high-frequency strategies. The dashboard stats strip shows the full chain — gross realized P/L, minus fees, equals net — so you can see immediately whether fees are eating the edge.',
          },
        ],
      },
      {
        id: 'stop-and-manual',
        question: 'How do I stop the bot or close positions manually?',
        blocks: [
          {
            type: 'list',
            items: [
              'Stop: use the Stop button on the Config page trader list. Stopping halts the decision loop; open positions remain open and are yours to manage.',
              'Manual close: close any position from the dashboard positions panel — manual closes sync back into the position history.',
              'Emergencies: you can always manage positions directly at the venue; AlgoBots never locks you out of your own account.',
            ],
          },
        ],
      },
    ],
  },

  // ───────────────────────── Dashboard & metrics ─────────────────────────
  {
    id: 'dashboard',
    title: 'Dashboard & Metrics',
    icon: Monitor,
    items: [
      {
        id: 'metrics-meaning',
        question: 'What do the header metrics mean exactly?',
        blocks: [
          {
            type: 'list',
            items: [
              'Equity — live account value including unrealized PnL.',
              'Total P/L (incl. unrealized) — equity versus your starting balance; moves with open positions.',
              'Realized P/L (closed trades) — net result of finished trades only; this is what win rate, profit factor and sharpe are computed from.',
              'Profit factor — gross wins ÷ gross losses on closed trades; above 1.0 means the closed book is net positive.',
              'Max drawdown — worst peak-to-trough dip of the realized equity curve, measured against your real starting balance.',
            ],
          },
        ],
      },
      {
        id: 'pl-contradiction',
        question: 'Why is Total P/L positive while Realized P/L is negative?',
        blocks: [
          {
            type: 'p',
            text: 'They measure different things. Realized P/L only counts closed trades; Total P/L also includes the unrealized gains of positions still open. A bot can be down on its closed trades while its open book carries enough unrealized profit to put total P/L in the green — and vice versa. Check the gross/fees/net strip to see how much of the realized result is fee drag.',
          },
        ],
      },
      {
        id: 'execution-log',
        question: 'Where can I see why the AI did (or refused) something?',
        blocks: [
          {
            type: 'p',
            text: 'The Execution Log panel lists every cycle with the actions taken, the AI call duration, and any blocked orders with the exact guard that fired (throttle, position cap, risk control). Full reasoning chains are stored with each decision record.',
          },
        ],
      },
      {
        id: 'competition',
        question: 'What is the leaderboard / competition?',
        blocks: [
          {
            type: 'p',
            text: 'Traders with "show in competition" enabled appear on the public leaderboard, ranked by live performance. It is opt-in per trader and can be toggled from the trader list at any time.',
          },
        ],
      },
    ],
  },

  // ───────────────────────── Security ─────────────────────────
  {
    id: 'security',
    title: 'Security',
    icon: Shield,
    items: [
      {
        id: 'key-storage',
        question: 'How are my keys stored?',
        blocks: [
          {
            type: 'list',
            items: [
              'All secrets (venue API keys, tokens, model credentials) are AES-256 encrypted at rest in your own database.',
              'Optional RSA transport encryption protects secrets in flight between browser and server.',
              'AlgoBots is self-hosted: your secrets stay in your own instance and are not sent to any third-party server.',
            ],
          },
        ],
      },
      {
        id: 'can-nofx-steal-funds',
        question: 'Can AlgoBots withdraw or steal my funds?',
        blocks: [
          {
            type: 'p',
            text: 'No. AlgoBots only ever holds trading-scoped credentials for accounts you connected yourself, and every connected account today is paper or demo. Create each API key with trading permission only — disable withdrawals and set an IP whitelist where the venue supports it.',
          },
          {
            type: 'note',
            text: 'Going live is a separate decision per account, taken deliberately and much later. No strategy, preset or update can flip an account to live on its own.',
          },
        ],
      },
      {
        id: 'registration-model',
        question: 'Why can’t anyone else register on my instance?',
        blocks: [
          {
            type: 'p',
            text: 'By design, an instance is single-operator: the first account registered becomes the operator and registration closes ("System already initialized"). This prevents strangers from creating accounts on an exposed deployment. Run one instance per operator.',
          },
        ],
      },
    ],
  },

  // ───────────────────────── Self-hosting ─────────────────────────
  {
    id: 'self-hosting',
    title: 'Setup & Troubleshooting',
    icon: Wrench,
    items: [
      {
        id: 'launch-blocked',
        question: 'Launch is blocked by a failing check — now what?',
        blocks: [
          {
            type: 'p',
            text: 'Read the message: every preflight failure names its fix and routes you to the right setup step — enable a model, reconnect the trading account, or resolve a risk-control conflict in the strategy config. The checks re-run against live data, so once you fix the item the launch goes through.',
          },
        ],
      },
      {
        id: 'exchange-unreachable',
        question:
          'The trading account shows "invalid credentials" or "unavailable".',
        blocks: [
          {
            type: 'list',
            items: [
              'Invalid credentials: the saved API key was rotated, revoked or expired at the venue — create a new trading-only key and reconnect the account in the guided setup.',
              'Unavailable: the venue API did not respond; the account state is cached for 30 seconds, so wait and refresh.',
              'Permissions: verify trading permission, the IP whitelist, and that the instrument class your strategy trades is enabled on the account.',
            ],
          },
        ],
      },
    ],
  },
]
