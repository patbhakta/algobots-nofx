# AlgoBots Roadmap v3

Oct 14, 2026 · @Pat

## Summary

Cut the plan to your six goals and connect the two containers through one small new service, a gateway, before adding any broker. The v2 handoff had 38 packets and the older roadmap had 75 sprints. Most of that work (Obsidian and TencentDB memory, Kestra, RAG, Jev, FinRL, fees, an agent task queue) does not serve the six goals, so it moves to a Later list.

What changed since the earlier documents:

- **NoFX is now the real frontend, not just a design reference.** v2 said to build a custom React UI inspired by NoFX. You are running NoFX itself, so the plan extends NoFX instead of replacing it.
- **NoFX already has a seam for this.** Its Go backend talks to every exchange through one `Trader` interface (`trader/types/interface.go`). Adding a `nautilus` exchange type that calls the gateway puts Nautilus accounts on the NoFX dashboard without rewriting the UI.
- **NoFX has no 2FA and no invite control.** Login is email, password and a JWT; the first account to register becomes the owner. 2FA and invites are new work.
- **TD Ameritrade's API no longer exists.** It became the Schwab Trader API.
- **Polymarket has two APIs.** Nautilus's stable Polymarket adapter targets the international exchange, where US users can only close positions. Polymarket US is a separate CFTC-regulated exchange with its own API, so it needs a custom adapter.
- **Kalshi is not in Nautilus yet.** It is listed as planned and the maintainers are building it themselves.
- **Robinhood stocks are reachable only through its Agentic Trading MCP beta.** That runs in a separate agent account with a preloaded wallet. Crypto has a regular API.
- **Nautilus 2.0 is still a release candidate** and each rc has renamed config classes. Pin rc6 and treat every upgrade as its own sprint.

The first milestone is narrow. A paper order placed in NoFX goes through the gateway into a Nautilus node, fills, and the fill shows back in NoFX.

## Architecture: how the two sides talk

Put NoFX and Nautilus in one Compose project on a shared network, and add a Python gateway between them that owns every call into Nautilus. NoFX never talks to a broker for friends' accounts; it asks the gateway, and the gateway asks a Nautilus node.

&#91;embedded content: AlgoBots services · one gateway between NoFX and Nautilus\]

The gateway is the only new piece in the order path; NoFX and Nautilus each keep their own job.

| Service | Built from | Job | Storage |
| --- | --- | --- | --- |
| `nofx-frontend` | NoFX (React) | Dashboard, login, 2FA screens | None |
| `nofx` | NoFX (Go), forked | Users, invites, 2FA, UI APIs, the new `nautilus` exchange type | Postgres, database `nofx` (NoFX already ships a GORM Postgres driver) |
| `gateway` | New (Python, FastAPI) | REST and WebSocket API for accounts, orders, positions, signals; starts and stops nodes; checks risk limits before forwarding an order | Postgres, database `algobots` |
| `node-<account>` | Nautilus 2.0.0rc6 | One trading node per member, broker account and paper/live mode; runs strategies and the broker adapter | Redis (message bus), Parquet catalog volume |
| `signals` | New (Python) | Polls Massive, Reddit and xAI; publishes signal events | Postgres, database `algobots` |
| `redis` | Redis 7 | Nautilus event streams out, command stream in | Named volume, AOF on |
| `postgres` | Postgres 16 | Durable state for both apps | Named volume, nightly dump |
| `auth-proxy` (optional) | Authelia or Authentik | 2FA in front of everything until NoFX's own 2FA lands | Postgres |

How a message moves:

