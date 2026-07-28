"""Test Backtest Engine.

Fokus utama: membuktikan tidak ada **lookahead bias**. Backtest yang diam-diam
memakai data masa depan akan tampak hebat tapi mustahil ditiru di dunia nyata,
sehingga justru berbahaya — pengguna mengira sistemnya terbukti padahal tidak.
"""
import numpy as np
import pandas as pd
import pytest

from services import backtest
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# LOOKAHEAD BIAS — pengujian paling penting di berkas ini
# ---------------------------------------------------------------------------

def test_scores_do_not_change_when_future_bars_are_added():
    """Skor bar ke-i harus sama persis, ada atau tidak ada data sesudahnya.

    Inilah definisi operasional "tanpa lookahead": bila menambahkan bar masa
    depan mengubah skor masa lalu, berarti skor itu ikut mengintip.
    """
    full = make_ohlcv(days=400, trend=0.001)
    truncated = full.iloc[:300]

    scores_full = backtest.technical_score_history(full)["score"].iloc[:300]
    scores_truncated = backtest.technical_score_history(truncated)["score"]

    pd.testing.assert_series_equal(
        scores_truncated, scores_full, check_names=False,
        obj="skor pada bar yang sama harus identik",
    )


def test_causal_support_resistance_ignores_future_bars():
    full = make_ohlcv(days=400)
    truncated = full.iloc[:300]

    sup_full, res_full = backtest.causal_support_resistance(full)
    sup_trunc, res_trunc = backtest.causal_support_resistance(truncated)

    pd.testing.assert_series_equal(sup_trunc, sup_full.iloc[:300], check_names=False)
    pd.testing.assert_series_equal(res_trunc, res_full.iloc[:300], check_names=False)


@pytest.mark.parametrize("bar", [250, 300, 380])
def test_causal_sr_matches_what_live_system_would_have_computed(bar):
    """Backtest harus meniru persis keputusan sistem live pada saat itu.

    Kalau S/R versi backtest berbeda dari yang dihitung sistem live pada
    tanggal tersebut, maka hasil uji tidak mewakili perilaku nyata — sekalipun
    tidak ada kebocoran data masa depan.
    """
    from services import market_data

    full = make_ohlcv(days=400)
    causal_sup, causal_res = backtest.causal_support_resistance(full)

    # Yang dilihat sistem live bila dijalankan pada bar tersebut
    live = market_data.support_resistance(full.iloc[: bar + 1])

    assert causal_sup.iloc[bar] == pytest.approx(live["support"], abs=0.01)
    assert causal_res.iloc[bar] == pytest.approx(live["resistance"], abs=0.01)


def test_entry_never_uses_signal_bar_price():
    """Posisi harus dibuka pada pembukaan bar BERIKUTNYA, bukan harga sinyal."""
    df = make_ohlcv(days=400, trend=0.002)
    result = backtest.run_backtest(df, entry_threshold=50.0, warmup=200)

    opens = df["Open"]
    for trade in result["trades"]:
        entry_date = pd.Timestamp(trade["entry_date"])
        matched = opens[opens.index.date == entry_date.date()]
        assert not matched.empty
        assert trade["entry_price"] == pytest.approx(float(matched.iloc[0]), abs=1e-4)


# ---------------------------------------------------------------------------
# Aturan keluar
# ---------------------------------------------------------------------------

def _fixed_frame(rows):
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close", "Volume"])


def test_stop_loss_assumed_first_when_both_hit_same_bar():
    """Asumsi pesimistis: bar yang menyentuh stop dan target dianggap rugi."""
    # Bar tunggal yang rentangnya melampaui stop sekaligus target
    df = _fixed_frame([[100, 100, 100, 100, 1]] * 3 + [[100, 200, 50, 100, 1]] * 3)
    scores = pd.Series([100.0] * len(df), index=df.index)
    atr = pd.Series([5.0] * len(df), index=df.index)

    trades = backtest._simulate_trades(
        df=df, scores=scores, atr=atr, entry_threshold=50.0,
        atr_multiplier=2.0, reward_risk_ratio=2.0, max_holding_days=10, warmup=2,
    )
    assert trades
    assert trades[0]["outcome"] == "stop_loss"
    assert trades[0]["return_pct"] < 0


def test_take_profit_recorded_when_only_target_hit():
    df = _fixed_frame(
        [[100, 101, 99, 100, 1]] * 3
        + [[100, 100.5, 99.5, 100, 1]]      # bar masuk, tenang
        + [[100, 125, 99.5, 120, 1]]        # menyentuh target saja
    )
    scores = pd.Series([100.0] * len(df), index=df.index)
    atr = pd.Series([5.0] * len(df), index=df.index)

    trades = backtest._simulate_trades(
        df=df, scores=scores, atr=atr, entry_threshold=50.0,
        atr_multiplier=2.0, reward_risk_ratio=2.0, max_holding_days=10, warmup=2,
    )
    assert trades[0]["outcome"] == "take_profit"
    assert trades[0]["return_pct"] > 0


