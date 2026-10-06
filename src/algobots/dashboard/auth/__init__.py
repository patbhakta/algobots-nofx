"""Server-side dashboard views for tenant switching and membership (A03)."""

from algobots.dashboard.auth.switcher import render_tenant_switcher_html, tenant_switcher_snapshot

__all__ = ["render_tenant_switcher_html", "tenant_switcher_snapshot"]
