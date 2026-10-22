"""The rc6 paper node: ``algobots:cmd:<node>`` in, ``trader-*`` streams out (ALG-3405).

This is the process the ``nautilus-node`` container runs (``deploy/compose.nautilus-node.yaml``).
It is the first place every P1 piece meets a real engine:

* a Nautilus **2.0.0rc6** ``LiveNode`` (roadmap rule 5) in the ``SANDBOX``
  environment, with the engine's own sandbox execution client as the venue —
  paper only, ADR 0001's "every order goes through an ``ExecutionClient``";
* :class:`~algobots.node.command_stream.CommandStream` and
  :class:`~algobots.node.command_actor.CommandActor` (P1.3) reading the
  gateway's command stream, with
  :class:`~algobots.node.nautilus_actor.NautilusExecution` as the surface, so
  a gateway ``POST /orders`` becomes ``Strategy.submit_order`` here;
* the engine's own Redis message bus (P0.3) publishing every order, position
  and account event onto ``trader-{trader_id}:algobots:events.*``, plus
  :class:`~algobots.node.event_egress.EventEgress` adding the
  ``AlgoBotsHeartbeat`` the gateway's fitness check reads.

**Threading.** rc6's engine objects are owned by the node's event loop, so
nothing here touches the strategy from another thread. The command stream is
polled from a strategy timer with a *non-blocking* ``XREADGROUP`` instead of
the blocking loop :meth:`CommandStream.run` uses in the sandbox node.

**Prices.** A sandbox venue only fills against market data. By default
(``ALGOBOTS_FEED=replay``, ALG-3406) the ``REPLAY`` client replays the recorded
EUR/USD quotes of the Parquet catalog the image ships (:mod:`algobots.node.replay`)
on their own clock, until IBKR paper data exists (ALG-3357). Every quote that
reaches the strategy is counted, and once a second the node writes what it
received — recorded timestamp, its own receive timestamp, source — to
``algobots:feed:<node>``; that stream is hop 4's evidence. ``ALGOBOTS_FEED=synthetic``
keeps the ALG-3405 random walk (client id ``SYNTHETIC``, source ``synthetic``)
so no fill priced off it can be mistaken for market data. ``types_filter``
keeps quotes off the Redis event egress either way.

Configuration is environment-only (:func:`settings`), so the image carries code
and the compose file carries the deployment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from algobots.node import replay
from algobots.node.command_actor import CommandActor, Outcome
from algobots.node.command_stream import CommandStream
from algobots.node.event_egress import STREAMS_PREFIX, EventEgress
from algobots.node.nautilus_actor import NautilusExecution
from algobots.node.sandbox import trader_id_for

NAUTILUS_PIN = "2.0.0rc6"

log = logging.getLogger("algobots.paper_node")


@dataclass(frozen=True)
class Settings:
    node: str
    venue: str
    nautilus_account_id: str
    symbol: str
    starting_balance: Decimal
    currency: str
    redis_host: str
    redis_port: int
    heartbeat_s: float
    poll_ms: int
    quote_interval_s: float
    quote_mid: Decimal
    feed: str
    replay_path: str
    replay_speed: float
    replay_max_gap_s: float
    feed_signal_s: float

    @property
    def trader_id(self) -> str:
        return trader_id_for(self.node)


def settings(env: dict[str, str] | None = None) -> Settings:
    e = os.environ if env is None else env
    return Settings(
        node=e.get("ALGOBOTS_NODE", "nautilus-paper"),
        venue=e.get("ALGOBOTS_NODE_VENUE", "SIM"),
        nautilus_account_id=e.get("ALGOBOTS_NODE_ACCOUNT", "SIM-001"),
        symbol=e.get("ALGOBOTS_NODE_SYMBOL", "EUR/USD.SIM"),
        starting_balance=Decimal(e.get("ALGOBOTS_NODE_BALANCE", "100000")),
        currency=e.get("ALGOBOTS_NODE_CURRENCY", "USD"),
        redis_host=e.get("REDIS_HOST", "redis"),
        redis_port=int(e.get("REDIS_PORT", "6379")),
        heartbeat_s=float(e.get("ALGOBOTS_HEARTBEAT_S", "5")),
        poll_ms=int(e.get("ALGOBOTS_CMD_POLL_MS", "200")),
        quote_interval_s=float(e.get("ALGOBOTS_QUOTE_INTERVAL_S", "1")),
        quote_mid=Decimal(e.get("ALGOBOTS_QUOTE_MID", "1.10000")),
        feed=e.get("ALGOBOTS_FEED", "replay"),
        replay_path=e.get("ALGOBOTS_REPLAY_PATH", replay.DEFAULT_PATH),
        replay_speed=float(e.get("ALGOBOTS_REPLAY_SPEED", "1")),
        replay_max_gap_s=float(e.get("ALGOBOTS_REPLAY_MAX_GAP_S", "2")),
        feed_signal_s=float(e.get("ALGOBOTS_FEED_SIGNAL_S", "1")),
    )


def _instrument(s: Settings) -> Any:
    """The node's one instrument; precisions match the replayed catalog (5 / 0)."""
    from nautilus_trader.model import Venue
    from nautilus_trader.testkit.providers import TestInstrumentProvider

    pair, venue = s.symbol.rsplit(".", 1)
    return TestInstrumentProvider.default_fx_ccy(pair, venue=Venue(venue))