def test_timeout_exit_when_neither_level_reached():
    df = _fixed_frame([[100, 100.2, 99.8, 100, 1]] * 12)
    scores = pd.Series([100.0] * len(df), index=df.index)
    atr = pd.Series([5.0] * len(df), index=df.index)

    trades = backtest._simulate_trades(
        df=df, scores=scores, atr=atr, entry_threshold=50.0,
        atr_multiplier=2.0, reward_risk_ratio=2.0, max_holding_days=3, warmup=2,
    )
    assert trades[0]["outcome"] == "timeout"
    assert trades[0]["holding_days"] == 3


def test_no_overlapping_positions():
    df = make_ohlcv(days=400, trend=0.001)
    result = backtest.run_backtest(df, entry_threshold=40.0, warmup=200)
    trades = result["trades"]
    for earlier, later in zip(trades, trades[1:]):
        assert earlier["exit_date"] < later["entry_date"], "posisi tidak boleh menumpuk"


def test_low_threshold_produces_more_trades_than_high():
    df = make_ohlcv(days=500, trend=0.001)
    banyak = backtest.run_backtest(df, entry_threshold=40.0, warmup=200)
    sedikit = backtest.run_backtest(df, entry_threshold=85.0, warmup=200)
    assert banyak["stats"]["trades"] >= sedikit["stats"]["trades"]


# ---------------------------------------------------------------------------
# Statistik & kejujuran laporan
# ---------------------------------------------------------------------------

def test_statistics_are_internally_consistent():
    df = make_ohlcv(days=600, trend=0.0015)
    result = backtest.run_backtest(df, entry_threshold=50.0, warmup=200)
    stats = result["stats"]

    if stats["trades"]:
        assert stats["wins"] + stats["losses"] == stats["trades"]
        assert 0 <= stats["win_rate"] <= 1
        assert stats["win_rate"] == pytest.approx(stats["wins"] / stats["trades"], abs=1e-6)
        assert stats["max_drawdown_pct"] <= 0
        assert sum(stats["outcomes"].values()) == stats["trades"]


def test_buy_and_hold_benchmark_is_reported():
    """Pembanding jujur: kalau sekadar menahan lebih baik, harus terlihat."""
    df = make_ohlcv(days=600, trend=0.002)
    result = backtest.run_backtest(df, entry_threshold=50.0, warmup=200)
    stats = result["stats"]
    assert "buy_and_hold_pct" in stats
    assert isinstance(stats["beats_buy_and_hold"], bool)
    assert stats["beats_buy_and_hold"] == (stats["total_return_pct"] > stats["buy_and_hold_pct"])


def test_verdict_admits_when_strategy_loses():
    """Kesimpulan harus mengakui kekalahan, bukan memilih kata yang enak dibaca."""
    stats = {
        "trades": 50, "profit_factor": 0.7, "total_return_pct": -12.0,
        "buy_and_hold_pct": 30.0, "beats_buy_and_hold": False,
        "max_drawdown_pct": -25.0, "buy_and_hold_max_drawdown_pct": -20.0,
        "return_per_drawdown": None, "buy_and_hold_return_per_drawdown": 1.5,
        "market_exposure_pct": 60.0,
    }
    verdict = backtest._verdict(stats)
    assert "merugi" in verdict
    assert "beli-dan-tahan lebih unggul" in verdict


def test_verdict_reports_risk_efficiency_when_return_lags():
    """Kalah hasil tapi menang efisiensi risiko harus tetap terlihat jelas."""
    stats = {
        "trades": 100, "profit_factor": 1.8, "total_return_pct": 156.0,
        "buy_and_hold_pct": 208.0, "beats_buy_and_hold": False,
        "max_drawdown_pct": -18.0, "buy_and_hold_max_drawdown_pct": -34.0,
        "return_per_drawdown": 8.65, "buy_and_hold_return_per_drawdown": 6.1,
        "market_exposure_pct": 76.0,
    }
    verdict = backtest._verdict(stats)
    assert "beli-dan-tahan lebih unggul dari sisi hasil" in verdict
    assert "strategi lebih efisien terhadap risiko" in verdict
    assert "76.0%" in verdict


def test_random_baseline_makes_win_rate_interpretable():
    """Win rate tanpa pembanding acak mudah disalahpahami sebagai 'buruk'."""
    df = make_ohlcv(days=600, trend=0.001)
    result = backtest.run_backtest(df, entry_threshold=50.0, warmup=200)
    stats = result["stats"]

    assert stats["random_baseline_win_rate"] is not None
    assert 0 <= stats["random_baseline_win_rate"] <= 1
    assert stats["edge_vs_random_pp"] == pytest.approx(
        (stats["win_rate"] - stats["random_baseline_win_rate"]) * 100, abs=0.01
    )


