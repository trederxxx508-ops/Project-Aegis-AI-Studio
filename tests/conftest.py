"""Fixtures bersama untuk test suite Project Aegis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(days: int = 300, start_price: float = 1000.0, trend: float = 0.001, seed: int = 42) -> pd.DataFrame:
    """DataFrame OHLCV sintetis dengan tren + noise deterministik."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-07-24", periods=days)
    returns = trend + rng.normal(0, 0.01, days)
    close = start_price * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.003, days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, days)))
    volume = rng.integers(1_000_000, 10_000_000, days).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


@pytest.fixture(autouse=True)
def clear_market_cache():
    """Cache TTL bersifat global — kosongkan agar test tidak saling bocor."""
    from services import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ohlcv_uptrend() -> pd.DataFrame:
    return make_ohlcv(trend=0.002)


@pytest.fixture
def ohlcv_downtrend() -> pd.DataFrame:
    return make_ohlcv(trend=-0.002)