def _data_client_types() -> tuple[type, type, type]:
    """Built lazily: subclassing rc6's client base needs the engine installed."""
    from nautilus_trader.live.clients import DataClientFactory, MarketDataClient
    from nautilus_trader.model import Price, Quantity, QuoteTick

    class SyntheticQuotes(MarketDataClient):
        """Random-walk two-sided quotes for one instrument. Not market data."""

        instrument: Any = None
        interval_s: float = 1.0
        mid: float = 1.1

        async def _connect(self) -> None:
            self._handle_instrument(self.instrument)

        async def _disconnect(self) -> None:
            return None

        async def _subscribe_quotes(self, command: Any) -> None:
            self.create_task(self._pump(), "synthetic-quotes")

        async def _unsubscribe_quotes(self, command: Any) -> None:
            return None

        async def _pump(self) -> None:
            inst = self.instrument
            tick = float(inst.price_increment)
            rng = random.Random()
            while True:
                self.mid = max(tick * 10, self.mid + rng.choice((-1, 0, 1)) * tick)
                ts = self.clock.timestamp_ns()
                self._handle_data(
                    QuoteTick(
                        instrument_id=inst.id,
                        bid_price=Price(self.mid - tick, inst.price_precision),
                        ask_price=Price(self.mid + tick, inst.price_precision),
                        bid_size=Quantity(1_000_000, inst.size_precision),
                        ask_size=Quantity(1_000_000, inst.size_precision),
                        ts_event=ts,
                        ts_init=ts,
                    )
                )
                await asyncio.sleep(self.interval_s)

    class ReplayQuotes(SyntheticQuotes):
        """Recorded catalog quotes, paced by their recorded gaps, looped at the end."""

        path: str = replay.DEFAULT_PATH
        speed: float = 1.0
        max_gap_s: float = 2.0
        cursor: replay.ReplayCursor | None = None

        async def _subscribe_quotes(self, command: Any) -> None:
            self.create_task(self._replay(), "replay-quotes")

        async def _replay(self) -> None:
            inst, cur = self.instrument, self.cursor
            assert cur is not None
            pp, sp = inst.price_precision, inst.size_precision
            while True:
                prev: int | None = None
                for q in replay.read_quotes(self.path):
                    await asyncio.sleep(replay.pace(prev, q.ts_event, self.speed, self.max_gap_s))
                    prev = q.ts_event
                    cur.row, cur.recorded_ts = q.row, q.ts_event
                    ts = self.clock.timestamp_ns()
                    self._handle_data(
                        QuoteTick(
                            instrument_id=inst.id,
                            bid_price=Price.from_raw(q.bid_raw, pp),
                            ask_price=Price.from_raw(q.ask_raw, pp),
                            bid_size=Quantity.from_raw(q.bid_size_raw, sp),
                            ask_size=Quantity.from_raw(q.ask_size_raw, sp),
                            ts_event=ts,
                            ts_init=ts,
                        )
                    )
                cur.laps += 1
                log.info("replay lap %d done (%d quotes); restarting", cur.laps, cur.row + 1)

    class QuotesFactory(DataClientFactory):
        settings: Settings | None = None
        cursor: replay.ReplayCursor | None = None

        @staticmethod
        def create(*, name: str, config: Any, cache: Any, clock: Any) -> Any:
            s = QuotesFactory.settings
            assert s is not None
            inst = _instrument(s)
            kind = ReplayQuotes if s.feed == "replay" else SyntheticQuotes
            client = kind(name=name, config=config, cache=cache, clock=clock, venue=inst.id.venue)
            client.instrument = inst
            client.interval_s = s.quote_interval_s
            client.mid = float(s.quote_mid)
            if isinstance(client, ReplayQuotes):
                client.path = s.replay_path
                client.speed = s.replay_speed
                client.max_gap_s = s.replay_max_gap_s
                client.cursor = QuotesFactory.cursor
            return client

    return SyntheticQuotes, ReplayQuotes, QuotesFactory


