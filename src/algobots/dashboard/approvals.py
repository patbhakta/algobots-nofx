"""Server-side dashboard views for the approval queue (S4.3).

`approval_inbox_snapshot` builds the data model behind the dashboard
approval inbox: the parked queue (with park reason and current wait), the
recent verdicts (with decision reason and persisted park -> decision
latency), and the action-ledger tail. `render_approvals_html` turns a
snapshot into an embeddable fragment with no frontend stack dependency,
following the `dashboard/accounts.py` pattern. Secret-free by construction.
"""

import html
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.approvals.models import ActionLedger, ApprovalRequest
from algobots.api.approvals.service import aware_utc
from algobots.api.models import Account, Order

_PARKED = "parked"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age_ms(parked_at: datetime, now: datetime) -> int:
    return max(0, round((aware_utc(now) - aware_utc(parked_at)).total_seconds() * 1000))


def approval_inbox_snapshot(
    db: Session, user_id: UUID, *, now: datetime | None = None, ledger_limit: int = 20
) -> dict[str, Any]:
    """Tenant-scoped approval inbox: parked queue + verdicts + ledger tail.

    Parked entries carry the park reason and current wait (age); decided
    entries carry the verdict, decision reason, and the persisted
    park -> decision `latency_ms`. Quantities of interest are summarized in
    `totals`.
    """
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(ApprovalRequest, Order, Account)
        .outerjoin(Order, Order.id == ApprovalRequest.order_id)
        .outerjoin(Account, Account.id == ApprovalRequest.account_id)
        .where(ApprovalRequest.user_id == user_id)
        .order_by(ApprovalRequest.parked_at.desc())
    ).all()

    parked: list[dict[str, Any]] = []
    decided: list[dict[str, Any]] = []
    totals = {"requests": 0, "parked": 0, "approved": 0, "rejected": 0, "expired": 0}
    for request, order, account in rows:
        entry = {
            "id": str(request.id),
            "order_id": str(request.order_id),
            "account_label": account.label if account else None,
            "symbol": request.symbol,
            "side": request.side,
            "qty": request.qty,
            "status": request.status,
            "park_reason": request.park_reason,
            "decision_reason": request.decision_reason,
            "latency_ms": request.latency_ms,
            "age_ms": _age_ms(request.parked_at, now) if request.status == _PARKED else None,
            "expires_at": _iso(request.expires_at),
            "decided_at": _iso(request.decided_at),
            "order_status": order.status if order else None,
        }
        totals["requests"] += 1
        if request.status in totals:
            totals[request.status] += 1
        (parked if request.status == _PARKED else decided).append(entry)

    ledger_rows = list(
        db.scalars(
            select(ActionLedger)
            .where(ActionLedger.user_id == user_id)
            .order_by(ActionLedger.created_at.desc(), ActionLedger.id.desc())
            .limit(ledger_limit)
        )
    )
    ledger = [
        {
            "action": row.action,
            "reason": row.reason,
            "latency_ms": row.latency_ms,
            "created_at": _iso(row.created_at),
        }
        for row in ledger_rows
    ]
    return {"parked": parked, "decided": decided, "totals": totals, "ledger": ledger}


def _fmt_latency(latency_ms: int | None) -> str:
    return "—" if latency_ms is None else f"{latency_ms} ms"


def render_approvals_html(snapshot: dict[str, Any]) -> str:
    """Render an approval inbox snapshot as an HTML fragment (dashboard embed)."""
    totals = snapshot["totals"]
    parts = [
        "<section class='approvals-inbox'>",
        "<h2>Approval Inbox</h2>",
        "<p class='approvals-totals'>"
        f"{totals['parked']} parked · {totals['approved']} approved · "
        f"{totals['rejected']} rejected · {totals['expired']} expired</p>",
        "<table class='approvals-table'>",
        "<tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Account</th>"
        "<th>Status</th><th>Reason</th><th>Latency</th></tr>",
    ]
    for entry in [*snapshot["parked"], *snapshot["decided"]]:
        reason = entry["park_reason"] if entry["status"] == _PARKED else entry["decision_reason"]
        latency = entry["age_ms"] if entry["status"] == _PARKED else entry["latency_ms"]
        css = "approval-parked" if entry["status"] == _PARKED else f"approval-{entry['status']}"
        parts.append(
            "<tr>"
            f"<td>{html.escape(entry['symbol'])}</td>"
            f"<td>{html.escape(entry['side'])}</td>"
            f"<td>{entry['qty']}</td>"
            f"<td>{html.escape(entry['account_label'] or '—')}</td>"
            f"<td class='{css}'>{html.escape(entry['status'])}</td>"
            f"<td>{html.escape(reason)}</td>"
            f"<td>{_fmt_latency(latency)}</td>"
            "</tr>"
        )
    parts.append("</table>")
    parts.append("<h3>Action Ledger (latest)</h3>")
    parts.append("<table class='ledger-table'>")
    parts.append("<tr><th>Action</th><th>Reason</th><th>Latency</th></tr>")
    for row in snapshot["ledger"]:
        parts.append(
            "<tr>"
            f"<td>{html.escape(row['action'])}</td>"
            f"<td>{html.escape(row['reason'])}</td>"
            f"<td>{_fmt_latency(row['latency_ms'])}</td>"
            "</tr>"
        )
    parts.append("</table>")
    parts.append("</section>")
    return "".join(parts)
