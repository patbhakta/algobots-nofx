"""Strategy studio: versioned strategy definitions, fan-out preview, frozen deployments.

A *definition* is a template (or one of the live demo strategies); a
*version* is one typed parameter set for it, frozen as canonical JSON with a
sha256 artifact hash (DSL specs go through ``strategies.dsl``). A deployment
copies the version's parameters and hash at deploy time, so editing a
template — which only ever appends a new version — cannot reach a running
deployment.

The allocation preview is a pure function: (version, accounts, existing
deployments, sizing) -> per-account lines with the allocation, the headroom
left after it, or an explicit skip reason. Deploy re-runs the same preview
server-side, gates each eligible line through the one pre-trade risk gate,
and records only the lines that allocated.

A deploy is a *fan-out campaign* (A11-3): one parent, one independent child
per account — skipped and risk-rejected children included, each with its own
status and reason. The parent state is always derived from the children and
never says "succeeded" unless every child did; one child's failure never
touches another child's fills. Only one active deployment may own entries for
a given (account, instrument): a conflicting version is skipped at preview
with the owning deployment named. A version can be disabled for new
deployments and a campaign paused (new entries held, protective orders left
in place) without deleting any history.

State lives in one JSON file next to the kill switch, written atomically.
"""

from __future__ import annotations

import functools
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from algobots.demo import gate as GATE
from algobots.demo import ledger as L
from algobots.risk import RiskEnvelope
from algobots.strategies import dsl

CENT = L.CENT
_LOCK = threading.RLock()  # load-modify-save of studio.json within this process
MIN_DEPLOY = Decimal("100")  # smallest paper allocation worth running a template on
MAX_ORDER = Decimal("1000")  # per-deployment entry cap: one template never bets more (AC: risk)
STUDIO_ENVELOPE = RiskEnvelope(max_order_value=MAX_ORDER, max_daily_loss=Decimal("1000000"))
TEST_LABEL = "TEST STRATEGY · NO VALIDATED RETURNS"
LIVE_LABEL = "DEPLOYED · PAPER"
Mode = Literal["equal", "pct"]
ACTIVE = ("pending", "running")  # deployment states that own their instruments


class StudioError(ValueError):
    """Bad studio input; the message is user-presentable."""


# --- typed template parameters -------------------------------------------------


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrendParams(_Params):
    symbol: str = Field(default="SPY", pattern=r"^[A-Z]{1,5}$")
    cadence: dsl.Cadence = "1d"
    fast: int = Field(default=20, ge=2, le=400)
    slow: int = Field(default=50, ge=3, le=400)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> TrendParams:
        if self.fast >= self.slow:
            raise ValueError(f"fast ({self.fast}) must be below slow ({self.slow})")
        return self

    def spec(self) -> dsl.StrategySpec:
        def sma(p: int) -> dict:
            return {"indicator": "sma", "params": {"period": p}}

        return dsl.validate_spec(
            {
                "cadence": self.cadence,
                "entry": {"left": sma(self.fast), "op": "crosses_above", "right": sma(self.slow)},
                "exit": {"left": sma(self.fast), "op": "crosses_below", "right": sma(self.slow)},
            }
        )


class RsiParams(_Params):
    symbol: str = Field(default="QQQ", pattern=r"^[A-Z]{1,5}$")
    cadence: dsl.Cadence = "1h"
    period: int = Field(default=14, ge=2, le=200)
    lower: float = Field(default=30, gt=0, lt=100)
    upper: float = Field(default=70, gt=0, lt=100)

    @model_validator(mode="after")
    def _band(self) -> RsiParams:
        if self.lower >= self.upper:
            raise ValueError(f"lower ({self.lower}) must be below upper ({self.upper})")
        return self

    def spec(self) -> dsl.StrategySpec:
        rsi = {"indicator": "rsi", "params": {"period": self.period}}
        return dsl.validate_spec(
            {
                "cadence": self.cadence,
                "entry": {"left": rsi, "op": "lt", "right": {"value": self.lower}},
                "exit": {"left": rsi, "op": "gt", "right": {"value": self.upper}},
            }
        )


