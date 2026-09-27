"""Server-side dashboard views for the account registry (S4.1).

`registry_snapshot` builds the broker-grouped, secret-free data model behind
the multi-account dashboard (the precondition this card delivers); the HTML
renderer turns a snapshot into an embeddable fragment with no frontend stack
dependency. No credential material ever enters a snapshot — only token-health
state.
"""

import html
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.accounts.models import AccountCredential
from algobots.api.models import Account


def registry_snapshot(db: Session, user_id: UUID) -> dict[str, Any]:
    """Broker-grouped, tenant-scoped registry view with token-health summary."""
    rows = db.execute(
        select(Account, AccountCredential)
        .outerjoin(AccountCredential, AccountCredential.account_id == Account.id)
        .where(Account.user_id == user_id)
        .order_by(Account.broker, Account.created_at)
    ).all()

    brokers: dict[str, list[dict[str, Any]]] = {}
    totals = {"accounts": 0, "paper": 0, "live": 0, "expired_tokens": 0}
    for account, credential in rows:
        entry = {
            "id": str(account.id),
            "label": account.label,
            "mode": account.mode,
            "status": account.status,
            "base_currency": account.base_currency,
            "token_status": credential.token_status if credential else None,
            "token_expires_at": _iso(credential.token_expires_at if credential else None),
            "last_refreshed_at": _iso(credential.last_refreshed_at if credential else None),
        }
        brokers.setdefault(account.broker, []).append(entry)
        totals["accounts"] += 1
        totals[account.mode if account.mode in ("paper", "live") else "paper"] += 1
        if credential is not None and credential.token_status == "expired":
            totals["expired_tokens"] += 1

    return {"brokers": brokers, "totals": totals}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def render_accounts_html(snapshot: dict[str, Any]) -> str:
    """Render a registry snapshot as an HTML fragment (dashboard embed)."""
    totals = snapshot["totals"]
    parts = [
        "<section class='accounts-registry'>",
        "<h2>Accounts</h2>",
        "<p class='accounts-totals'>"
        f"{totals['accounts']} accounts · {totals['paper']} paper · "
        f"{totals['live']} live · {totals['expired_tokens']} expired tokens</p>",
    ]
    for broker in sorted(snapshot["brokers"]):
        entries = snapshot["brokers"][broker]
        parts.append(f"<h3>{html.escape(broker)} ({len(entries)})</h3>")
        parts.append("<table class='accounts-table'>")
        parts.append("<tr><th>Label</th><th>Mode</th><th>Status</th><th>Token</th></tr>")
        for entry in entries:
            token = entry["token_status"] or "—"
            css = "token-expired" if entry["token_status"] == "expired" else ""
            parts.append(
                "<tr>"
                f"<td>{html.escape(entry['label'])}</td>"
                f"<td>{html.escape(entry['mode'])}</td>"
                f"<td>{html.escape(entry['status'])}</td>"
                f"<td class='{css}'>{html.escape(token)}</td>"
                "</tr>"
            )
        parts.append("</table>")
    parts.append("</section>")
    return "".join(parts)
