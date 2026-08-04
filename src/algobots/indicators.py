"""Technical indicators — RSI, MACD, Bollinger Bands, SMA, EMA.

All calculations implemented manually with numpy/pandas for full control and testability.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index — momentum oscillator (0-100).

    RSI < 30 = oversold, RSI > 70 = overbought.
    """
    delta = prices.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    avg_gain = gains.rolling(window=period, min_periods=period).mean()
    avg_loss = losses.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Moving Average Convergence Divergence — trend indicator.

    Returns (MACD line, Signal line, Histogram).
    Bullish when MACD > Signal, bearish when MACD < Signal.
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger(
    prices: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands — volatility indicator.

    Returns (Upper band, Middle band/SMA, Lower band).
    Price near lower band = potentially oversold.
    Price near upper band = potentially overbought.
    """
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average."""
    return prices.rolling(window=period).mean()


def calculate_ema(prices: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return prices.ewm(span=period, adjust=False).mean()


def calculate_volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume Simple Moving Average — for volume analysis."""
    return volume.rolling(window=period).mean()


def calculate_all(data: dict) -> dict:
    """Calculate all indicators for all tickers.

    Args:
        data: Dict from fetcher — {ticker: [{Open, High, Low, Close, Volume}, ...]}

    Returns:
        Dict with indicators added per ticker.
    """
    results = {}
    for ticker, records in data.items():
        df = pd.DataFrame(records)
        if "Close" not in df.columns or df.empty:
            continue

        close = df["Close"]
        volume = df.get("Volume", pd.Series(dtype=float))

        macd_line, signal_line, macd_hist = calculate_macd(close)
        upper, middle, lower = calculate_bollinger(close)

        results[ticker] = {
            "price": float(close.iloc[-1]),
            "rsi": float(calculate_rsi(close).iloc[-1]),
            "macd": float(macd_line.iloc[-1]),
            "macd_signal": float(signal_line.iloc[-1]),
            "macd_histogram": float(macd_hist.iloc[-1]),
            "bollinger_upper": float(upper.iloc[-1]),
            "bollinger_middle": float(middle.iloc[-1]),
            "bollinger_lower": float(lower.iloc[-1]),
            "sma_20": float(calculate_sma(close).iloc[-1]),
            "ema_20": float(calculate_ema(close).iloc[-1]),
            "volume": float(volume.iloc[-1]) if not volume.empty else None,
            "volume_sma": float(calculate_volume_sma(volume).iloc[-1]) if not volume.empty else None,
        }
        print(f"Calculated indicators for {ticker}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(description="Calculate technical indicators")
    parser.add_argument("--input", default="data.json")
    parser.add_argument("--output", default="indicators.json")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    results = calculate_all(data)
    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"Wrote indicators for {len(results)} tickers to {args.output}")


if __name__ == "__main__":
    main()