class AllocationParams(_Params):
    weights: dict[str, float] = Field(default_factory=lambda: {"SPY": 0.6, "AGG": 0.3, "GLD": 0.1})
    rebalance: Literal["weekly", "monthly", "quarterly"] = "monthly"
    drift_band: float = Field(default=0.05, ge=0, le=0.5)

    @model_validator(mode="after")
    def _weights(self) -> AllocationParams:
        if not self.weights or any(w <= 0 for w in self.weights.values()):
            raise ValueError("weights must be positive and non-empty")
        if abs(sum(self.weights.values()) - 1) > 1e-9:
            raise ValueError(f"weights sum to {sum(self.weights.values()):.4f}, not 1")
        return self

    def spec(self) -> None:
        return None  # rebalancer, not a condition strategy


@dataclass(frozen=True)
class Definition:
    key: str
    name: str
    kind: str  # condition_dsl | allocation | live
    venue: str  # equities | kalshi
    label: str
    params: type[_Params] | None  # None = live strategy, parameters fixed in code


DEFINITIONS: dict[str, Definition] = {
    "trend": Definition(
        "trend", "Trend crossover", dsl.SPEC_KIND, "equities", TEST_LABEL, TrendParams
    ),
    "range_rsi": Definition(
        "range_rsi", "Range / RSI", dsl.SPEC_KIND, "equities", TEST_LABEL, RsiParams
    ),
    "etf_alloc": Definition(
        "etf_alloc",
        "Periodic ETF allocation",
        "allocation",
        "equities",
        TEST_LABEL,
        AllocationParams,
    ),
    **{k: Definition(k, n, "live", "kalshi", LIVE_LABEL, None) for k, n in L.STRATEGIES.items()},
}

# The live demo strategies' effective parameters (ledger.py), frozen like any version.
LIVE_PARAMS: dict[str, dict] = {
    k: {
        "instrument": "KXBTC15M",
        "fill_price": str(L.FILL_PRICE),
        "min_stake": str(L.MIN_STAKE),
        "max_order_value": str(L.ENVELOPE.max_order_value),
        "max_daily_loss": str(L.ENVELOPE.max_daily_loss),
        **({"min_edge": L.LAYA_MIN_EDGE} if k == "laya" else {}),
    }
    for k in L.STRATEGIES
}


@dataclass(frozen=True)
class Version:
    definition: str
    version: int
    params: dict  # canonical, JSON-safe
    hash: str
    spec_hash: str | None = None  # dsl.artifact_hash of the condition spec, when there is one
    created_ts: float = 0.0
    actor: str = "built-in"
    disabled: bool = False  # no new deployments; existing ones and history stay (A11-3 recovery)

    @property
    def short(self) -> str:
        return self.hash[:12]


def canonical(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def freeze(definition: str, params: dict | None, version: int, **meta) -> Version:
    """Validate typed params and freeze them; the hash covers kind + params + DSL spec."""
    d = DEFINITIONS.get(definition)
    if d is None:
        raise StudioError(f"unknown strategy '{definition}'")
    if d.params is None:
        frozen, spec = LIVE_PARAMS[definition], None
    else:
        try:
            model = d.params.model_validate(params or {})
        except ValidationError as exc:
            raise StudioError(_flatten(exc)) from None
        frozen, spec = model.model_dump(mode="json"), model.spec()
    doc = {"definition": definition, "kind": d.kind, "params": frozen}
    if spec is not None:
        doc["spec"] = json.loads(dsl.canonical_json(spec))
    digest = hashlib.sha256(canonical(doc).encode()).hexdigest()
    return Version(
        definition,
        version,
        json.loads(canonical(frozen)),
        digest,
        dsl.artifact_hash(spec) if spec is not None else None,
        **meta,
    )


def _flatten(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'params'}: {err['msg']}"
        for err in exc.errors(include_url=False)
    )


BUILTIN: list[Version] = [freeze(k, {}, 1) for k in DEFINITIONS]


# --- accounts + deployments ------------------------------------------------------


@dataclass(frozen=True)
class Account:
    id: str
    label: str
    venue: str
    environment: str
    approved: Decimal  # approved paper allocation ceiling


ACCOUNTS: dict[str, Account] = {
    "eq-a": Account("eq-a", "Pat · Equities paper A", "equities", "PAPER", Decimal("1000")),
    "eq-b": Account("eq-b", "Pat · Equities paper B", "equities", "PAPER", Decimal("2500")),
    "eq-c": Account("eq-c", "Pat · Equities paper C", "equities", "PAPER", Decimal("500")),
    **{k: Account(k, n, "kalshi", "PAPER", L.SLEEVE) for k, n in L.STRATEGIES.items()},
}


