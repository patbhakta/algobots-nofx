"""AlgoBots dashboard views (server-rendered, secret-free)."""

from algobots.dashboard.accounts import registry_snapshot, render_accounts_html

__all__ = ["registry_snapshot", "render_accounts_html"]
