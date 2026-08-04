"""Analyze indicators and generate buy/sell/hold signals."""

import argparse
import json
import sys
from pathlib import Path


def analyze_stock(ticker: str, indicators: dict) -> dict:
    """Generate trading signals from technical indicators.

    Returns:
        {
            "ticker": str,
            "price": float,
            "signals": {indicator_name: signal_str},
            "recommendation": "BUY" | "SELL" | "HOLD",
            "confidence": float (0-1),
            "reasons": [str, ...],
        }
    """
    signals = {}
    reasons = []
    buy_score = 0
    sell_score = 0

    price = indicators["price"]

    # RSI analysis
    rsi = indicators.get("rsi")
    if rsi is not None:
        if rsi < 30:
            signals["RSI"] = f"{rsi:.0f} (Oversold)"
            buy_score += 2
            reasons.append(f"RSI at {rsi:.0f} — oversold territory, potential bounce")
        elif rsi > 70:
            signals["RSI"] = f"{rsi:.0f} (Overbought)"
            sell_score += 2
            reasons.append(f"RSI at {rsi:.0f} — overbought, correction likely")
        else:
            signals["RSI"] = f"{rsi:.0f} (Neutral)"

    # MACD analysis
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            signals["MACD"] = "Bullish"
            buy_score += 1
            reasons.append("MACD above signal line — bullish momentum")
        else:
            signals["MACD"] = "Bearish"
            sell_score += 1
            reasons.append("MACD below signal line — bearish momentum")

    # Bollinger analysis
    lower = indicators.get("bollinger_lower")
    upper = indicators.get("bollinger_upper")
    if lower is not None and upper is not None:
        if price <= lower * 1.02:
            signals["Bollinger"] = "Lower Band"
            buy_score += 2
            reasons.append("Price near lower Bollinger band — mean reversion likely")
        elif price >= upper * 0.98:
            signals["Bollinger"] = "Upper Band"
            sell_score += 2
            reasons.append("Price near upper Bollinger band — overextended")
        else:
            signals["Bollinger"] = "Middle Range"

    # SMA/EMA trend
    sma = indicators.get("sma_20")
    ema = indicators.get("ema_20")
    if sma is not None:
        if price > sma:
            signals["SMA-20"] = "Above (Uptrend)"
            buy_score += 1
        else:
            signals["SMA-20"] = "Below (Downtrend)"
            sell_score += 1

    # Volume analysis
    volume = indicators.get("volume")
    vol_sma = indicators.get("volume_sma")
    if volume is not None and vol_sma is not None and vol_sma > 0:
        vol_ratio = volume / vol_sma
        if vol_ratio > 1.5:
            signals["Volume"] = f"{vol_ratio:.1f}x avg (High)"
            reasons.append(f"Volume {vol_ratio:.1f}x above average — strong interest")
        elif vol_ratio < 0.5:
            signals["Volume"] = f"{vol_ratio:.1f}x avg (Low)"
        else:
            signals["Volume"] = f"{vol_ratio:.1f}x avg (Normal)"

    # Final recommendation
    total = buy_score + sell_score
    if total == 0:
        recommendation = "HOLD"
        confidence = 0.33
    elif buy_score > sell_score:
        recommendation = "BUY"
        confidence = buy_score / (total + 1)
    elif sell_score > buy_score:
        recommendation = "SELL"
        confidence = sell_score / (total + 1)
    else:
        recommendation = "HOLD"
        confidence = 0.50

    return {
        "ticker": ticker,
        "price": price,
        "signals": signals,
        "recommendation": recommendation,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "indicators": {k: v for k, v in indicators.items() if k not in ("price",)},
    }


def analyze_all(indicators_data: dict) -> list[dict]:
    """Analyze all tickers."""
    results = []
    for ticker, indicators in indicators_data.items():
        analysis = analyze_stock(ticker, indicators)
        results.append(analysis)
        print(f"Analyzed {ticker}: {analysis['recommendation']}", file=sys.stderr)
    return results


def main():
    parser = argparse.ArgumentParser(description="Analyze indicators")
    parser.add_argument("--input", default="indicators.json")
    parser.add_argument("--output", default="analysis.json")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    results = analyze_all(data)
    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"Wrote analysis for {len(results)} tickers to {args.output}")


if __name__ == "__main__":
    main()
