"""Fetch OHLCV stock data via yfinance."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf


def fetch_stock_data(
    tickers: list[str], period: str = "3mo"
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for multiple tickers.

    Args:
        tickers: List of ticker symbols (e.g. ["AAPL", "GOOGL"])
        period: Data period — 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max

    Returns:
        Dict mapping ticker → DataFrame with columns [Open, High, Low, Close, Volume]
    """
    results = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(period=period)
            if data.empty:
                print(f"WARNING: No data for {ticker}", file=sys.stderr)
                continue
            results[ticker] = data
            print(f"Fetched {ticker}: {len(data)} rows", file=sys.stderr)
        except Exception as e:
            print(f"ERROR fetching {ticker}: {e}", file=sys.stderr)
    return results


def to_json(data: dict[str, pd.DataFrame]) -> str:
    """Serialize fetched data to JSON."""
    out = {}
    for ticker, df in data.items():
        df.index = df.index.astype(str)
        out[ticker] = df.to_dict(orient="records")
    return json.dumps(out, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Fetch stock data")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "GOOGL", "TSLA"])
    parser.add_argument("--period", default="3mo")
    parser.add_argument("--output", default="data.json")
    args = parser.parse_args()

    data = fetch_stock_data(args.tickers, args.period)
    Path(args.output).write_text(to_json(data))
    print(f"Wrote {len(data)} tickers to {args.output}")


if __name__ == "__main__":
    main()
