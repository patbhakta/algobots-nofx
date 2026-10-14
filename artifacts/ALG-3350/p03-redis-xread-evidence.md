# ALG-3350 P0.3 done-when evidence: Nautilus order/position events on Redis

Captured 2026-10-14T07:08:19Z on redis:7-alpine (throwaway container),
nautilus_trader 1.231.0.
Node: scripts/phase0_redis_egress.py using algobots.engine.redis_message_bus.

## Stream keys created (`KEYS *`)

```
trader-ALGOBOTS-001:algobots:data.instrument.SIM.EUR/USD
trader-ALGOBOTS-001:algobots:events.account.SIM-001
trader-ALGOBOTS-001:algobots:events.fills.EUR/USD.SIM
trader-ALGOBOTS-001:algobots:events.order.EgressDemoStrategy-000
trader-ALGOBOTS-001:algobots:events.position.EgressDemoStrategy-000
trader-ALGOBOTS-001:algobots:events.system.ALGOBOTS-001
trader-ALGOBOTS-001:algobots:events.system.DataEngine
trader-ALGOBOTS-001:algobots:events.system.EgressDemoStrategy-000
trader-ALGOBOTS-001:algobots:events.system.ExecEngine
trader-ALGOBOTS-001:algobots:events.system.OrderEmulator
trader-ALGOBOTS-001:algobots:events.system.RiskEngine
trader-ALGOBOTS-001:algobots:events.system.SIM
```

Key format is `trader-{trader_id}:{streams_prefix}:{topic}` - the trader
prefix precedes streams_prefix, so a `algobots*` glob does not match.
No `data.quotes.*` stream exists: types_filter=[QuoteTick] suppressed the
high-volume quote egress while quotes still drove the strategy.

## XLEN

```
events.order.EgressDemoStrategy-000           6
events.position.EgressDemoStrategy-000        2
events.fills.EUR/USD.SIM                      2
```

## `XREAD` order events

```
trader-ALGOBOTS-001:algobots:events.order.EgressDemoStrategy-000
1791961658535-0
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderInitialized","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221320-001-000-1","order_side":"BUY","order_type":"MARKET","quantity":"100000","time_in_force":"GTC","post_only":false,"reduce_only":false,"quote_quantity":false,"options":{},"emulation_trigger":"NO_TRIGGER","trigger_instrument_id":null,"contingency_type":"NO_CONTINGENCY","order_list_id":null,"linked_order_ids":null,"parent_order_id":null,"exec_algorithm_id":null,"exec_algorithm_params":null,"exec_spawn_id":null,"tags":null,"event_id":"0886924d-0296-4325-b0c1-df2f658a8b4f","ts_init":"2023-11-14T22:13:20Z","ts_event":"2023-11-14T22:13:20Z","reconciliation":false}
encoding
Json
1791961658535-1
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderSubmitted","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221320-001-000-1","account_id":"SIM-001","event_id":"b7c0eaf9-5208-4f56-8843-95fb9fec9ccc","ts_event":"2023-11-14T22:13:20Z","ts_init":"2023-11-14T22:13:20Z"}
encoding
Json
1791961658536-0
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderFilled","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221320-001-000-1","venue_order_id":"SIM-1-001","account_id":"SIM-001","trade_id":"T-eb81e6b5c55cc841-001","position_id":"SIM-1-001","order_side":"BUY","order_type":"MARKET","last_qty":"100000","last_px":"1.10005","currency":"USD","commission":"2.20 USD","liquidity_side":"TAKER","event_id":"adf04cbf-defd-4f18-96b3-e1fb22217c03","ts_event":"2023-11-14T22:13:20Z","ts_init":"2023-11-14T22:13:20Z","info":{},"reconciliation":false}
encoding
Json
1791961658538-0
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderInitialized","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221321-001-000-2","order_side":"SELL","order_type":"MARKET","quantity":"100000","time_in_force":"GTC","post_only":false,"reduce_only":true,"quote_quantity":false,"options":{},"emulation_trigger":"NO_TRIGGER","trigger_instrument_id":null,"contingency_type":"NO_CONTINGENCY","order_list_id":null,"linked_order_ids":null,"parent_order_id":null,"exec_algorithm_id":null,"exec_algorithm_params":null,"exec_spawn_id":null,"tags":null,"event_id":"e24af86d-3e5c-4674-9e6a-a119dc7ab5b4","ts_init":"2023-11-14T22:13:21Z","ts_event":"2023-11-14T22:13:21Z","reconciliation":false}
encoding
Json
1791961658538-1
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderSubmitted","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221321-001-000-2","account_id":"SIM-001","event_id":"16b46ad6-30ce-4ca5-9be6-1ccb99b7f05a","ts_event":"2023-11-14T22:13:21Z","ts_init":"2023-11-14T22:13:21Z"}
encoding
Json
1791961658539-0
topic
events.order.EgressDemoStrategy-000
type

payload
{"type":"OrderFilled","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","client_order_id":"O-20231114-221321-001-000-2","venue_order_id":"SIM-1-002","account_id":"SIM-001","trade_id":"T-f3366365ac18f220-002","position_id":"SIM-1-001","order_side":"SELL","order_type":"MARKET","last_qty":"100000","last_px":"1.10005","currency":"USD","commission":"2.20 USD","liquidity_side":"TAKER","event_id":"6b125241-9e77-4a19-ac2d-795ee713fe5a","ts_event":"2023-11-14T22:13:21Z","ts_init":"2023-11-14T22:13:21Z","info":{},"reconciliation":false}
encoding
Json
```

## `XREAD` position events

```
trader-ALGOBOTS-001:algobots:events.position.EgressDemoStrategy-000
1791961658537-0
topic
events.position.EgressDemoStrategy-000
type

payload
{"type":"PositionOpened","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","position_id":"SIM-1-001","account_id":"SIM-001","opening_order_id":"O-20231114-221320-001-000-1","entry":"BUY","side":"LONG","signed_qty":100000.0,"quantity":"100000","peak_qty":"100000","last_qty":"100000","last_px":"1.10005","currency":"USD","avg_px_open":1.10005,"realized_pnl":"-2.20 USD","duration_ns":0,"event_id":"eff50a71-dabd-4b57-9377-1dfcda0e6f88","ts_event":"2023-11-14T22:13:20Z","ts_init":"2023-11-14T22:13:20Z"}
encoding
Json
1791961658539-0
topic
events.position.EgressDemoStrategy-000
type

payload
{"type":"PositionClosed","trader_id":"ALGOBOTS-001","strategy_id":"EgressDemoStrategy-000","instrument_id":"EUR/USD.SIM","position_id":"SIM-1-001","account_id":"SIM-001","opening_order_id":"O-20231114-221320-001-000-1","closing_order_id":"O-20231114-221321-001-000-2","entry":"BUY","side":"FLAT","signed_qty":0.0,"quantity":"0","peak_qty":"100000","last_qty":"100000","last_px":"1.10005","currency":"USD","avg_px_open":1.10005,"avg_px_close":1.10005,"realized_return":0.0,"realized_pnl":"-4.40 USD","event_id":"f662dc47-2320-4247-8aff-446e1c9a80fe","ts_opened":"2023-11-14T22:13:20Z","ts_closed":"2023-11-14T22:13:21Z","duration_ns":1000000000,"ts_init":"2023-11-14T22:13:21Z"}
encoding
Json
```