def test_wider_target_lowers_random_baseline_win_rate():
    """Target yang lebih jauh membuat win rate rendah secara struktural.

    Inilah sebabnya win rate 44% pada R:R 2:1 tidak boleh dinilai buruk
    tanpa melihat pembandingnya.
    """
    df = make_ohlcv(days=600, trend=0.0005)
    atr = backtest.technical_score_history(df)["atr"]

    sempit = backtest.random_entry_baseline(
        df, atr, n_trades=60, atr_multiplier=2.0, reward_risk_ratio=1.0,
        max_holding_days=60, warmup=200, rounds=15,
    )
    lebar = backtest.random_entry_baseline(
        df, atr, n_trades=60, atr_multiplier=2.0, reward_risk_ratio=4.0,
        max_holding_days=60, warmup=200, rounds=15,
    )
    assert sempit["win_rate"] > lebar["win_rate"]


def test_small_edge_is_not_called_significant():
    """Selisih di dalam rentang kebetulan tidak boleh diklaim sebagai keunggulan."""
    stats = {
        "trades": 100, "profit_factor": 1.8, "total_return_pct": 150.0,
        "buy_and_hold_pct": 200.0, "beats_buy_and_hold": False, "win_rate": 0.44,
        "random_baseline_win_rate": 0.445, "random_baseline_noise_pp": 4.1,
        "edge_vs_random_pp": -0.5, "edge_is_significant": False,
        "max_drawdown_pct": -18.0, "buy_and_hold_max_drawdown_pct": -34.0,
        "return_per_drawdown": 8.3, "buy_and_hold_return_per_drawdown": 5.9,
        "market_exposure_pct": 76.0,
    }
    verdict = backtest._verdict(stats)
    assert "BELUM terbukti" in verdict
    assert "manajemen risiko" in verdict
    assert "wajar secara matematis" in verdict


def test_significant_edge_is_reported_as_such():
    stats = {
        "trades": 100, "profit_factor": 2.0, "total_return_pct": 250.0,
        "buy_and_hold_pct": 100.0, "beats_buy_and_hold": True, "win_rate": 0.60,
        "random_baseline_win_rate": 0.44, "random_baseline_noise_pp": 3.0,
        "edge_vs_random_pp": 16.0, "edge_is_significant": True,
        "max_drawdown_pct": -15.0, "buy_and_hold_max_drawdown_pct": -30.0,
        "return_per_drawdown": 16.7, "buy_and_hold_return_per_drawdown": 3.3,
        "market_exposure_pct": 50.0,
    }
    verdict = backtest._verdict(stats)
    assert "di luar rentang kebetulan" in verdict
    assert "memang menambah nilai" in verdict


def test_assumptions_are_disclosed():
    df = make_ohlcv(days=400)
    result = backtest.run_backtest(df, warmup=200)
    text = " ".join(result["assumptions"]).lower()
    assert "pembukaan bar berikutnya" in text
    assert "pesimistis" in text
    assert "biaya transaksi" in text


def test_requires_enough_history():
    with pytest.raises(ValueError, match="Butuh minimal"):
        backtest.run_backtest(make_ohlcv(days=100), warmup=200)


# ---------------------------------------------------------------------------
# Kalibrasi masukan risiko — mengganti win rate yang selama ini ditebak
# ---------------------------------------------------------------------------

def test_calibration_refuses_small_sample():
    result = {"stats": {"trades": 12, "win_rate": 0.75, "avg_win_pct": 5, "avg_loss_pct": 2}}
    calib = backtest.calibrated_risk_inputs(result)
    assert calib["usable"] is False
    assert "terlalu sedikit" in calib["reason"]


def test_calibration_supplies_measured_inputs():
    result = {"stats": {
        "trades": 80, "win_rate": 0.58, "avg_win_pct": 4.0,
        "avg_loss_pct": 2.0, "expectancy_pct": 1.48,
    }}
    calib = backtest.calibrated_risk_inputs(result)
    assert calib["usable"] is True
    assert calib["win_rate"] == 0.58
    assert calib["reward_risk_ratio"] == 2.0
    assert calib["sample_size"] == 80


def test_calibration_handles_no_trades():
    calib = backtest.calibrated_risk_inputs({"stats": {"trades": 0, "win_rate": None}})
    assert calib["usable"] is False


# ---------------------------------------------------------------------------
# Pengambilan data
# ---------------------------------------------------------------------------

def test_backtest_ticker_uses_injected_fetcher():
    df = make_ohlcv(days=400, trend=0.001)
    result = backtest.backtest_ticker(
        "bbca.jk", fetcher=lambda t, period="5y": df
    )
    assert result["ticker"] == "BBCA.JK"
    assert result["period"]["bars_total"] == 400


def test_flat_market_produces_no_false_confidence():
    """Pasar datar tidak boleh menghasilkan klaim kemenangan."""
    flat = pd.DataFrame(
        {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0},
        index=pd.bdate_range("2023-01-01", periods=400),
    )
    result = backtest.run_backtest(flat, entry_threshold=50.0, warmup=200)
    stats = result["stats"]
    if stats["trades"]:
        assert stats["total_return_pct"] == pytest.approx(0.0, abs=1e-6)