1. **Commands in.** NoFX calls `POST /orders` on the gateway with an idempotency key. The gateway checks the member's grant and limits, records the intent in Postgres, then writes it to the Redis stream `algobots:cmd:<node>`.
2. **Execution.** A small `CommandActor` inside each Nautilus node reads that stream and calls `submit_order` or `cancel_order`. Nautilus's own RiskEngine still runs, so the gateway check is an extra layer, not a replacement.
3. **Events out.** Each node publishes its message bus to Redis with `MessageBusConfig` (JSON encoding, one stream per node, `types_filter` dropping high-volume quote ticks). The gateway consumes the streams, writes orders, fills and positions to Postgres, and pushes them to NoFX over WebSocket.
4. **Display.** The `nautilus` exchange type in NoFX implements `GetBalance`, `GetPositions`, the order methods and `GetMarketPrice` by calling the gateway, so existing NoFX screens fill with Nautilus data.

Nautilus documents event egress to Redis but not a way for outside systems to send commands in, which is why the `CommandActor` is part of the plan ([message bus docs](https://nautilustrader.io/docs/nightly/concepts/message_bus)).

### Docker's agent features: not for this

Docker Compose's agent features (the `models` element, MCP Gateway, Offload) package LLM agents with their models and MCP tools ([InfoQ](https://www.infoq.com/news/2025/07/docker-compose-agent-gpu-offload)). They do not provide service-to-service messaging between two apps, so they would not make NoFX and Nautilus talk. What does the job is plain Compose: one shared network, Redis for messages, Postgres for state, and named volumes so nothing is lost on restart.

The agent features do fit one later idea. Exposing the gateway's read-only endpoints through Docker's MCP Gateway would let an AI assistant query positions and signals. That is listed under Later.

### Things NoFX's shape forces

- NoFX's `Trader` interface is shaped for crypto perpetuals (`OpenLong`, `OpenShort`, `SetLeverage`). Stocks and yes/no contracts fit badly, so the `nautilus` type adds a generic `PlaceOrder(instrument, side, qty, type, price)` path and the UI gets pages for those asset types.
- NoFX has its own AI trading loop (`auto_trader_*.go`) that sends orders directly to exchanges. For accounts routed through Nautilus, that loop may suggest trades but every order must go through the gateway.
- NoFX is AGPL-3.0. Serving a modified copy to friends over the network means offering them its source. Keep the fork in a repository you can share.

## Reality check: brokers, markets and data

Only Interactive Brokers has a stable Nautilus adapter among the US brokers you named, so most of goals 4 to 6 means writing adapters in your own repository. The [Nautilus integrations list](https://nautilustrader.io/docs/nightly/integrations/) has 21 entries; for US stocks it lists only IBKR.

| Target | Goal | Nautilus today | Official API | Path | Check before building |
| --- | --- | --- | --- | --- | --- |
| Interactive Brokers | 5 | Stable adapter | TWS / IB Gateway | Use the built-in adapter; this is the first real broker | Paper account login; one Gateway container per account |
| Alpaca (suggested) | 5 | None | REST + WebSocket, free paper accounts | Custom adapter; easiest second broker | None; good for testing the adapter kit |
| Schwab (was TD Ameritrade) | 5 | None | Schwab Trader API, OAuth | Custom adapter | Developer app approval; refresh tokens need a manual re-login about weekly (unverified) |
| Robinhood stocks | 5 | None | [Agentic Trading over MCP](https://techcrunch.com/2026/05/27/robinhood-now-lets-your-ai-agents-trade-stocks/), beta, stocks only, separate agent account with a preloaded wallet | Experimental: an MCP client inside an adapter | Whether the MCP route allows automated orders without per-trade approval |
| Robinhood crypto | 5 | None (the "Lighter on Robinhood" adapter is a DEX on Robinhood Chain, not your brokerage account) | Robinhood Crypto Trading API with signed keys | Custom adapter | Current docs and key setup |
| tastytrade, Webull | 5 | None | OAuth APIs | Custom adapters, after Schwab | Third-party app approval |
| Kalshi | 4 | Planned; maintainers own the build and closed an outside PR ([PR 5010](https://github.com/nautechsystems/nautilus_trader/pull/5010)) | [REST, WebSocket, FIX, demo environment](https://docs.kalshi.com/welcome) | Wait if the official adapter lands before Phase 4; otherwise build a thin in-house one and retire it later | Whether the official adapter has shipped |
| Polymarket US | 4 | None (the stable adapter is the international exchange) | [Separate CFTC-regulated API](https://www.quantvps.com/blog/polymarket-us-api-available): Ed25519-signed REST plus market and private WebSockets, 25 requests a second | Custom adapter | Each member needs a verified Polymarket US account |
| Massive (formerly Polygon.io) | 6 | None | REST + WebSocket for stocks, options, crypto | Custom data client | Whether your plan allows showing data to other people; Databento is the stable-adapter fallback |
| xAI (Grok) | 6 | Not applicable | Responses API with `x_search` and `web_search` tools ([docs](https://docs.x.ai/docs/guides/tools/search-tools)) | Scheduled job asks Grok for structured sentiment on a watchlist | It is request and response, not a stream; budget per call |
| Reddit | 6 | Not applicable | Data API, 100 queries a minute with OAuth, commercial use needs approval ([summary](https://octolens.com/blog/reddit-api-pricing)) | Poller over a list of subreddits | Personal use is fine; anything resembling a product needs Reddit's approval |

Two patterns hold across all of these. Each member connects their own broker accounts with their own credentials, which keeps Pat out of other people's logins. And every adapter starts against a paper or demo account; a live key is a separate decision per account.

## Roadmap: phases and micro sprints

The roadmap has seven phases, and each micro sprint is one pull request an AI coding agent can finish and prove with a test. Phases 0 to 3 are strictly in order. Phases 4, 5 and 6 can run side by side once Phase 3's gate passes.

&#91;embedded content: AlgoBots phases · 7 phases, 3 gates\]

Phase 1 is the first milestone; phases 4 to 6 wait for IBKR paper to work end to end, except the signals service (P6.2), which can start after G1.

Rules for every agent:

1. One sprint, one branch, one PR. Its "Done when" test must run in CI or as a script in the repo.
2. The gateway's API lives in one file, `contracts/gateway.openapi.yaml`. Change it first, then regenerate the Go client NoFX uses.
3. Paper and demo accounts only. No sprint may add a live key or flip an account to live.
4. Secrets come from environment variables or the encrypted store, never from the repo or logs.
5. Pin Nautilus to `2.0.0rc6`. An upgrade to a later rc is its own sprint, with the release notes' renamed configs fixed and tests green.

### Phase 0: Baseline

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P0.1 | Put both running setups in one repo (NoFX fork as a submodule or subtree, Nautilus node configs, compose files) and record exact versions, ports and volumes | None | `INVENTORY.md` lists every container, image tag, port and volume now running |
| P0.2 | One `compose.yaml` with a shared network, Postgres, Redis and named volumes; NoFX moved from SQLite to Postgres | P0.1 | `docker compose down && up` keeps NoFX users and settings |
| P0.3 | Nautilus sandbox node with Redis message bus egress (JSON, quote ticks filtered) | P0.2 | `redis-cli XREAD` shows order and position events from a test strategy |

### Phase 1: Make them talk (goal 1)

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P1.1 | Gateway skeleton: `/health`, `/accounts`, `/positions`, `/orders`, `/events` WebSocket; OpenAPI contract | P0.3 | Contract tests pass against a fixture node |
| P1.2 | Gateway consumes node event streams into Postgres tables for orders, fills, positions and balances | P1.1 | Restarting the gateway rebuilds the same positions from Postgres |
| P1.3 | `CommandActor` in the node: reads `algobots:cmd:<node>`, submits or cancels with the idempotency key as client order id | P1.1 | Sending the same command twice creates one order |
| P1.4 | NoFX `nautilus` exchange type implementing `Trader` through the generated gateway client | P1.1 | Adding a Nautilus account in NoFX shows its sandbox balance |
| P1.5 | End-to-end paper test | P1.2, P1.3, P1.4 | A market order placed in NoFX fills in the sandbox and the fill appears in NoFX within 2 seconds |

Gate G1: P1.5 passes in CI on every merge.

### Phase 2: Friends and family login (goal 2)

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P2.1 | Invite-only sign-up: open `/register` disabled; Pat issues single-use invite links | G1 | Registering without a valid invite fails |
| P2.2 | TOTP 2FA with recovery codes, required for every member | P2.1 | Login without the code fails; a recovery code works once |
| P2.3 | Roles: owner (Pat) sees system health, not other members' trades or keys | P2.1 | Owner calls to another member's account data return 403 |
| P2.4 | Isolation tests across every NoFX and gateway route | P2.3 | Automated test: member A cannot read or trade member B's accounts |
| P2.5 | Broker credentials encrypted at rest and handed only to that account's node | P2.4 | Credentials never appear in API responses, logs or the frontend bundle |
| P2.6 | Optional: Authelia or Authentik with TOTP or passkeys in front of NoFX until P2.2 ships | G1 | Every route needs a second factor |

Gate G2: two test members each see only their own paper accounts.

### Phase 3: Execution wiring (goal 3)

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P3.1 | Account registry: one node per member, broker account and mode; gateway starts and stops node containers | G2 | Adding an account in NoFX starts its node; removing it stops it |
| P3.2 | Per-account limits: max order size, max position, daily loss stop, and a kill switch button in NoFX | P3.1 | An order over the limit is refused with a reason shown in NoFX |
| P3.3 | Restart recovery: node reconciles with the broker on start; unknown orders block new orders until resolved | P3.1 | Killing a node mid-order and restarting it ends with matching broker and gateway state |
| P3.4 | IBKR paper through the built-in adapter, IB Gateway in its own container | P3.2, P3.3 | Buy and sell a US stock in IBKR paper from NoFX |
| P3.5 | Adapter kit: a template package, fixtures and conformance tests every new adapter must pass | P3.3 | The sandbox adapter passes the kit's tests |

Gate G3: IBKR paper trading works end to end for two members.

### Phase 4: Prediction markets (goal 4)

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P4.1 | Yes/no contract support in NoFX: market list, price as probability, position pages | G3 | A fixture Kalshi market renders with its yes and no prices |
| P4.2 | Kalshi decision: use the official Nautilus adapter if released, else build a thin one | P3.5 | Decision written in the repo |
| P4.3 | Kalshi data and orders against the demo environment | P4.1, P4.2 | Place and cancel a demo order from NoFX; passes the adapter kit |
| P4.4 | Polymarket US read side: markets, order book stream, portfolio | P4.1, P3.5 | Live book for a market shows in NoFX |
| P4.5 | Polymarket US orders and private stream, smallest size on a verified account | P4.4 | Place and cancel an order; fills reconcile |

### Phase 5: US brokers (goal 5)

Each broker is three sprints: connect and read accounts, place orders, then stream and reconcile. Every one must pass the adapter kit.

| Order | Broker | Why this order |
| --- | --- | --- |
| 1 | Alpaca | Free paper trading and a simple API; proves the kit on stocks |
| 2 | Schwab | Covers your former TD Ameritrade accounts |
| 3 | Robinhood crypto | Official signed-key API |
| 4 | tastytrade | OAuth API, options-friendly |
| 5 | Robinhood stocks | Only through the Agentic MCP beta; build last and keep it experimental |
| 6 | Webull | Only if a member needs it |

### Phase 6: Real-time data and signals (goal 6)

| ID | Sprint | Depends on | Done when |
| --- | --- | --- | --- |
| P6.1 | Massive data client: WebSocket trades and minute bars into Nautilus | P3.5 | A strategy receives Massive bars for 5 tickers in the sandbox |
| P6.2 | `signals` service and a common signal event (source, symbol, score, text, time) | G1 | A test signal reaches NoFX and a subscribed strategy |
| P6.3 | Reddit poller over a configured list of subreddits, with ticker extraction | P6.2 | Mentions per ticker per hour shown in NoFX |
| P6.4 | xAI job: Grok `x_search` on the watchlist every N minutes, returning structured JSON, with a daily spend cap | P6.2 | Cap stops calls when reached; scores show in NoFX |
| P6.5 | Signals page in NoFX and a sample strategy that reads signals in paper mode | P6.1, P6.3 | Sample strategy trades on a signal in the sandbox |

### Later

These came from v2 and stay parked until the six goals work: Obsidian and TencentDB memory, Kestra, RAG and Jev decision graphs, TradingAgents and FinRL research, DuckDB analytics, fees and billing, derivatives and margin, OpenAlgo, the multi-agent task queue, and exposing the gateway as MCP tools.

## Risks and open decisions

The biggest risk is not technical. Running strategies on other people's money can make you their investment adviser, so the plan keeps each member in control of their own accounts. This is a design choice, not legal advice; check with a lawyer before anyone but you trades live.

| Risk | What could go wrong | Mitigation in this plan |
| --- | --- | --- |
| Trading for others | Placing trades in friends' accounts could need adviser registration, and breaks some brokers' terms | Members link their own accounts and pick their own strategies; the owner role has no trading rights on other accounts (P2.3) |
| Nautilus 2.0 churn | Each rc renamed config classes and changed defaults (rc4 set backtest leverage to 10x for margin accounts) | Pin rc6, upgrade only as a dedicated sprint, set leverage explicitly |
| Unofficial broker access | Scraping or unofficial Robinhood libraries can get accounts locked | Official APIs only; Robinhood stocks stay experimental |
| Data redistribution | Showing Massive or exchange data to other people may need a different plan | Check the license in P6.1; Databento as fallback |
| Unknown order state | A crash between send and confirm could double a position | Idempotency keys (P1.3) and block-until-reconciled (P3.3) |
| AGPL | Sharing a modified NoFX without its source breaks the license | Keep the fork's source available to members |
| Polymarket geography | Using the international exchange from the US | Polymarket US API only (P4.4) |

Decisions only you can make:

- [ ] Should NoFX's own AI trader stay on for your personal crypto exchange accounts, or should every order go through Nautilus? The plan assumes Nautilus for all friends' accounts and leaves yours as you choose.
- [ ] Is Alpaca acceptable as the second broker, ahead of Schwab? It is the cheapest way to prove the adapter kit.
- [ ] Does any friend need live trading in the first release, or is paper enough until G3?
- [ ] Which Massive plan do you hold, and does it allow display to other users?

## Sources

- [NoFX repository](https://github.com/NoFxAiOS/nofx), dev branch inspected 2026-10-14: `trader/types/interface.go`, `auth/auth.go`, `api/server.go`, `docker-compose.yml`
- [NautilusTrader releases](https://github.com/nautechsystems/nautilus_trader/releases) and [integrations](https://nautilustrader.io/docs/nightly/integrations/)
- [Nautilus message bus](https://nautilustrader.io/docs/nightly/concepts/message_bus) and [prediction markets](https://nautilustrader.io/prediction/)
- [Kalshi adapter PR 5010](https://github.com/nautechsystems/nautilus_trader/pull/5010) and [Kalshi API docs](https://docs.kalshi.com/welcome)
- [Polymarket US API overview](https://www.quantvps.com/blog/polymarket-us-api-available)
- [Robinhood agentic trading (TechCrunch)](https://techcrunch.com/2026/05/27/robinhood-now-lets-your-ai-agents-trade-stocks/)
- [xAI search tools](https://docs.x.ai/docs/guides/tools/search-tools)
- [Reddit API limits and pricing](https://octolens.com/blog/reddit-api-pricing)
- [Docker Compose agent features (InfoQ)](https://www.infoq.com/news/2025/07/docker-compose-agent-gpu-offload)
- Earlier plans: ROADMAP.md (75 sprints), AlgoBots v2 analysis and handoff bundle (38 packets, 22 September 2026)
