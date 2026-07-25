"""Test Technical Engine — indikator & skor."""
import numpy as np
import pandas as pd
import pytest

from services import market_data


def test_ema_matches_pandas_ewm(ohlcv_uptrend):
    close = ohlcv_uptrend["Close"]
    expected = close.ewm(span=20, adjust=False).mean()
    pd.testing.assert_series_equal(market_data.ema(close, 20), expected)


def test_rsi_bounds_and_direction(ohlcv_uptrend, ohlcv_downtrend):
    rsi_up = market_data.rsi(ohlcv_uptrend["Close"]).dropna()
    rsi_down = market_data.rsi(ohlcv_downtrend["Close"]).dropna()
    assert ((rsi_up >= 0) & (rsi_up <= 100)).all()
    assert rsi_up.iloc[-1] > rsi_down.iloc[-1]


def test_rsi_all_gains_near_100():
    series = pd.Series(np.linspace(100, 200, 60))
    result = market_data.rsi(series).dropna()
    assert result.iloc[-1] > 99


def test_macd_components_consistent(ohlcv_uptrend):
    close = ohlcv_uptrend["Close"]
    macd_line, signal_line, hist = market_data.macd(close)
    pd.testing.assert_series_equal(hist, macd_line - signal_line)
    expected_macd = market_data.ema(close, 12) - market_data.ema(close, 26)
    pd.testing.assert_series_equal(macd_line, expected_macd)


def test_atr_positive_and_scales_with_range(ohlcv_uptrend):
    atr = market_data.atr(ohlcv_uptrend).dropna()
    assert (atr > 0).all()

    wide = ohlcv_uptrend.copy()
    wide["High"] = wide["High"] * 1.05
    wide["Low"] = wide["Low"] * 0.95
    atr_wide = market_data.atr(wide).dropna()
    assert atr_wide.iloc[-1] > atr.iloc[-1]


def test_support_resistance_brackets_price(ohlcv_uptrend):
    sr = market_data.support_resistance(ohlcv_uptrend)
    close = float(ohlcv_uptrend["Close"].iloc[-1])
    assert sr["support"] < close
    assert sr["resistance"] > close


def test_compute_indicators_snapshot(ohlcv_uptrend):
    ind = market_data.compute_indicators(ohlcv_uptrend)
    for key in (
        "last_price", "ema_20", "ema_50", "ema_200", "rsi_14",
        "macd", "macd_signal", "macd_histogram", "atr_14",
        "support", "resistance",
    ):
        assert key in ind
    assert ind["atr_14"] > 0
    assert 0 <= ind["rsi_14"] <= 100


def test_compute_indicators_requires_enough_bars(ohlcv_uptrend):
    with pytest.raises(ValueError):
        market_data.compute_indicators(ohlcv_uptrend.head(10))


def test_technical_score_uptrend_beats_downtrend(ohlcv_uptrend, ohlcv_downtrend):
    score_up = market_data.technical_score(market_data.compute_indicators(ohlcv_uptrend))
    score_down = market_data.technical_score(market_data.compute_indicators(ohlcv_downtrend))
    assert 0 <= score_down["score"] < score_up["score"] <= 100
    assert set(score_up["breakdown"]) == {
        "trend_ema", "momentum_rsi", "macd", "support_resistance",
    }
