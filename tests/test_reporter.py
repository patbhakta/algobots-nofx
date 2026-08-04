"""Tests for report generator."""

import pytest

from algobots.reporter import generate_report


@pytest.fixture
def sample_analyses():
    return [
        {
            "ticker": "AAPL",
            "price": 195.50,
            "signals": {"RSI": "32 (Oversold)", "MACD": "Bullish", "Bollinger": "Lower Band"},
            "recommendation": "BUY",
            "confidence": 0.75,
            "reasons": ["RSI oversold", "MACD bullish cross"],
            "indicators": {"rsi": 32.0, "macd": 1.5},
        },
        {
            "ticker": "TSLA",
            "price": 245.80,
            "signals": {"RSI": "75 (Overbought)", "MACD": "Bearish", "Bollinger": "Upper Band"},
            "recommendation": "SELL",
            "confidence": 0.70,
            "reasons": ["RSI overbought"],
            "indicators": {"rsi": 75.0, "macd": -2.0},
        },
    ]


class TestGenerateReport:
    def test_returns_string(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert isinstance(report, str)

    def test_has_title(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert "# Stock Technical Analysis Report" in report

    def test_has_summary_table(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert "## Summary" in report
        assert "|" in report  # Table format

    def test_has_tickers(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert "AAPL" in report
        assert "TSLA" in report

    def test_has_detailed_analysis(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert "## Detailed Analysis" in report
        assert "### AAPL" in report

    def test_has_disclaimer(self, sample_analyses):
        report = generate_report(sample_analyses)
        assert "## Disclaimer" in report
        assert "NOT financial advice" in report

    def test_empty_list(self):
        report = generate_report([])
        assert "# Stock Technical Analysis Report" in report
