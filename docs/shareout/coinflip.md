# Coinflip share-out report (ALG-3354 / ALG-3381)

Served at `http://100.82.57.72:8203/` (landing) and `/coinflip.html` (report) by the
`static-shares` container on .243. That container serves
`/mnt/funnytree/algobots/share-out/` read-only. Both pages are plain static HTML,
with no scripts, no external assets, and no login.

## Inputs

| File | Source |
|------|--------|
| `data/research/laya-kalshi/coinflip.jsonl` | Byte copy of FunnyTree `research/laya-kalshi/coinflip.jsonl` (sha256 `c77de65c…`) |
| `data/research/laya-kalshi/coinflip_markets.json` | The 29 matching rows of `markets_detail.json`, reduced to `event, market, title, result, floor_strike` |

## P&L basis: what's recorded and what's modelled

Each archive row holds `event, p, outcome, hit, ts`. There is **no price, stake,
fill, fee or P&L field**, and every price field in `markets_detail.json` is null.
So the report:

- labels recorded P&L "not recorded" in every row and in the headline. The old
  page's `+0.00` values were placeholders.
- draws the equity curve from two **illustrative** flat-$1 models, labelled as
  models wherever they appear:
  - Model A, even money with no fee: `+1` per hit, `−1` per miss. 28 − 28 = **$0.00**.
  - Model B, the Oct 14 draft's 9% fee assumption: `+0.91` per hit, `−1` per miss.
    28 × 0.91 − 28 = **−$2.52**. This is not Kalshi's published fee schedule.
- shows the 95% fair-coin band `±1.96·√i` for Model A after bet *i*.
- compares against 50% using an exact two-sided binomial p-value and a Wilson 95%
  interval. It also gives the bet count needed to tell Model B's 52.4% break-even
  from 50% (5% two-sided, 80% power).

The loader fails closed in these cases: a `hit` flag disagrees with the pick rule
(`p ≥ 0.5` → YES), an event appears twice, a market result contradicts the archive,
or the archive gains money fields. That last check stops a future archive with real
prices from being silently ignored.

## Rebuild and deploy

```bash
cd ~/repos/algobots
python -m algobots.shareout.coinflip \
    --data data/research/laya-kalshi/coinflip.jsonl \
    --markets data/research/laya-kalshi/coinflip_markets.json \
    --out /tmp/share-out
# prints sha256 of coinflip.html and index.html; output is deterministic
scp /tmp/share-out/{index,coinflip}.html 100.82.57.72:/mnt/funnytree/algobots/share-out/
curl -s http://100.82.57.72:8203/coinflip.html | sha256sum   # must match the printed hash
```

The module needs only the standard library. Without an install, run it as
`PYTHONPATH=src python3 -m …`. Tests: `python -m pytest tests/shareout -q`.
