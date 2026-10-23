"""NoFX Strategy Studio compat surface (ALG-3414): the funder demo on :8201.

The NoFX frontend speaks a Go-backend dialect (``POST /api/login`` returning
``token/user_id/email/tenant_id``, ``/api/strategies`` CRUD). Its nginx maps
those paths onto this ``/api/nofx`` prefix, so the browser authenticates
against the real A03 gate: invite-only registration, DB-bound sessions,
live-user and membership re-checks on every request. There is no second login
and no open proxy to the synthetic-principal ``/demo`` routes — every read here
needs a live session.

``/api/nofx/studio/live`` is the funder evidence feed: Kalshi observer
timestamps, logged decisions with their risk verdicts, and the actual Nautilus
paper-fill receipts from the worker heartbeats, correlated per decision.
Nothing is synthesised: missing or stale inputs are reported as such.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.config import get_settings
from algobots.api.database import get_db
from algobots.api.dependencies import AuthContext, get_auth_context
from algobots.api.memberships import service as memberships
from algobots.api.models import InviteCode, Strategy, User, UserRole
from algobots.api.routers import auth as auth_routes
from algobots.api.routers import studio as studio_routes
from algobots.api.schemas import RegisterRequest
from algobots.api.security import create_access_token, verify_password
from algobots.contracts.identity import Grant, IdentityKind, Principal
from algobots.strategies.studio import StudioError, translate_nofx_config

router = APIRouter(prefix="/api/nofx", tags=["nofx-studio"])

compat_router = APIRouter(tags=["nofx-studio"])

STUDIO_KIND = "nofx-studio"
FEED_STALE_S = 20 * 60  # observer writes once per 15-min interval
WORKER_STALE_S = 90  # workers heartbeat every poll (15 s)
DECISIONS_PER_STRATEGY = 24


def _error(code: int, message: str) -> JSONResponse:
    """NoFX reads ``error`` from failed auth responses."""
    return JSONResponse({"error": message}, status_code=code)


def _session_payload(db: Session, user: User) -> dict:
    session = memberships.start_session(db, user)
    db.commit()
    return {
        "token": create_access_token(user.id, session.id),
        "user_id": str(user.id),
        "email": user.email,
        "tenant_id": str(session.tenant_id) if session.tenant_id else None,
        "role": user.role,
        "expires_in": get_settings().access_token_expire_minutes * 60,
    }


# --- auth (the existing invite gate, NoFX-shaped) ---


class NofxLogin(BaseModel):
    email: EmailStr
    password: str


class NofxRegister(BaseModel):
    email: EmailStr
    password: str
    beta_code: str | None = None  # NoFX's name for the invite code
    lang: str | None = None


@router.get("/config")
def nofx_config() -> dict:
    """Public: registration is invite-only, so the register form demands a code."""
    return {"initialized": True, "beta_mode": True, "registration_enabled": True}


@router.post("/login")
def nofx_login(payload: NofxLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        return _error(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        return _error(status.HTTP_401_UNAUTHORIZED, "Access revoked")
    return _session_payload(db, user)


@router.post("/register")
def nofx_register(payload: NofxRegister, db: Session = Depends(get_db)):
    """Redeem an owner-minted invite (single use, expiring); then sign in."""
    if not payload.beta_code or not payload.beta_code.strip():
        return _error(status.HTTP_400_BAD_REQUEST, "An invite code is required")
    try:
        req = RegisterRequest(
            email=payload.email,
            password=payload.password,
            display_name=payload.email.split("@")[0][:120] or "funder",
            invite_code=payload.beta_code.strip(),
        )
    except ValidationError as e:
        return _error(status.HTTP_400_BAD_REQUEST, e.errors()[0]["msg"])
    try:
        auth_routes.register(req, db)
    except HTTPException as e:
        return _error(status.HTTP_409_CONFLICT, str(e.detail))
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    return _session_payload(db, user)


@router.post("/logout")
def nofx_logout(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    ctx.session.revoked_at = datetime.now(UTC)
    db.commit()
    return {"message": "signed out"}


# --- owner: funder invites and access revocation ---


def _owner(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if ctx.user.role != UserRole.OWNER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the platform owner manages invites")
    return ctx


def _invite_row(db: Session, inv: InviteCode, show_code: bool = False) -> dict:
    claimed = db.get(User, inv.claimed_by_user_id) if inv.claimed_by_user_id else None
    expires = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=UTC)
    if claimed is not None:
        state = "active" if claimed.is_active else "revoked"
    else:
        state = "expired" if expires <= datetime.now(UTC) else "open"
    return {
        "id": str(inv.id),
        # The code is shown once, at mint time; listings carry only a hint.
        "code": inv.code if show_code else None,
        "code_hint": f"{inv.code[:8]}…",
        "state": state,
        "expires_at": expires.isoformat(),
        "created_at": inv.created_at.isoformat(),
        "claimed_at": inv.claimed_at.isoformat() if inv.claimed_at else None,
        "claimed_by": None
        if claimed is None
        else {"user_id": str(claimed.id), "email": claimed.email, "active": claimed.is_active},
    }


@router.get("/studio/me")
def studio_me(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    return {
        "user_id": str(ctx.user.id),
        "email": ctx.user.email,
        "role": ctx.user.role,
        "tenant_id": str(ctx.tenant_id) if ctx.tenant_id else None,
        "can_mint_invites": ctx.user.role == UserRole.OWNER.value,
    }


@router.get("/studio/invites")
def list_invites(ctx: AuthContext = Depends(_owner), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(InviteCode)
        .where(InviteCode.created_by_user_id == ctx.user.id)
        .order_by(InviteCode.created_at.desc())
    )
    return {"invites": [_invite_row(db, i) for i in rows]}


@router.post("/studio/invites", status_code=status.HTTP_201_CREATED)
def mint_invite(ctx: AuthContext = Depends(_owner), db: Session = Depends(get_db)) -> dict:
    """A single-use, expiring platform invite (the P2.1 gate's own code format)."""
    inv = InviteCode(
        code=f"ALG-{secrets.token_urlsafe(18)}",
        created_by_user_id=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().invite_expire_days),
    )
    db.add(inv)
    db.commit()
    return _invite_row(db, inv, show_code=True)


