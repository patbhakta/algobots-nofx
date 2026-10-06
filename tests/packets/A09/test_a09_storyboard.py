"""A09 acceptance cases 1 and 3: clickable static storyboard, DEMO DATA on every
financial panel, account + environment on every action, accessible statuses."""

from html.parser import HTMLParser
from pathlib import Path

import pytest

from algobots.dashboard.design import components as c
from algobots.dashboard.design.storyboard import SCREENS, pages
from algobots.dashboard.fixtures import STATES, fixture

ROOT = Path(__file__).resolve().parents[3]
BUILT = ROOT / "artifacts" / "A09" / "storyboard"
PAGES = pages()
CONTENT_PAGES = [n for n in PAGES if n != "index.html"]
VOID = {"meta", "input", "br", "img", "hr", "link", "line", "rect"}


class Page(HTMLParser):
    """Collects elements with their ancestor stack and visible text."""

    def __init__(self, html: str):
        super().__init__()
        self.stack: list[tuple[str, dict]] = []
        self.elements: list[dict] = []
        self.open: list[dict] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        el = {"tag": tag, "attrs": dict(attrs), "text": "", "ancestors": list(self.stack)}
        self.elements.append(el)
        if tag not in VOID:
            self.stack.append((tag, dict(attrs)))
            self.open.append(el)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack:
            self.stack.pop()
            el = self.open.pop()
            if el["tag"] == tag:
                break

    def handle_data(self, data):
        for el in self.open:
            el["text"] += data

    def find(self, pred):
        return [e for e in self.elements if pred(e)]


def _cls(el) -> set[str]:
    return set((el["attrs"].get("class") or "").split())


@pytest.fixture(scope="module")
def parsed():
    return {name: Page(html) for name, html in PAGES.items()}


def test_storyboard_covers_four_screens_by_five_states():
    assert set(SCREENS) == {"overview", "workspace", "studio", "invite"}
    assert sorted(CONTENT_PAGES) == sorted(f"{s}-{st}.html" for s in SCREENS for st in STATES)


def test_build_is_deterministic_and_committed_copy_is_current():
    assert pages() == PAGES
    for name, html in PAGES.items():
        assert (BUILT / name).read_text(encoding="utf-8") == html, f"{name} stale; rebuild"


def test_static_no_live_service(parsed):
    for name, html in PAGES.items():
        assert "http://" not in html and "https://" not in html, name
        assert "fetch(" not in html and "XMLHttpRequest" not in html and "WebSocket" not in html
        p = parsed[name]
        assert not p.find(lambda e: e["tag"] in ("link", "img", "iframe")), name
        assert not p.find(lambda e: e["tag"] == "script" and "src" in e["attrs"]), name


def test_every_link_is_clickable_to_an_existing_page(parsed):
    for name, p in parsed.items():
        hrefs = [e["attrs"]["href"] for e in p.find(lambda e: e["tag"] == "a")]
        assert hrefs, name
        for href in hrefs:
            assert href in PAGES, f"{name}: broken link {href}"
    reachable, frontier = set(), ["index.html"]
    while frontier:
        n = frontier.pop()
        if n not in reachable:
            reachable.add(n)
            frontier += [e["attrs"]["href"] for e in parsed[n].find(lambda e: e["tag"] == "a")]
    assert reachable == set(PAGES)


@pytest.mark.parametrize("name", CONTENT_PAGES)
def test_demo_banner_and_tags(name, parsed):
    p = parsed[name]
    (banner,) = p.find(lambda e: "demo-banner" in _cls(e))
    assert "DEMO DATA" in banner["text"]
    assert "DEMO DATA" in p.find(lambda e: e["tag"] == "title")[0]["text"]
    for panel in p.find(
        lambda e: (
            e["tag"] == "section"
            and e["attrs"].get("data-financial") == "true"
            and "panel" in _cls(e)
        )
    ):
        assert "DEMO DATA" in panel["text"], f"{name}: financial panel without DEMO DATA tag"
    for value in p.find(lambda e: "data-fin" in e["attrs"]):
        enclosing = [a for t, a in value["ancestors"] if t == "section"]
        assert enclosing and enclosing[-1].get("data-financial") == "true", (
            f"{name}: financial value outside a DEMO DATA-marked section"
        )


@pytest.mark.parametrize("name", CONTENT_PAGES)
def test_every_action_shows_account_and_environment(name, parsed):
    f = fixture(name.split("-")[1].removesuffix(".html"))
    labels = {a["id"]: a for a in f["accounts"]}
    actions = parsed[name].find(lambda e: e["tag"] == "button" and "action" in _cls(e))
    assert actions, f"{name} has no actions"
    for el in actions:
        a = el["attrs"]
        acct = labels[a["data-account"]]
        assert a["data-environment"] == acct["environment"]
        assert acct["label"] in el["text"] and a["data-environment"] in el["text"], el["text"]
        assert acct["label"] in a["aria-label"] and a["data-environment"] in a["aria-label"]
        if acct["environment"] == "LIVE":
            assert "disabled" in a and "not authorized" in el["text"]
    assert not parsed[name].find(
        lambda e: (
            e["tag"] == "button"
            and not ({"action"} & _cls(e))
            and e["attrs"].get("data-toggle") is None
        )
    )


