"""Tests for stock analyzer."""

import pytest

from algobots.analyzer import analyze_stock, analyze_all


@pytest.fixture
def sample_indicators():
    return {
        "AAPL": {
            "price": 150.0,
            "rsi": 25.0,
            "macd": 2.5,
            "macd_signal": 1.0,
            "macd_histogram": 1.5,
            "bollinger_upper": 160.0,
            "bollinger_middle": 145.0,
            "bollinger_lower": 130.0,
            "sma_20": 140.0,
            "ema_20": 142.0,
            "volume": 5000000,
            "volume_sma": 3000000,
        },
        "TSLA": {
            "price": 280.0,
            "rsi": 75.0,
            "macd": -3.0,
            "macd_signal": -1.0,
            "macd_histogram": -2.0,
            "bollinger_upper": 285.0,
            "bollinger_middle": 250.0,
            "bollinger_lower": 215.0,
            "sma_20": 260.0,
            "ema_20": 265.0,
            "volume": 8000000,
            "volume_sma": 4000000,
        },
    }


class TestAnalyzeStock:
    def test_returns_dict(self, sample_indicators):
        result = analyze_stock("AAPL", sample_indicators["AAPL"])
        assert isinstance(result, dict)

    def test_has_required_fields(self, sample_indicators):
        result = analyze_stock("AAPL", sample_indicators["AAPL"])
        assert "ticker" in result
        assert "price" in result
        assert "signals" in result
        assert "recommendation" in result
        assert "confidence" in result
        assert "reasons" in result

    def test_oversold_buy_signal(self, sample_indicators):
        result = analyze_stock("AAPL", sample_indicators["AAPL"])
        assert result["recommendation"] == "BUY"
        assert result["confidence"] > 0.5

    def test_overbought_sell_signal(self, sample_indicators):
        result = analyze_stock("TSLA", sample_indicators["TSLA"])
        assert result["recommendation"] == "SELL"
        assert result["confidence"] > 0.5

    def test_confidence_range(self, sample_indicators):
        result = analyze_stock("AAPL", sample_indicators["AAPL"])
        assert 0.0 <= result["confidence"] <= 1.0


class TestAnalyzeAll:
    def test_analyze_multiple(self, sample_indicators):
        results = analyze_all(sample_indicators)
        assert len(results) == 2
        assert results[0]["ticker"] == "AAPL"
        assert results[1]["ticker"] == "TSLA"