def _strategy_type() -> type:
    from nautilus_trader.trading import Strategy

    class CommandNode(Strategy):
        """The strategy whose ``submit_order`` the gateway's commands go through.

        It trades nothing on its own: every order it submits came from
        ``algobots:cmd:<node>``. Its timers do two things — drain the command
        stream and beat the heartbeat — both on the node's own loop.
        """

        # rc6's pyo3 ``Strategy.__new__`` takes only a config, so the node's
        # wiring is bound after construction rather than passed to __init__.
        s: Settings
        redis: Any
        egress: EventEgress
        stream: CommandStream | None = None
        feed: replay.FeedSignal
        cursor: replay.ReplayCursor | None = None

        def bind(
            self, s: Settings, redis_client: Any, cursor: replay.ReplayCursor | None
        ) -> CommandNode:
            self.s = s
            self.redis = redis_client
            self.egress = EventEgress(client=redis_client, trader_id=s.trader_id)
            self.feed = replay.FeedSignal(client=redis_client, node=s.node, every_s=s.feed_signal_s)
            self.cursor = cursor
            return self

        def on_quote(self, tick: Any) -> None:  # rc6 name (1.x: on_quote_tick)
            # Hop 4's evidence: a quote the strategy actually received, with the
            # recorded time it was replayed from and the node time it arrived.
            try:
                wrote = self.feed.on_quote(
                    ts_init=tick.ts_init,
                    bid=str(tick.bid_price),
                    ask=str(tick.ask_price),
                    cursor=self.cursor,
                )
            except Exception as exc:  # a Redis hiccup must not stop the strategy
                log.warning("feed signal failed: %s", exc)
                return
            if wrote and self.feed.written % 60 == 1:  # first, then about once a minute
                c = self.cursor
                log.info(
                    "feed received=%d node_ts=%d recorded_ts=%s row=%s bid=%s ask=%s",
                    self.feed.received,
                    tick.ts_init,
                    c.recorded_ts if c else "synthetic",
                    c.row if c else "-",
                    tick.bid_price,
                    tick.ask_price,
                )

        def _before_ack(self, outcome: Outcome) -> None:
            """rc6 submit_order queues work; its return is not execution evidence."""
            if outcome.action not in ("submitted", "duplicate"):
                return
            from nautilus_trader.model import ClientOrderId

            order = self.cache.order(ClientOrderId(outcome.client_order_id))
            status = getattr(order.status, "name", str(order.status)) if order is not None else ""
            if status in ("", "INITIALIZED", "EMULATED", "RELEASED"):
                raise RuntimeError(
                    f"awaiting engine execution: {outcome.client_order_id} ({status})"
                )
            if status == "DENIED":
                # rc6 risk denials do not reach external message-bus egress.
                # Retry this write before XACK, including after a Redis failure.
                event = order.last_event
                if callable(event):
                    event = event()
                self.egress.publish(denial_payload(event))

        def on_start(self) -> None:
            from nautilus_trader.model import InstrumentId

            self.subscribe_quotes(InstrumentId.from_str(self.s.symbol))
            actor = CommandActor(
                execution=NautilusExecution(self), node=self.s.node, log=_log_event
            )
            # block_ms=None: a non-blocking XREADGROUP, because this runs on the
            # engine's loop and must never park it.
            self.stream = CommandStream(
                client=self.redis,
                actor=actor,
                node=self.s.node,
                consumer=self.s.trader_id,
                block_ms=None,  # type: ignore[arg-type]
                log=_log_event,
                before_ack=self._before_ack,
            )
            self.stream.ensure_group()
            self._beat()
            self.clock.set_timer_ns(
                "algobots-cmd", self.s.poll_ms * 1_000_000, callback=self._on_poll
            )
            self.clock.set_timer_ns(
                "algobots-heartbeat",
                int(self.s.heartbeat_s * 1e9),
                callback=lambda _e: self._beat(),
            )

        def _beat(self) -> None:
            # The trader starts only after startup reconciliation completes
            # (``nautilus_live::node``), so a running strategy is a reconciled node.
            self.egress.heartbeat(
                node=self.s.node,
                nautilus_account_id=self.s.nautilus_account_id,
                ts=time.time(),
                reconciled=True,
            )

        def _on_poll(self, _event: Any) -> None:
            assert self.stream is not None
            try:
                # Pending first: an entry whose handling raised (an instrument
                # not loaded yet, a lost connection) is retried before new ones.
                self.stream.drain_pending()
                self.stream.poll()
            except Exception as exc:  # the entry stays pending; next tick retries
                log.warning("command poll failed: %s", exc)

    return CommandNode