@dataclass(frozen=True)
class Deployment:
    id: str
    account: str
    definition: str
    version: int
    hash: str
    params: dict  # copied at deploy time — never re-read from the version
    allocation: str
    created_ts: float
    actor: str
    state: str  # running (worker heartbeating) | pending (awaiting its template worker)


LIVE_DEPLOYMENTS: list[Deployment] = [
    Deployment(
        f"dep-{k}-live",
        k,
        k,
        1,
        v.hash,
        dict(v.params),
        str(L.SLEEVE),
        0.0,
        "built-in",
        "running",
    )
    for k in L.STRATEGIES
    for v in BUILTIN
    if v.definition == k
]


# --- fan-out campaigns (A11-3) ------------------------------------------------------


@dataclass(frozen=True)
class Child:
    """One account's slice of a campaign. ``status`` is the deploy-time outcome
    (skipped / rejected-by-risk / pending); the live state is derived from the
    deployment and its order log by :func:`child_view`."""

    account: str
    deployment: str | None = None
    allocation: str = "0"
    status: str = "pending"
    reason: str = ""


@dataclass(frozen=True)
class Campaign:
    id: str
    version: str  # artifact hash the campaign froze
    definition: str
    mode: Mode
    requested: str
    created_ts: float
    actor: str
    paused: bool = False
    paused_ts: float | None = None
    paused_by: str = ""
    children: list[Child] = field(default_factory=list)


def instruments(params: dict, definition: str) -> list[str]:
    """The instruments a deployment trades: its entry targets, frozen at deploy."""
    if definition == "etf_alloc":
        return sorted(params.get("weights", {}))
    if "symbol" in params:
        return [params["symbol"]]
    if "instrument" in params:  # the live demo strategies trade one contract
        return [params["instrument"]]
    return []


def owners(st: Studio) -> dict[tuple[str, str], Deployment]:
    """(account, instrument) -> the active deployment that owns entries for it (AC4).

    The oldest active deployment wins a duplicate recording; a deployment that
    is no longer active owns nothing.
    """
    own: dict[tuple[str, str], Deployment] = {}
    for d in st.deployments:
        if d.state not in ACTIVE:
            continue
        for sym in instruments(d.params, d.definition):
            own.setdefault((d.account, sym), d)
    return own


@dataclass
class Studio:
    versions: list[Version]
    deployments: list[Deployment]
    campaigns: list[Campaign] = field(default_factory=list)
    # version hash -> {"by": str, "ts": float}
    disabled: dict[str, dict] = field(default_factory=dict)

    def latest(self, definition: str) -> Version:
        return max(
            (v for v in self.versions if v.definition == definition), key=lambda v: v.version
        )

    def by_hash(self, h: str) -> Version | None:
        return next((v for v in self.versions if v.hash == h or v.short == h), None)

    def committed(self, account: str) -> Decimal:
        return sum(
            (Decimal(d.allocation) for d in self.deployments if d.account == account), Decimal(0)
        )

    def campaign_of(self, dep_id: str) -> Campaign | None:
        return next(
            (c for c in self.campaigns if any(ch.deployment == dep_id for ch in c.children)), None
        )


def _path(state_dir: str) -> Path:
    return Path(state_dir) / "studio.json"


def _campaign(d: dict) -> Campaign:
    return Campaign(**{**d, "children": [Child(**ch) for ch in d.get("children", [])]})


def load(state_dir: str) -> Studio:
    p = _path(state_dir)
    raw = json.loads(p.read_text()) if p.exists() else {"versions": [], "deployments": []}
    disabled = raw.get("disabled") or {}
    recorded = [Version(**v) for v in raw["versions"]]
    versions = [replace(v, disabled=v.hash in disabled) for v in BUILTIN + recorded]
    return Studio(
        versions,
        LIVE_DEPLOYMENTS + [Deployment(**d) for d in raw["deployments"]],
        [_campaign(c) for c in raw.get("campaigns", [])],
        {h: dict(m) for h, m in disabled.items() if h in {v.hash for v in versions}},
    )


