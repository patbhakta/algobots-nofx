"""Market session calendars (A05 acceptance case 3).

Two calendar families ship with A05:

- ``24x7`` — continuous trading (spot crypto, perpetual swaps): always open.
- US equity exchange sessions (``XNYS``/``XNAS``) — Mon-Fri 09:30-16:00 in
  ``America/New_York``. Weekend closures and DST transitions fall out of the
  zoneinfo arithmetic: the session is defined on wall-clock time, so the UTC
  mapping shifts with the transition. Exchange holidays are NOT modeled
  (recorded as a limitation).

Unknown calendars fail closed: the market reports closed with an explicit
reason, so unknown metadata blocks new exposure (A05 recovery rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = ["SessionState", "market_session", "is_open"]

_CONTINUOUS = "24x7"
# Weekday wall-clock sessions per calendar key (open, close) in local time.
_WEEKDAY_SESSIONS: dict[str, tuple[time, time]] = {
    "XNYS": (time(9, 30), time(16, 0)),
    "XNAS": (time(9, 30), time(16, 0)),
}


@dataclass(frozen=True)
class SessionState:
    open: bool
    reason: str


def market_session(calendar: str, timezone: str, at: datetime) -> SessionState:
    """Resolve the session state of one calendar at ``at`` (any UTC-aware time)."""
    if at.utcoffset() is None:
        raise ValueError("session checks require an offset-aware timestamp")
    if calendar == _CONTINUOUS:
        return SessionState(open=True, reason="continuous-24x7")
    if calendar not in _WEEKDAY_SESSIONS:
        # Fail closed: unknown calendar metadata blocks new exposure.
        return SessionState(open=False, reason=f"unknown-calendar:{calendar}")
    try:
        local = at.astimezone(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return SessionState(open=False, reason=f"unknown-timezone:{timezone}")
    if local.weekday() >= 5:
        return SessionState(open=False, reason=f"weekend:{local.strftime('%a')}")
    opens, closes = _WEEKDAY_SESSIONS[calendar]
    if local.time() < opens:
        return SessionState(open=False, reason="pre-open")
    if local.time() >= closes:
        return SessionState(open=False, reason="post-close")
    return SessionState(open=True, reason=f"regular-session:{calendar}")


def is_open(calendar: str, timezone: str, at: datetime) -> bool:
    return market_session(calendar, timezone, at).open