def _my_invite(db: Session, ctx: AuthContext, invite_id: UUID) -> InviteCode:
    inv = db.get(InviteCode, invite_id)
    if inv is None or inv.created_by_user_id != ctx.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    return inv


@router.post("/studio/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: UUID, ctx: AuthContext = Depends(_owner), db: Session = Depends(get_db)
) -> dict:
    """Unclaimed: expire the code now. Claimed: deactivate that funder and kill
    every session they hold, so the next request 401s."""
    inv = _my_invite(db, ctx, invite_id)
    if inv.claimed_by_user_id is None:
        inv.expires_at = datetime.now(UTC)
    else:
        funder = db.get(User, inv.claimed_by_user_id)
        if funder is None or funder.id == ctx.user.id or funder.role == UserRole.OWNER.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "Owner access cannot be revoked here")
        funder.is_active = False
        memberships.revoke_sessions(db, funder.id)
    db.commit()
    return _invite_row(db, inv)


# --- Studio strategy configs (tenant-scoped, stored in our strategies table) ---


class StudioStrategyIn(BaseModel):
    name: str = Field(default="Studio strategy", min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False
    config_visible: bool = False


def _tenant(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active tenant membership")
    return ctx.tenant_id


def _studio_rows(db: Session, tenant_id: UUID) -> list[Strategy]:
    return list(
        db.scalars(
            select(Strategy)
            .where(Strategy.tenant_id == tenant_id, Strategy.kind == STUDIO_KIND)
            .order_by(Strategy.created_at)
        )
    )


def _studio_or_404(db: Session, tenant_id: UUID, strategy_id: str) -> Strategy:
    try:
        sid = UUID(strategy_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found") from None
    row = db.get(Strategy, sid)
    if row is None or row.tenant_id != tenant_id or row.kind != STUDIO_KIND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    return row


def _out(row: Strategy) -> dict:
    p = row.params
    return {
        "id": str(row.id),
        "name": row.name,
        "description": p.get("description", ""),
        "is_active": bool(p.get("active")),
        "is_default": False,
        "is_public": False,
        "config_visible": False,
        "config": p.get("config", {}),
        # Saved here; execution stays on the Nautilus paper loop (see /studio/live).
        "execution": "config-only",
        # ALG-3408: the same save, through the /api/studio draft + compile contract.
        "studio": p.get("studio"),
        "created_at": row.created_at.isoformat(),
        "updated_at": (row.updated_at or row.created_at).isoformat(),
    }


def _save(row: Strategy, **params: Any) -> None:
    row.params_json = json.dumps({**row.params, **params}, sort_keys=True)


def _sync_studio(db: Session, ctx: AuthContext, row: Strategy) -> None:
    """Save the NoFX config through the Studio draft contract, then compile it.

    The NoFX row keeps the user's config as typed; `studio` records the linked
    draft, its revision and the compiled artifact, or the owning field of the
    translation/compile error. Errors never block the NoFX save itself.
    """
    p = row.params
    link = p.get("studio") or {}
    try:
        draft, warnings = translate_nofx_config(row.name, p.get("config") or {})
        if link.get("draft_id"):
            d = studio_routes._draft_or_404(db, row.tenant_id, link["draft_id"])
            if d.params["draft"] != studio_routes.parse_draft(draft).model_dump(mode="json"):
                studio_routes.revise_draft(d, d.params["revision"], draft)
        else:
            d = studio_routes.save_draft(db, ctx, draft)
        rec, _ = studio_routes.compile_draft(db, ctx, d)
        studio = {
            "status": "compiled",
            "draft_id": str(d.id),
            "revision": d.params["revision"],
            "artifact_hash": rec["artifact_hash"],
            "implementation": rec["implementation"],
            "strategy_id": rec["strategy_id"],
            "deployable": rec["deployable"],
            "warnings": warnings + rec["warnings"],
        }
    except StudioError as exc:
        studio = {"status": "invalid", "draft_id": link.get("draft_id"), **exc.to_dict()}
    _save(row, studio=studio)


def _momentum_config() -> dict:
    from algobots.demo import ledger as L

    return {
        "strategy_type": "ai_trading",
        "language": "en",
        "ai_config": {
            "coin_source": {
                "source_type": "static",
                "static_coins": ["KXBTC15M"],
                "use_ai500": False,
                "use_oi_top": False,
                "use_oi_low": False,
            },
            "indicators": {
                "klines": {
                    "primary_timeframe": "15m",
                    "primary_count": 20,
                    "enable_multi_timeframe": False,
                },
                "enable_raw_klines": True,
                "enable_volume": False,
                **{
                    f"enable_{k}": False
                    for k in ("ema", "macd", "rsi", "atr", "boll", "oi", "funding_rate")
                },
            },
            "custom_prompt": (
                "Kalshi BTC 15m: mom3x15m/vol20 P(up); "
                f"abstain within ±{L.LAYA_MIN_EDGE} of 0.50. Paper only."
            ),
            "risk_control": {
                "max_positions": 1,
                "btc_eth_max_leverage": 1,
                "altcoin_max_leverage": 1,
                "max_margin_usage": 1,
                "min_position_size": float(L.MIN_STAKE),
                "min_risk_reward_ratio": 1,
                "min_confidence": 0,
            },
        },
        "demo_worker": {
            "account": "laya",
            "p_source": "mom3x15m/vol20",
            "min_edge": L.LAYA_MIN_EDGE,
            "max_order_value": str(L.ENVELOPE.max_order_value),
            "max_daily_loss": str(L.ENVELOPE.max_daily_loss),
            "execution": "config-only",
        },
    }


@router.get("/strategies")
def list_strategies(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    tenant_id = _tenant(ctx)
    rows = _studio_rows(db, tenant_id)
    if not rows:
        row = Strategy(
            tenant_id=tenant_id,
            user_id=ctx.user.id,
            name="Kalshi BTC 15m momentum",
            kind=STUDIO_KIND,
            params_json=json.dumps(
                {
                    "description": (
                        "Demo Laya momentum configuration. "
                        "Saved drafts do not reconfigure the running paper worker."
                    ),
                    "config": _momentum_config(),
                    "active": False,
                }
            ),
        )
        db.add(row)
        db.flush()
        _sync_studio(db, ctx, row)
        db.commit()
        rows = [row]
    return {"strategies": [_out(r) for r in rows]}


@router.get("/strategies/active")
def active_strategy(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    for r in _studio_rows(db, _tenant(ctx)):
        if r.params.get("active"):
            return _out(r)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No active strategy")


@router.get("/strategies/default-config")
def default_config(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    _tenant(ctx)
    return _momentum_config()


@router.post("/strategies", status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: StudioStrategyIn,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    tenant_id = _tenant(ctx)
    row = Strategy(
        tenant_id=tenant_id,
        user_id=ctx.user.id,
        name=payload.name,
        kind=STUDIO_KIND,
        params_json=json.dumps(
            {"description": payload.description, "config": payload.config, "active": False}
        ),
    )
    db.add(row)
    db.flush()
    _sync_studio(db, ctx, row)
    db.commit()
    return _out(row)


@router.get("/strategies/{strategy_id}")
def get_strategy(
    strategy_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    return _out(_studio_or_404(db, _tenant(ctx), strategy_id))


@router.put("/strategies/{strategy_id}")
def update_strategy(
    strategy_id: str,
    payload: StudioStrategyIn,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    row = _studio_or_404(db, _tenant(ctx), strategy_id)
    row.name = payload.name
    _save(row, description=payload.description, config=payload.config)
    _sync_studio(db, ctx, row)
    db.commit()
    return _out(row)


@router.delete("/strategies/{strategy_id}")
def delete_strategy(
    strategy_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    db.delete(_studio_or_404(db, _tenant(ctx), strategy_id))
    db.commit()
    return {"message": "deleted"}


@router.post("/strategies/{strategy_id}/activate")
def activate_strategy(
    strategy_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    tenant_id = _tenant(ctx)
    target = _studio_or_404(db, tenant_id, strategy_id)
    for r in _studio_rows(db, tenant_id):
        _save(r, active=r.id == target.id)
    db.commit()
    return _out(target)


@router.post("/strategies/{strategy_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_strategy(
    strategy_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
):
    tenant_id = _tenant(ctx)
    src = _studio_or_404(db, tenant_id, strategy_id)
    row = Strategy(
        tenant_id=tenant_id,
        user_id=ctx.user.id,
        name=f"{src.name} (copy)"[:120],
        kind=STUDIO_KIND,
        params_json=json.dumps({**src.params, "active": False, "studio": None}),
    )
    db.add(row)
    db.flush()
    _sync_studio(db, ctx, row)
    db.commit()
    return _out(row)


# --- live evidence: Kalshi feed -> decisions -> Nautilus paper receipts ---


def _feed_status(path: Path, now: float) -> dict:
    out: dict[str, Any] = {
        "source": "Kalshi KXBTC15M public market data (read-only observer)",
        "state": "unavailable",
    }
    try:
        lines = path.read_text().splitlines()
    except OSError:
        out["reason"] = "observer feed not readable"
        return out
    rows = []
    for line in lines[-6:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    if not rows:
        out["reason"] = "observer feed is empty"
        return out
    last = rows[-1]
    age = now - float(last.get("ts") or 0)
    out.update(
        state="stale" if age > FEED_STALE_S else "live",
        last_observed_ts=last.get("ts"),
        age_s=round(age, 1),
        event=last.get("event"),
        market=last.get("market"),
        strike=last.get("strike"),
        yes_bid=last.get("mkt_yes_bid"),
        yes_ask=last.get("mkt_yes_ask"),
        open_ts=last.get("open_ts"),
        close_ts=last.get("close_ts"),
        recent=[
            {
                "event": r.get("event"),
                "ts": r.get("ts"),
                "strike": r.get("strike"),
                "outcome": r.get("outcome"),
                "settle_value": r.get("settle_value"),
                "settled_ts": r.get("settled_ts"),
            }
            for r in reversed(rows)
        ],
    )
    if out["state"] == "stale":
        out["reason"] = (
            f"no observer row for {int(age // 60)} min (Kalshi maintenance or observer down)"
        )
    return out


def _worker(state_dir: Path, account: str, now: float) -> dict:
    path = state_dir / "workers" / f"{account}.json"
    try:
        hb = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"account": account, "state": "unavailable", "fills": [], "positions": []}
    age = now - float(hb.get("last_heartbeat") or 0)
    fills = hb.get("fills") or ([hb["last_fill"]] if hb.get("last_fill") else [])
    return {
        "account": account,
        "state": "stale" if age > WORKER_STALE_S else hb.get("phase", "unknown"),
        "heartbeat_age_s": round(age, 1),
        "mode": hb.get("mode"),
        "execution": hb.get("execution"),
        "trader_id": hb.get("trader_id"),
        "venue_account_id": hb.get("venue_account_id"),
        "orders_submitted": hb.get("orders_submitted"),
        "orders_filled": hb.get("orders_filled"),
        "open_positions": hb.get("open_positions"),
        "funds": (hb.get("report") or {}).get("funds"),
        "positions": (hb.get("report") or {}).get("positions") or [],
        "fills": fills,
    }


def _receipt(worker: dict, event: str, side: str | None) -> dict | None:
    """The Nautilus fill (client_order_id/trade_id) or, failing that, the open
    position in the worker's cache for this decision's instrument."""
    if not side:
        return None
    prefix = f"{event}-{side}."
    for f in reversed(worker["fills"]):
        if str(f.get("instrument", "")).startswith(prefix):
            return {"kind": "fill", **f}
    for p in worker["positions"]:
        if str(p.get("instrument", "")).startswith(prefix):
            return {"kind": "position", **p}
    return None


def _demo_scope(ctx: AuthContext):
    from algobots.demo.scope import Scope

    s = get_settings()
    principal = Principal(
        schema_version=Principal.contract_version,
        principal_id=str(ctx.user.id),
        kind=IdentityKind.USER,
        tenant_id=str(ctx.tenant_id) if ctx.tenant_id else s.demo_tenant_id,
        grants=(Grant.ACCOUNT_READ,),
    )
    return Scope.of(principal, {a.strip().lower() for a in s.demo_account_grants.split(",")})


def _decisions(state_dir: Path, scope) -> tuple[list[dict], dict[str, int], int, str | None]:
    """Sync the append-only decision log from the ledger (as /demo does), then read it."""
    from algobots.demo import decisions as D
    from algobots.demo import router as demo_router

    outcomes: dict[str, int] = {}
    settled, err = 0, None
    try:
        q = demo_router._quality(scope)
        outcomes = {x.rec["decision_id"]: x.outcome for x in q.settled}
        settled = len(q.settled)
    except Exception as exc:  # noqa: BLE001 — show the logged decisions regardless
        err = f"ledger sync unavailable: {type(exc).__name__}"
    return D.load(state_dir / D.LOG_FILE), outcomes, settled, err


@router.get("/studio/live")
def studio_live(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    s = get_settings()
    now = time.time()
    state_dir = Path(s.demo_state_dir)
    scope = _demo_scope(ctx)
    workers = {a: _worker(state_dir, a, now) for a in scope.accounts}
    recs, outcomes, settled, err = _decisions(state_dir, scope)

    decisions: list[dict] = []
    logged: dict[str, int] = {}
    for acct in scope.accounts:
        mine = [r for r in recs if r.get("strategy") == acct]
        logged[acct] = len(mine)
        for r in mine[-DECISIONS_PER_STRATEGY:]:
            ex = r.get("execution") or {}
            event = r.get("instrument_id") or ""
            receipt = (
                _receipt(workers[acct], event, r.get("side"))
                if ex.get("status") == "FILLED"
                else None
            )
            decisions.append(
                {
                    "decision_id": r.get("decision_id"),
                    "strategy": acct,
                    "provider": r.get("provider"),
                    "event": event,
                    "decided_at": r.get("decided_at"),
                    "status": r.get("status"),
                    "side": r.get("side"),
                    "p_up": r.get("p_up"),
                    "reason": r.get("reason"),
                    "execution": ex.get("status"),
                    "risk_blocked": ex.get("status") == "BLOCKED",
                    "qty": ex.get("qty"),
                    "fill_px": ex.get("fill_px"),
                    "stake": ex.get("stake"),
                    "px_source": ex.get("px_source"),
                    "outcome": outcomes.get(r.get("decision_id")),
                    "receipt": receipt,
                }
            )
    decisions.sort(key=lambda d: (d["decided_at"] or "", d["strategy"]), reverse=True)
    for w in workers.values():
        w.pop("positions")  # summarised through receipts; keep the payload small
        w["fills"] = w["fills"][-10:]
    return {
        "as_of": now,
        "environment": {
            "mode": "paper",
            "execution": "Nautilus sandbox paper venue — no live orders, no real money",
            "market_data": "live Kalshi public prices",
        },
        "viewer": {"user_id": str(ctx.user.id), "role": ctx.user.role},
        "feed": _feed_status(Path(s.demo_feed_path), now),
        "workers": list(workers.values()),
        "decisions": decisions,
        "counts": {"logged": logged, "logged_total": sum(logged.values()), "settled": settled},
        "decisions_error": err,
    }


@compat_router.get("/api/data")
@router.get("/data")
def data_feed(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    live = studio_live(ctx)
    path = Path(get_settings().demo_feed_path)
    rows = []
    try:
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(
                        {
                            k: row.get(k)
                            for k in (
                                "ts",
                                "event",
                                "market",
                                "strike",
                                "p",
                                "p_source",
                                "mkt_yes_bid",
                                "mkt_yes_ask",
                                "outcome",
                            )
                        }
                    )
            except ValueError:
                continue
    except OSError:
        pass
    return {
        "as_of": live["as_of"],
        "feed": live["feed"],
        "row_count": len(rows),
        "observations": rows[-100:][::-1],
        "counts": live["counts"],
        "error": live["decisions_error"],
    }


@compat_router.get("/api/leaderboard")
@router.get("/leaderboard")
def leaderboard(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    from algobots.demo import router as demo_router

    try:
        scope = _demo_scope(ctx)
        q = demo_router._quality(scope)
        ledger, _ = demo_router._ledger()
    except Exception as exc:
        return {"accounts": [], "error": f"Scores unavailable: {type(exc).__name__}"}
    return {
        "accounts": [asdict(score) for score in q.scores.values()],
        "equity_curves": {
            account: [
                {"ts": ts, "equity": str(equity)} for ts, equity in ledger.books[account].curve
            ]
            for account in scope.accounts
            if account in ledger.books
        },
        "equity_source": (
            "decision-ledger replay; includes sleeve refills; not worker cash balances"
        ),
        "logged": q.logged,
        "settled": len(q.settled),
        "error": None,
    }
