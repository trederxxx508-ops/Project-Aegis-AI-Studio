"""Test Watchlist Scanner & cache — sumber data eksternal di-mock."""
import pytest

from services import cache, fundamental_engine, market_data, scanner, sentiment_engine
from tests.conftest import make_ohlcv


@pytest.fixture
def mocked_market(monkeypatch):
    """Setiap ticker mendapat tren berbeda supaya peringkatnya deterministik."""
    trends = {"AAA.JK": 0.003, "BBB.JK": 0.001, "CCC.JK": -0.003}

    def fake_fetch(ticker, period="1y", interval="1d"):
        if ticker not in trends:
            raise ValueError(f"Tidak ada data harga untuk ticker '{ticker}'.")
        return make_ohlcv(trend=trends[ticker])

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(
        sentiment_engine, "sentiment_score",
        lambda t: {"score": 50.0, "label": "NEUTRAL", "headline_count": 0, "details": []},
    )
    monkeypatch.setattr(
        fundamental_engine, "score_fundamental",
        lambda t, use_rag=True: {"score": 60.0, "source": "yfinance_ratios"},
    )
    return trends


def test_scan_ranks_by_total_score(mocked_market):
    result = scanner.scan_watchlist(["AAA.JK", "BBB.JK", "CCC.JK"], use_cache=False)

    assert result["requested"] == 3
    assert result["analyzed"] == 3
    assert result["errors"] == []

    scores = [r["total_score"] for r in result["results"]]
    assert scores == sorted(scores, reverse=True), "hasil harus terurut menurun"
    assert [r["rank"] for r in result["results"]] == [1, 2, 3]
    assert result["top_pick"] == result["results"][0]["ticker"]
    # Tren naik harus mengungguli tren turun
    assert result["results"][0]["ticker"] == "AAA.JK"
    assert result["results"][-1]["ticker"] == "CCC.JK"


def test_scan_isolates_failing_tickers(mocked_market):
    result = scanner.scan_watchlist(["AAA.JK", "TIDAKADA.JK", "BBB.JK"], use_cache=False)

    assert result["analyzed"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0]["ticker"] == "TIDAKADA.JK"
    assert "Tidak ada data harga" in result["errors"][0]["error"]


def test_scan_deduplicates_and_uppercases(mocked_market):
    result = scanner.scan_watchlist(["aaa.jk", "AAA.JK", " bbb.jk "], use_cache=False)
    assert result["requested"] == 2
    assert {r["ticker"] for r in result["results"]} == {"AAA.JK", "BBB.JK"}


def test_scan_min_score_filter(mocked_market):
    full = scanner.scan_watchlist(["AAA.JK", "BBB.JK", "CCC.JK"], use_cache=False)
    cutoff = full["results"][0]["total_score"]
    filtered = scanner.scan_watchlist(
        ["AAA.JK", "BBB.JK", "CCC.JK"], min_score=cutoff, use_cache=False
    )
    assert filtered["analyzed"] == 3
    assert filtered["passed_filter"] == 1
    assert all(r["total_score"] >= cutoff for r in filtered["results"])


def test_scan_empty_list_raises():
    with pytest.raises(ValueError):
        scanner.scan_watchlist([])


def test_summarize_row_shape(mocked_market):
    result = scanner.scan_watchlist(["AAA.JK"], use_cache=False)
    rows = scanner.summarize(result)
    assert len(rows) == 1
    for key in (
        "rank", "ticker", "signal", "total_score", "price", "rsi_14",
        "stop_loss", "take_profit", "lots", "allocation", "exposure_pct",
    ):
        assert key in rows[0]
    assert rows[0]["stop_loss"] < rows[0]["price"] < rows[0]["take_profit"]


def test_scan_flags_rate_limit(monkeypatch):
    def rate_limited(ticker, period="1y", interval="1d"):
        raise market_data.RateLimitedError("Penyedia data membatasi permintaan.")

    monkeypatch.setattr(market_data, "fetch_ohlcv", rate_limited)
    result = scanner.scan_watchlist(["AAA.JK", "BBB.JK"], use_cache=False)

    assert result["analyzed"] == 0
    assert result["rate_limited"] is True
    assert all(e["rate_limited"] for e in result["errors"])


def test_scan_not_flagged_rate_limit_for_other_errors(mocked_market):
    result = scanner.scan_watchlist(["TIDAKADA.JK"], use_cache=False)
    assert result["rate_limited"] is False
    assert result["errors"][0]["kind"] == "ValueError"


def test_watchlist_presets_are_valid():
    assert "idx_bluechip" in scanner.WATCHLISTS
    for name, tickers in scanner.WATCHLISTS.items():
        assert tickers, f"watchlist {name} kosong"
        assert len(tickers) == len(set(tickers)), f"watchlist {name} punya duplikat"


def test_cache_serves_within_ttl_and_expires():
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    assert cache.get_or_compute("k", 60, compute) == 1
    assert cache.get_or_compute("k", 60, compute) == 1  # dilayani dari cache
    assert calls["n"] == 1

    # TTL 0 -> entri langsung dianggap basi
    assert cache.get_or_compute("k", 0, compute) == 2
    assert calls["n"] == 2


def test_cache_avoids_refetching_same_ticker(mocked_market, monkeypatch):
    calls = {"n": 0}
    original = market_data.fetch_ohlcv

    def counting_fetch(ticker, period="1y", interval="1d"):
        calls["n"] += 1
        return original(ticker, period=period, interval=interval)

    monkeypatch.setattr(market_data, "fetch_ohlcv", counting_fetch)

    scanner.scan_watchlist(["AAA.JK"], use_cache=True)
    scanner.scan_watchlist(["AAA.JK"], use_cache=True)
    assert calls["n"] == 1, "pemindaian kedua harus dilayani dari cache"
