"""A08 risk routes: account controls + risk preview (ALG-3104).

- ``GET/PUT /api/accounts/{account_id}/controls`` — the operator's live view
  and lever: entry pause, cancel-entries, reduce-only, and a SEPARATELY
  authorized flatten (its own actor + expiry window, never implied).
- ``POST /api/risk/preview`` — evaluate a hypothetical proposal against a
  policy WITHOUT reserving anything: same deterministic engine, no funds
  move, no intent is committed.

The account id here is the ledger-scoped account string (the A07/A08 domain
convention), scoped to the authenticated user as tenant. Another tenant's
rows are indistinguishable from missing rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from algobots.api.database import get_db
from algobots.api.dependencies import get_current_user
from algobots.api.models import User
from algobots.contracts.risk import RiskDecision, RiskPolicyVersion
from algobots.execution.admission import get_controls, set_controls
from algobots.risk.controls import AccountControls
from algobots.risk.policy import (
    AccountRiskState,
    InstrumentMark,
    RiskProposal,
    evaluate_proposal,
)

router = APIRouter(prefix="/api", tags=["risk"])


class ControlsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    entries_paused: bool
    cancel_entries_requested: bool
    reduce_only: bool
    flatten_authorized: bool
    flatten_authorized_by: str | None
    flatten_valid_until: datetime | None


class ControlsSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries_paused: bool = False
    cancel_entries_requested: bool = False
    reduce_only: bool = False
    #: Flatten authorization is DELIBERATELY not settable through this bulk
    #: shape: use ``POST .../controls/flatten`` with an explicit grant.
    flatten_minutes: int = Field(default=0, ge=0, le=1440)


class FlattenGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorized_by: str = Field(min_length=1, max_length=128)
    minutes: int = Field(gt=0, le=1440)


def _controls_out(account_id: str, controls: AccountControls) -> ControlsOut:
    return ControlsOut(
        account_id=account_id,
        entries_paused=controls.entries_paused,
        cancel_entries_requested=controls.cancel_entries_requested,
        reduce_only=controls.reduce_only,
        flatten_authorized=controls.flatten_authorized(),
        flatten_authorized_by=controls.flatten_authorized_by,
        flatten_valid_until=controls.flatten_valid_until,
    )


@router.get("/accounts/{account_id}/controls", response_model=ControlsOut)
def read_controls(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ControlsOut:
    """Live control state for one account (protection visibility, AC5)."""
    return _controls_out(account_id, get_controls(db, current_user.id, account_id))


@router.put("/accounts/{account_id}/controls", response_model=ControlsOut)
def write_controls(
    account_id: str,
    payload: ControlsSet,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ControlsOut:
    """Set operator controls. Pausing entries never removes stops."""
    existing = get_controls(db, current_user.id, account_id)
    controls = AccountControls(
        entries_paused=payload.entries_paused,
        cancel_entries_requested=payload.cancel_entries_requested,
        reduce_only=payload.reduce_only,
        # a flatten grant survives bulk control writes; expire via /flatten/cancel
        flatten_authorized_by=existing.flatten_authorized_by,
        flatten_authorized_at=existing.flatten_authorized_at,
        flatten_valid_until=existing.flatten_valid_until,
    )
    result = set_controls(db, current_user.id, account_id, controls)
    db.commit()
    response.headers["X-Audit-Resource"] = "account_controls"
    response.headers["X-Audit-Resource-Id"] = account_id
    return _controls_out(account_id, result)


@router.post("/accounts/{account_id}/controls/flatten", response_model=ControlsOut)
def authorize_flatten(
    account_id: str,
    payload: FlattenGrant,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ControlsOut:
    """Separately authorize a flatten window (actor + bounded expiry)."""
    now = datetime.now(UTC)
    existing = get_controls(db, current_user.id, account_id)
    controls = existing.model_copy(
        update={
            "flatten_authorized_by": payload.authorized_by,
            "flatten_authorized_at": now,
            "flatten_valid_until": now + timedelta(minutes=payload.minutes),
        }
    )
    result = set_controls(db, current_user.id, account_id, controls)
    db.commit()
    return _controls_out(account_id, result)


@router.post("/accounts/{account_id}/controls/flatten/cancel", response_model=ControlsOut)
def cancel_flatten_authorization(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ControlsOut:
    existing = get_controls(db, current_user.id, account_id)
    controls = existing.model_copy(
        update={
            "flatten_authorized_by": None,
            "flatten_authorized_at": None,
            "flatten_valid_until": None,
        }
    )
    result = set_controls(db, current_user.id, account_id, controls)
    db.commit()
    return _controls_out(account_id, result)


class PreviewMark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    price: Decimal = Field(gt=0)
    quality: str
    observed_at: datetime


class PreviewState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cash_available: Decimal
    cash_reserved: Decimal = Decimal(0)
    gross_exposure: Decimal = Decimal(0)
    equity_reference: Decimal = Field(gt=0)
    instrument_exposure: Decimal = Decimal(0)
    instrument_position: Decimal = Decimal(0)
    deployment_gross_notional: Decimal = Decimal(0)
    daily_pnl: Decimal = Decimal(0)
    connected: bool = True
    reconciled_within_seconds: int | None = None
    instrument_mark: PreviewMark | None = None


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: RiskPolicyVersion
    proposal: dict = Field(min_length=1)
    state: PreviewState
    #: Evaluation instant for the stale-state rules. Optional in production
    #: (wall clock); deterministic replays pass it explicitly.
    evaluated_at: datetime | None = None


class PreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: RiskDecision


@router.post("/risk/preview", response_model=PreviewOut)
def risk_preview(
    payload: PreviewRequest,
    current_user: User = Depends(get_current_user),
) -> PreviewOut:
    """Deterministic policy evaluation with NO reservation and NO intent:
    the same :func:`evaluate_proposal` the admission path runs, over an
    operator-supplied snapshot. Fail-closed on malformed input (422/400)."""
    proposal = RiskProposal.model_validate(payload.proposal)
    mark = None
    if payload.state.instrument_mark is not None:
        m = payload.state.instrument_mark
        mark = InstrumentMark(
            instrument_id=m.instrument_id,
            price=m.price,
            quality=m.quality,
            observed_at=m.observed_at,
        )
    state = AccountRiskState(
        cash_available=payload.state.cash_available,
        cash_reserved=payload.state.cash_reserved,
        gross_exposure=payload.state.gross_exposure,
        equity_reference=payload.state.equity_reference,
        instrument_exposure=payload.state.instrument_exposure,
        instrument_position=payload.state.instrument_position,
        instrument_mark=mark,
        deployment_gross_notional=payload.state.deployment_gross_notional,
        daily_pnl=payload.state.daily_pnl,
        connected=payload.state.connected,
        reconciled_within_seconds=payload.state.reconciled_within_seconds,
    )
    decision = evaluate_proposal(payload.policy, proposal, state, now=payload.evaluated_at)
    return PreviewOut(decision=decision)
