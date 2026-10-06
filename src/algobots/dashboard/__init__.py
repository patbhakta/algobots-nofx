"""AlgoBots dashboard views (server-rendered, secret-free)."""

from algobots.dashboard.accounts import registry_snapshot, render_accounts_html
from algobots.dashboard.approvals import approval_inbox_snapshot, render_approvals_html

__all__ = [
    "approval_inbox_snapshot",
    "registry_snapshot",
    "render_accounts_html",
    "render_approvals_html",
]