def test_action_component_refuses_missing_context():
    acct = {"id": "demo-acct-001", "label": "A (demo)", "environment": "PAPER"}
    with pytest.raises(ValueError, match="account context"):
        c.action("Buy", account=None, environment="PAPER")
    with pytest.raises(ValueError, match="environment"):
        c.action("Buy", account=acct, environment=None)
    with pytest.raises(ValueError, match="environment LIVE != account PAPER"):
        c.action("Buy", account=acct, environment="LIVE")


@pytest.mark.parametrize("name", CONTENT_PAGES)
def test_header_shows_account_mode_and_freshness(name, parsed):
    p = parsed[name]
    (header,) = p.find(lambda e: "app-header" in _cls(e))
    assert any(t == "div" and "chrome" in (a.get("class") or "") for t, a in header["ancestors"])
    assert p.find(
        lambda e: (
            "badge" in _cls(e)
            and any("app-header" in (a.get("class") or "") for _, a in e["ancestors"])
        )
    )
    assert "data " in header["text"] and "reconciliation" in header["text"]


def test_paused_actions_say_why_and_stop_access_stays_open(parsed):
    stale = parsed["overview-stale.html"]
    approve = stale.find(lambda e: e["attrs"].get("data-action", "").startswith("Approve"))[0]
    assert "disabled" in approve["attrs"] and "market data 7m 11s old" in approve["text"]
    pause = stale.find(lambda e: e["attrs"].get("data-action") == "Pause all strategies")[0]
    assert "disabled" not in pause["attrs"]
    ws = parsed["workspace-unknown.html"]
    cancel = ws.find(lambda e: e["attrs"].get("data-action", "").startswith("Request cancel"))[0]
    assert "disabled" not in cancel["attrs"]


@pytest.mark.parametrize("name", CONTENT_PAGES)
def test_statuses_are_color_independent(name, parsed):
    for el in parsed[name].find(lambda e: "status" in _cls(e) and e["tag"] == "span"):
        assert el["attrs"].get("aria-label"), el
        assert el["text"].strip() and len(el["text"].strip()) > 1, "glyph plus a text label"


def test_unknown_values_render_unavailable_not_zero(parsed):
    p = parsed["overview-unknown.html"]
    metrics = [m["text"] for m in p.find(lambda e: "metric" in _cls(e))]
    for label in ("Equity", "Net P&L", "Drawdown"):
        (text,) = [t for t in metrics if t.startswith(label)]
        assert "Unavailable" in text and "0.00" not in text, text
    ws = parsed["workspace-empty.html"]
    assert "no closed trades in period" in "".join(
        m["text"] for m in ws.find(lambda e: "metric" in _cls(e))
    )
    for html in PAGES.values():
        assert "Infinity" not in html and "NaN" not in html and "∞" not in html


def test_signed_values_are_readable_without_color():
    loss = c.money({"amount": "-7340.61", "currency": "USD"}, signed=True)
    assert "−7,340.61" in loss and "loss" in loss
    gain = c.money({"amount": "4210.55", "currency": "USD"}, signed=True)
    assert "+4,210.55" in gain and "gain" in gain
    assert c.pct("-2.10", signed=True).count("−2.10%") == 1


@pytest.mark.parametrize("name", CONTENT_PAGES)
def test_basic_accessibility(name, parsed):
    p = parsed[name]
    assert p.find(lambda e: e["tag"] == "html")[0]["attrs"]["lang"] == "en"
    assert len(p.find(lambda e: e["tag"] == "h1")) == 1
    ids = {e["attrs"].get("id") for e in p.elements}
    for inp in p.find(lambda e: e["tag"] == "input"):
        assert p.find(
            lambda e, i=inp: e["tag"] == "label" and e["attrs"].get("for") == i["attrs"]["id"]
        )
        if inp["attrs"].get("aria-invalid") == "true":
            assert inp["attrs"]["aria-describedby"] in ids
    for el in p.find(lambda e: e["attrs"].get("role") == "img"):
        assert el["attrs"].get("aria-label"), name
    for el in p.find(lambda e: e["tag"] == "nav"):
        assert el["attrs"].get("aria-label")


def test_component_inventory_is_published():
    names = {n for n, _ in c.INVENTORY}
    assert {"action", "status", "money", "metric", "panel", "demo_banner", "settings"} <= names
    for n in names - {"demo_banner", "app_header", "trace", "table"}:
        assert hasattr(c, n), n