def _save(state_dir: str, st: Studio) -> None:
    p = _path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "versions": [asdict(v) for v in st.versions if v.actor != "built-in"],
        "deployments": [asdict(d) for d in st.deployments if d.actor != "built-in"],
        "campaigns": [asdict(c) for c in st.campaigns],
        "disabled": st.disabled,
    }
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    tmp.replace(p)


def _locked(fn):
    @functools.wraps(fn)
    def run(*a, **kw):
        with _LOCK:
            return fn(*a, **kw)

    return run


@_locked
def edit(
    state_dir: str, definition: str, params: dict, *, actor: str, now: float | None = None
) -> Version:
    """Append a new version of a template. Running deployments keep their frozen copy."""
    st = load(state_dir)
    if DEFINITIONS.get(definition) is None or DEFINITIONS[definition].params is None:
        raise StudioError(f"'{definition}' is not an editable template")
    prev = st.latest(definition)
    ts = time.time() if now is None else now
    v = freeze(definition, params, prev.version + 1, created_ts=ts, actor=actor)
    if v.hash == prev.hash:
        return prev  # no-op edit: same parameters, same artifact
    st.versions.append(v)
    _save(state_dir, st)
    return v


# --- allocation preview ----------------------------------------------------------


@dataclass(frozen=True)
class Line:
    account: str
    label: str
    approved: Decimal
    available: Decimal  # approved - already committed
    allocation: Decimal  # 0 when skipped
    residual: Decimal  # headroom left on the account after this allocation
    skip: str | None = None


@dataclass(frozen=True)
class Preview:
    version: Version
    mode: Mode
    requested: Decimal  # equal: the total; pct: sum of per-account targets
    lines: list[Line] = field(default_factory=list)

    @property
    def allocated(self) -> Decimal:
        return sum((ln.allocation for ln in self.lines), Decimal(0))

    @property
    def undeployed(self) -> Decimal:
        return self.requested - self.allocated

    @property
    def deployable(self) -> list[Line]:
        return [ln for ln in self.lines if ln.skip is None]


def _cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_DOWN)  # never allocate a cent that isn't there


def preview(
    st: Studio,
    version: Version,
    accounts: list[str],
    *,
    mode: Mode,
    amount: Decimal | None = None,
    pct: Decimal | None = None,
    kill_engaged: bool = False,
    visible: set[str] | None = None,
) -> Preview:
    """Fan one version out across accounts: equal dollars, or % of each approved allocation.

    Equal: the total is split evenly across *eligible* accounts, rounded down
    to the cent; a share above an account's headroom is capped there and the
    excess is reported as undeployed, never redistributed silently. A line
    below ``MIN_DEPLOY`` is skipped with its reason.
    """
    if mode == "equal":
        if amount is None or amount <= 0:
            raise StudioError("equal-dollar mode needs a total amount above 0")
    elif mode == "pct":
        if pct is None or not (0 < pct <= 100):
            raise StudioError("percent mode needs a percentage in (0, 100]")
    else:
        raise StudioError(f"unknown sizing mode '{mode}'")
    if not accounts:
        raise StudioError("select at least one account")
    d = DEFINITIONS[version.definition]
    own = owners(st)
    mine = instruments(version.params, version.definition)
    meta = st.disabled.get(version.hash, {})

    def gate(key: str) -> str | None:
        a = ACCOUNTS.get(key)
        if a is None or (visible is not None and key not in visible):
            return "unknown account"  # ungranted reads exactly like unknown: nothing leaks
        if version.disabled:
            by = f" (by {meta['by']})" if meta.get("by") else ""
            return f"version {version.short} is disabled for new deployments{by}"
        if a.environment != "PAPER":
            return "not a paper account — the studio deploys to paper only"
        if kill_engaged:
            return "kill switch engaged — no new deployments"
        if d.kind == "live":
            return "demo strategy is pinned to its own sleeve; deploy a template instead"
        if a.venue != d.venue:
            return f"{d.venue} strategy cannot trade on a {a.venue} account"
        dup = next((x for x in st.deployments if x.account == key and x.hash == version.hash), None)
        if dup:
            return f"version {version.short} already deployed here ({dup.id})"
        conflict = next((own.get((key, sym)) for sym in mine if (key, sym) in own), None)
        if conflict is not None:  # AC4: one active deployment owns an account/instrument
            sym = next(sym for sym in mine if (key, sym) in own)
            o = DEFINITIONS[conflict.definition]
            return (
                f"{sym} on {key} is owned by {o.name} v{conflict.version} ({conflict.id})"
            )
        if a.approved - st.committed(key) <= 0:
            return f"no headroom: {st.committed(key)} of {a.approved} USD already committed"
        return None

    keys = list(dict.fromkeys(accounts))  # de-dup, keep order
    reasons = {k: gate(k) for k in keys}
    eligible = [k for k in keys if reasons[k] is None]
    share = _cents(amount / len(eligible)) if mode == "equal" and eligible else Decimal(0)
    lines, requested = [], Decimal(0)
    for k in keys:
        a = ACCOUNTS.get(k) if visible is None or k in visible else None
        approved = a.approved if a else Decimal(0)
        avail = max(Decimal(0), approved - st.committed(k))
        why = reasons[k]
        alloc = Decimal(0)
        if why is None:
            target = share if mode == "equal" else _cents(approved * pct / 100)
            requested += target if mode == "pct" else 0
            alloc = min(target, avail)
            if alloc < MIN_DEPLOY:
                why = f"{alloc} USD is below the {MIN_DEPLOY} USD minimum" + (
                    f" (headroom {avail})" if alloc < target else ""
                )
                alloc = Decimal(0)
        lines.append(Line(k, a.label if a else k, approved, avail, alloc, avail - alloc, why))
    return Preview(version, mode, amount if mode == "equal" else requested, lines)


