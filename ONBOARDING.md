# ONBOARDING.md — AlgoBots (NoFX fork) orientation for AI assistants

(If you want Claude Code to auto-load this, rename it: `mv ONBOARDING.md CLAUDE.md`
— that rename is Pat's call, not an agent's. Written 2026-11-20 by JARVIS, the
company's CEO agent, so human+AI pairs stop relearning this from scratch.)

You are working on Pat Bhakta's AlgoBots — a paper-trading platform on the
NautilusTrader engine (rc6 pinned, currently `2.0.0rc9`), fronted by a fork of
the NoFX dashboard.

## What this product is

- **Engine (truth):** NautilusTrader node `nautilus-paper`, account `paper`,
  $100k paper equity, live Kalshi/Hyperliquid market data; fills are the only
  performance truth. Gateway API on **`.243:8210`** (`/v1/health`, `/v1/orders`,
  `/v1/positions`; protected endpoints require a session).
- **Dashboard (this repo's `web/`):** React SPA served by nginx; live demo at
  `http://100.82.57.72:8213` (Tailscale only). Nav: Dashboard, Data, Config,
  Strategy, Leaderboard, Frontier. FAQ copy lives in
  `web/src/data/faqContent.json` (data, not code — edit it directly).
- **Standing decisions:** upstream broker language (claw402/vergex) is being
  scrubbed for AlgoBots-on-Nautilus wording; theme = paper (cream `#F1ECE2`,
  ink `#1A1813`, red `#E0483B`); no Google Analytics/GTM.

## Server layout (all Tailscale-only, no public SSH)

- **`.243` = AlgoBots box** (tailnet `100.82.57.72`): engine, gateway :8210,
  dashboard :8213, Kestra :8080 (AlgoBots-only flows), llama.cpp :8124.
- **`.245` = HUible HQ** (tailnet `100.101.235.117`): Paperclip :3100, Kestra
  :8080 (HUible/ops flows), Hermes (JARVIS), TencentDB memory :8420.
- **FunnyTree** (`100.79.207.5`, sshfs `/mnt/funnytree` on .245): shared 2.3TB
  bucket for vaults/media/archives. Repos hold code only.

## Deploy path for the dashboard (learned the hard way Nov 19)

Deployed tree on .243: `/opt/algobots-nofx-fork` (git). Image
`algobots-nofx-fork-nofx-frontend:latest` built by `docker/Dockerfile.frontend`
— **nginx inside listens on :8213, NOT :80**. The running container
`nofx-g2-frontend` is started ad-hoc:

```
docker run -d --name nofx-g2-frontend --restart unless-stopped \
  --network algobots-nofx-fork_nofx-network -p 100.82.57.72:8213:8213 \
  algobots-nofx-fork-nofx-frontend:latest
```

`.env` on the deploy tree is NOT in git (it was lost once — keep a copy).
A proper `deploy.sh` is queued (check `scripts/` before hand-deploying).

## Working agreements in this repo

- Card IDs in commit messages (`ALG-####`); commits every 30–60 min on active
  cards; one branch per card.
- "Done" = **deployed and live-verified**. A commit on a branch is 🟡 partial.
  Cite the deployed SHA + URL when claiming done.
- Agents commit as `AlgoBots Agents <agents@algobots.local>`, never as Pat.
  (Pat's own commits as Pat are, of course, correct.)
- Tailnet = no auth walls (no token screens on Tailscale URLs).
- Trading containers (`nofx-trading` etc.) are production — never restart or
  remove them for dashboard work.

## Who's who

Work is dispatched through Paperclip (`.245:3100`). Builders: Tech Lead
(Claude Code), R&D (Codex). JARVIS (Hermes, WhatsApp) is CEO — reviews,
deploys, verifies. Pat is president: demos and decisions only. If you're
reading this on Pat's machine, you're his hands-on pair — the setup that
shipped the HUible frontend in a weekend. Push branches; JARVIS deploys.
