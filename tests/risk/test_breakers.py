"""RateBreakers — deterministic §19 trips, window recovery, privileged exits."""

from algobots.risk.breakers import RateBreakers


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t


def test_trip_at_ten_orders_per_minute_per_deployment():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    for _ in range(10):
        assert rb.check("entry", "dep").allowed
        rb.record("entry", "dep")
    denied = rb.check("entry", "dep")
    assert denied.allowed is False
    assert denied.reason == "per_deployment_orders_per_minute"
    # per-deployment scope: a different deployment is unaffected
    assert rb.check("entry", "other").allowed


def test_minute_window_recovery():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    for _ in range(10):
        rb.record("entry", "dep")
    assert rb.check("entry", "dep").allowed is False
    clock.advance(60.0)  # all 10 events aged out of the sliding window
    assert rb.check("entry", "dep").allowed


def test_trip_at_two_hundred_orders_per_day_per_deployment():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    t = 0.0
    for _ in range(200):
        rb.record("entry", "dep", now=t)
        t += 7.0  # spread so the per-minute window never trips
    denied = rb.check("entry", "dep", now=t)
    assert denied.allowed is False
    assert denied.reason == "per_deployment_orders_per_day"
    # recovery: the oldest orders age out of the 24h window
    assert rb.check("entry", "dep", now=t + 86400.0).allowed


def test_trip_at_seventyfive_fleet_entries_per_minute():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    for i in range(75):
        rb.record("entry", f"dep{i % 8}")  # no single dep hits its own 10/min
    denied = rb.check("entry", "fresh")
    assert denied.allowed is False
    assert denied.reason == "fleet_entries_per_minute"
    clock.advance(60.0)
    assert rb.check("entry", "fresh").allowed


def test_trip_at_five_hundred_fleet_entries_per_day():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    t = 0.0
    for i in range(500):
        rb.record("entry", f"dep{i % 8}", now=t)
        t += 61.0  # spaced beyond any minute window
    denied = rb.check("entry", "fresh", now=t)
    assert denied.allowed is False
    assert denied.reason == "fleet_entries_per_day"
    assert rb.check("entry", "fresh", now=t + 86400.0).allowed


def test_five_second_entry_cooldown_after_exit():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    rb.record("exit", "dep")  # arms the cooldown at t=0
    at_3s = rb.check("entry", "dep", now=3.0)
    assert at_3s.allowed is False
    assert at_3s.reason == "post_exit_entry_cooldown"
    at_5s = rb.check("entry", "dep", now=5.0)
    assert at_5s.allowed is True  # exactly 5s later: cooldown expired


def test_cooldown_blocks_only_entries():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    rb.record("exit", "dep", now=0.0)
    assert rb.check("exit", "dep", now=0.1).allowed is True  # exit never blocked
    assert rb.check("entry", "dep", now=0.1).allowed is False


def test_exit_privileged_with_every_breaker_armed_or_tripped():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    t = 0.0
    for _ in range(200):  # per-deployment day budget exhausted
        rb.record("entry", "dep", now=t)
        t += 7.0
    for i in range(500):  # fleet day (and more) exhausted
        rb.record("entry", f"fleet{i % 8}", now=t)
        t += 61.0
    for _ in range(10):  # per-deployment minute tripped right now
        rb.record("entry", "dep", now=t)
        t += 0.1
    rb.record("exit", "dep", now=t)  # arms the cooldown
    entry = rb.check("entry", "dep", now=t + 0.1)
    assert entry.allowed is False
    assert entry.reason == "post_exit_entry_cooldown"
    exit_decision = rb.check("exit", "dep", now=t + 0.1)
    assert exit_decision.allowed is True


def test_denials_consume_no_rate_budget():
    clock = FakeClock()
    rb = RateBreakers(clock=clock)
    for _ in range(10):
        rb.record("entry", "dep")
    before = rb.check("entry", "dep")
    assert before.allowed is False
    for _ in range(5):  # repeated denied attempts must not extend the trip
        assert rb.check("entry", "dep").allowed is False
    clock.advance(60.0)
    assert rb.check("entry", "dep").allowed