def _risk_check(
    account: str, allocation: Decimal, *, kill_engaged: bool, now: float
) -> str | None:
    """The one pre-trade gate (``demo.gate``) for one child at deploy time; None
    = allowed through. A clamp is a refusal, not a fill over the cap — same
    doctrine as the order-ticket broadcast."""
    g = GATE.pre_trade(
        GATE.GateRequest(
            account=account,
            path="deploy",
            value=allocation,
            equity=ACCOUNTS[account].approved,
            floor=MIN_DEPLOY,
            daily_pnl=Decimal(0),
            kill_engaged=kill_engaged,
            kind="entry",
            mode="PAPER",
            now=now,
        ),
        GATE.risk_gate(STUDIO_ENVELOPE),
    )
    if not g.allowed:
        return f"blocked by risk gate — {g.reason}"
    if g.approved < allocation:
        return (
            f"blocked by risk gate — {allocation} USD over max order value; "
            f"gate allows {g.approved} USD per deployment"
        )
    return None


@_locked
def deploy(
    state_dir: str,
    h: str,
    accounts: list[str],
    *,
    mode: Mode,
    amount: Decimal | None = None,
    pct: Decimal | None = None,
    kill_engaged: bool = False,
    visible: set[str] | None = None,
    actor: str,
    now: float | None = None,
) -> tuple[Preview, list[Deployment], Campaign]:
    """Recompute the preview server-side, gate each eligible line through the
    risk gate, and record one campaign parent with one independent child per
    account — skipped and rejected children included. There is no cross-account
    atomicity: one child's outcome never reverses another's."""
    st = load(state_dir)
    v = st.by_hash(h)
    if v is None:
        raise StudioError(f"unknown strategy version '{h}'")
    pv = preview(
        st,
        v,
        accounts,
        mode=mode,
        amount=amount,
        pct=pct,
        kill_engaged=kill_engaged,
        visible=visible,
    )
    ts = time.time() if now is None else now
    made: list[Deployment] = []
    children: list[Child] = []
    for ln in pv.lines:
        if ln.skip:
            children.append(Child(ln.account, None, "0", "skipped", ln.skip))
            continue
        why = _risk_check(ln.account, ln.allocation, kill_engaged=kill_engaged, now=ts)
        if why is not None:
            children.append(Child(ln.account, None, "0", "rejected-by-risk", why))
            continue
        dep = Deployment(
            f"dep-{v.hash[:8]}-{ln.account}",
            ln.account,
            v.definition,
            v.version,
            v.hash,
            json.loads(canonical(v.params)),
            str(ln.allocation),
            ts,
            actor,
            "pending",
        )
        made.append(dep)
        children.append(Child(ln.account, dep.id, dep.allocation, "pending"))
    campaign = Campaign(
        f"cmp-{v.hash[:8]}-{len(st.campaigns) + 1}",
        v.hash,
        v.definition,
        pv.mode,
        str(pv.requested),
        ts,
        actor,
        children=children,
    )
    st.deployments.extend(made)
    st.campaigns.append(campaign)
    _save(state_dir, st)  # the campaign is history even when every child was skipped
    return pv, made, campaign


