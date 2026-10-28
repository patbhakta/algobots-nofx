import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("# OpenBB QQQ historical prices\nFetch real yfinance daily bars, normalize UTC OHLCV, write and read back the Nautilus Parquet catalog on FunnyTree.")
    return


@app.cell
def _(mo):
    query_form = mo.ui.dictionary({
        "symbol": mo.ui.dropdown(options=["SPY", "QQQ", "AAPL"], value="QQQ", label="Ticker"),
        "start": mo.ui.date(value="2026-09-01", label="Start date"),
        "end": mo.ui.date(value="2026-09-15", label="End date"),
    }).form(submit_button_label="Fetch history and write catalog")
    query_form
    return (query_form,)


@app.cell
def _(mo, query_form):
    mo.stop(query_form.value is None, mo.md("Submit the form to fetch historical data. No provider calls occur before submission."))
    from datetime import datetime, timezone
    from pathlib import Path
    import hashlib
    import json
    import pandas as pd
    from openbb import obb
    from nautilus_trader.model import Bar, BarType, Currency, Equity, InstrumentId, Price, Quantity, Symbol
    from nautilus_trader.persistence import ParquetDataCatalog

    _q = query_form.value
    _symbol = _q["symbol"].strip().upper()
    if not _symbol or not all(c.isalnum() or c in ".-^=" for c in _symbol):
        raise ValueError("Use a valid ticker")
    if _q["start"] >= _q["end"]:
        raise ValueError("Start must precede end")
    _venue = {"SPY": "ARCA", "QQQ": "NASDAQ", "AAPL": "NASDAQ"}[_symbol]
    _query = dict(symbol=_symbol, start_date=str(_q["start"]), end_date=str(_q["end"]), provider="yfinance")
    history = obb.equity.price.historical(**_query).to_df().reset_index()
    history["date"] = pd.to_datetime(history["date"], utc=True)
    history = history.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if history.empty or history[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError("Provider returned empty or incomplete OHLCV")
    _identity = hashlib.sha256(history.to_json(date_format="iso").encode()).hexdigest()[:16]
    catalog_path = Path("/app/data/nautilus") / ("studio-" + _symbol + "-" + _venue + "-" + _identity)
    catalog_path.mkdir(parents=True, exist_ok=True)
    _instrument = Equity(
        instrument_id=InstrumentId.from_str(_symbol + "." + _venue), raw_symbol=Symbol(_symbol),
        currency=Currency.from_str("USD"), price_precision=2,
        price_increment=Price.from_str("0.01"), lot_size=Quantity.from_int(1), ts_event=0, ts_init=0,
    )
    _bar_type = BarType.from_str(_symbol + "." + _venue + "-1-DAY-LAST-EXTERNAL")
    _bars = []
    for _row in history.itertuples():
        # Daily bars become available at the end of the labeled UTC day.
        _ns = int(_row.date.value) + 86_400_000_000_000
        _bars.append(Bar(_bar_type, *[Price.from_str(f"{getattr(_row, _k):.2f}") for _k in ("open", "high", "low", "close")], Quantity.from_int(int(_row.volume)), ts_event=_ns, ts_init=_ns))
    _catalog = ParquetDataCatalog(str(catalog_path))
    if not (catalog_path / "provenance.json").exists():
        _catalog.write_instruments([_instrument])
        _catalog.write_bars(_bars)
    _replayed = list(_catalog.query_bars())
    assert len(_replayed) == len(_bars), "Nautilus catalog read-back mismatch"
    _provenance = dict(query=_query, retrieved_at=datetime.now(timezone.utc).isoformat(), rows=len(history), catalog_bars=len(_replayed), catalog=str(catalog_path), content_hash=_identity)
    (catalog_path / "provenance.json").write_text(json.dumps(_provenance, indent=2))
    mo.md(f"**{len(history)} real bars** fetched and read back from `{catalog_path}`.")
    return catalog_path, history


@app.cell
def _(history, mo, query_form):
    import matplotlib.pyplot as plt
    _fig, _ax = plt.subplots(figsize=(10, 4))
    _ax.plot(history["date"], history["close"], marker="o")
    _ax.set(title=f"{query_form.value['symbol']} — OpenBB / yfinance daily close", xlabel="UTC date", ylabel="USD")
    _ax.grid(alpha=0.25)
    _fig.autofmt_xdate()
    mo.as_html(_fig)
    return


@app.cell
def _(history, mo):
    mo.ui.table(history, page_size=10)
    return


if __name__ == "__main__":
    app.run()
