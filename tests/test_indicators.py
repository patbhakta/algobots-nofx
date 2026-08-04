"""Tests for technical indicators."""

import numpy as np
import pandas as pd
import pytest

from algobots.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger,
    calculate_sma,
    calculate_ema,
    calculate_volume_sma,
)


@pytest.fixture
def sample_prices():
    """Generate sample price data for testing."""
    np.random.seed(42)
    n = 60
    base = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.Series(base, name="Close")


@pytest.fixture
def sample_volume():
    """Generate sample volume data."""
    np.random.seed(42)
    return pd.Series(np.random.randint(500000, 5000000, 60), dtype=float)


class TestRSI:
    def test_rsi_returns_series(self, sample_prices):
        rsi = calculate_rsi(sample_prices)
        assert isinstance(rsi, pd.Series)

    def test_rsi_range(self, sample_prices):
        rsi = calculate_rsi(sample_prices)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_period(self, sample_prices):
        rsi = calculate_rsi(sample_prices, period=14)
        # First ~14 values should be NaN (warmup period: diff() loses 1, rolling loses 14)
        assert rsi.iloc[:13].isna().all()


class TestMACD:
    def test_macd_returns_three_series(self, sample_prices):
        macd, signal, hist = calculate_macd(sample_prices)
        assert isinstance(macd, pd.Series)
        assert isinstance(signal, pd.Series)
        assert isinstance(hist, pd.Series)

    def test_macd_length(self, sample_prices):
        macd, _, _ = calculate_macd(sample_prices)
        assert len(macd) == len(sample_prices)


class TestBollinger:
    def test_bollinger_returns_three_series(self, sample_prices):
        upper, middle, lower = calculate_bollinger(sample_prices)
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)

    def test_bollinger_ordering(self, sample_prices):
        upper, middle, lower = calculate_bollinger(sample_prices)
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()


class TestSMA:
    def test_sma_length(self, sample_prices):
        sma = calculate_sma(sample_prices, period=20)
        assert len(sma) == len(sample_prices)

    def test_sma_first_n_nan(self, sample_prices):
        sma = calculate_sma(sample_prices, period=20)
        assert sma.iloc[:19].isna().all()


class TestEMA:
    def test_ema_length(self, sample_prices):
        ema = calculate_ema(sample_prices, period=20)
        assert len(ema) == len(sample_prices)

    def test_ema_not_all_nan(self, sample_prices):
        ema = calculate_ema(sample_prices, period=20)
        assert ema.iloc[5:].notna().any()


class TestVolumeSMA:
    def test_volume_sma(self, sample_volume):
        vsma = calculate_volume_sma(sample_volume, period=20)
        assert len(vsma) == len(sample_volume)