# --- live campaign state ------------------------------------------------------------


def child_view(c: Child, st: Studio, orders: list[dict]) -> tuple[str, str]:
    """(status, reason) for one child now: deploy-time skips/rejections stand;
    otherwise derived from the deployment state and its order log."""
    if c.status != "pending":
        return c.status, c.reason
    dep = next((d for d in st.deployments if d.id == c.deployment), None)
    if dep is None:
        return "skipped", "deployment not found"
    fills = [o for o in orders if o.get("deployment") == dep.id and o["status"] == "filled"]
    blocks = [o for o in orders if o.get("deployment") == dep.id and o["status"] == "blocked"]
    if not fills and not blocks:
        return dep.state, ""  # pending (worker not ready yet) | running (no signal yet)
    if fills and not blocks:
        return "filled", f"{len(fills)} orders filled"
    if fills and blocks:
        return "partially-filled", f"{len(blocks)} of {len(fills) + len(blocks)} orders blocked"
    return "rejected-by-risk", blocks[-1]["reason"]


def campaign_state(cmp: Campaign, states: list[str]) -> tuple[str, int, int]:
    """Derived parent state — never stored, and never 'succeeded' unless every
    child succeeded (AC5). Returns (state, succeeded, total)."""
    n, ok = len(states), states.count("filled")
    if n == 0:
        return "pending", 0, 0
    if all(s == "skipped" for s in states):
        return "rejected", ok, n
    if ok == n:
        return "succeeded", ok, n
    if any(s in ("pending", "running", "partially-filled") for s in states):
        return "running", ok, n
    return "partial", ok, n


def campaign_display(cmp: Campaign, states: list[str]) -> str:
    state, ok, n = campaign_state(cmp, states)
    label = "paused" if cmp.paused else state
    return label.upper() + (f" · {ok}/{n}" if n else "")


@_locked
def set_disabled(
    state_dir: str, h: str, *, disabled: bool, actor: str, now: float | None = None
) -> Version:
    """Flag a version so no new deployments may use it. Existing deployments and
    the version's history stay untouched (A11-3 recovery)."""
    st = load(state_dir)
    v = st.by_hash(h)
    if v is None:
        raise StudioError(f"unknown strategy version '{h}'")
    if disabled:
        st.disabled[v.hash] = {"by": actor, "ts": time.time() if now is None else now}
    else:
        st.disabled.pop(v.hash, None)
    _save(state_dir, st)
    return replace(v, disabled=disabled)


@_locked
def pause_campaign(
    state_dir: str, cmp_id: str, *, paused: bool, actor: str, now: float | None = None
) -> Campaign:
    """Pause/resume a campaign: paused stops *new* entries on every child; exits
    and other already-placed protective orders are left in place."""
    st = load(state_dir)
    i = next((i for i, c in enumerate(st.campaigns) if c.id == cmp_id), None)
    if i is None:
        raise StudioError(f"unknown campaign '{cmp_id}'")
    ts = time.time() if now is None else now
    st.campaigns[i] = replace(
        st.campaigns[i],
        paused=paused,
        paused_ts=ts if paused else None,
        paused_by=actor if paused else "",
    )
    _save(state_dir, st)
    return st.campaigns[i]


def set_state(state_dir: str, dep_id: str, state: str) -> bool:
    """Flip one recorded deployment's run state (pending -> running); True if it changed."""
    with _LOCK:
        st = load(state_dir)
        i = next((i for i, d in enumerate(st.deployments) if d.id == dep_id), None)
        if i is None or st.deployments[i].actor == "built-in" or st.deployments[i].state == state:
            return False
        st.deployments[i] = replace(st.deployments[i], state=state)
        _save(state_dir, st)
        return True


def visible(granted: tuple[str, ...] | set[str]) -> set[str]:
    """Accounts a caller may see in the studio: granted Kalshi sleeves + the equity paper
    accounts (not under the A10-3 grant model yet)."""
    return set(granted) | {k for k, a in ACCOUNTS.items() if a.venue == "equities"}


def attribution(st: Studio) -> dict[str, Deployment]:
    """account -> its live deployment, for tagging ledger orders."""
    return {d.account: d for d in st.deployments if d.state == "running"}