def denial_payload(event: Any) -> dict[str, Any]:
    """Use the gateway's ISO timestamp envelope, including on older deployments."""
    from algobots.gateway.projection import iso

    payload = event.to_dict()
    for key in ("ts_event", "ts_init"):
        payload[key] = iso(payload[key] / 1e9)
    return payload


def _log_event(event: str, fields: dict[str, Any]) -> None:
    log.info("%s %s", event, fields)


def build(s: Settings) -> Any:
    """Assemble the rc6 ``LiveNode``. Importing this module does not need the engine."""
    import nautilus_trader
    import redis
    from nautilus_trader.adapters.sandbox import (
        SandboxExecutionClientConfig,
        SandboxExecutionClientFactory,
    )
    from nautilus_trader.common import Environment, MessageBusConfig, SerializationEncoding
    from nautilus_trader.execution import MakerTakerFeeModel
    from nautilus_trader.infrastructure import RedisMessageBusConfig, RedisMessageBusFactory
    from nautilus_trader.live import DataClientConfig, LiveNode
    from nautilus_trader.model import (
        AccountId,
        AccountType,
        Currency,
        Money,
        OmsType,
        TraderId,
        Venue,
    )

    if nautilus_trader.__version__ != NAUTILUS_PIN:
        raise RuntimeError(
            f"nautilus_trader {nautilus_trader.__version__} != pinned {NAUTILUS_PIN}"
        )

    if s.feed not in ("replay", "synthetic"):
        raise ValueError(f"ALGOBOTS_FEED={s.feed!r}: expected replay or synthetic")
    cursor: replay.ReplayCursor | None = None
    if s.feed == "replay":
        meta = replay.catalog_meta(s.replay_path)
        if meta.get("instrument_id") != s.symbol:
            raise RuntimeError(
                f"{s.replay_path} holds {meta.get('instrument_id')}, node trades {s.symbol}"
            )
        cursor = replay.ReplayCursor(source=f"replay:{s.replay_path}", instrument=s.symbol)
    *_clients, quotes_factory = _data_client_types()
    quotes_factory.settings = s
    quotes_factory.cursor = cursor

    builder = LiveNode.builder(s.node, TraderId(s.trader_id), Environment.SANDBOX)
    builder.with_msgbus_config(
        MessageBusConfig(
            encoding=SerializationEncoding.JSON,
            timestamps_as_iso8601=True,
            stream_per_topic=True,
            streams_prefix=STREAMS_PREFIX,
            # Quotes drive the venue; they are not events the gateway folds.
            types_filter=["QuoteTick"],
        )
    )
    builder.with_external_msgbus_factory(
        RedisMessageBusFactory(RedisMessageBusConfig(host=s.redis_host, port=s.redis_port))
    )
    builder.add_data_client(
        "REPLAY" if s.feed == "replay" else "SYNTHETIC", quotes_factory, DataClientConfig()
    )
    builder.add_simulated_exec_client(
        s.venue,
        SandboxExecutionClientFactory(),
        SandboxExecutionClientConfig(
            venue=Venue(s.venue),
            account_id=AccountId(s.nautilus_account_id),
            starting_balances=[Money(s.starting_balance, Currency.from_str(s.currency))],
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            # rc6 refuses an implicit fee model; paper charges nothing.
            fee_model=MakerTakerFeeModel(Decimal(0), Decimal(0)),
        ),
    )
    node = builder.build()
    client = redis.Redis(host=s.redis_host, port=s.redis_port)
    node.add_strategy(_strategy_type()().bind(s, client, cursor))
    return node


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    s = settings()
    log.info(
        "node=%s trader=%s venue=%s account=%s symbol=%s feed=%s redis=%s:%s",
        s.node,
        s.trader_id,
        s.venue,
        s.nautilus_account_id,
        s.symbol,
        s.feed if s.feed != "replay" else f"replay:{s.replay_path}@{s.replay_speed}x",
        s.redis_host,
        s.redis_port,
    )
    build(s).run()


if __name__ == "__main__":
    main()


__all__ = ["NAUTILUS_PIN", "Settings", "build", "main", "settings"]
