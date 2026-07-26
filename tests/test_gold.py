"""Test modul emas: makro, sentimen khusus emas, jam pasar, ukuran ounce."""
from datetime import datetime, timezone

import pytest

from services import gold, gold_sentiment, macro_engine, market_data, market_hours, risk_engine
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Sentimen khusus emas — perhatikan polaritasnya TERBALIK dari saham
# ---------------------------------------------------------------------------

def test_crisis_news_is_bullish_for_gold():
    """Krisis buruk bagi saham, tapi mendorong emas naik."""
    result = gold_sentiment.score_gold_headlines([
        "War escalates as tensions rise across the region",
        "Investors flee to safe haven amid banking crisis",
        "Krisis geopolitik memicu perburuan aset aman",
    ])
    assert result["score"] > 60
    assert result["label"] == "BULLISH"


def test_tightening_news_is_bearish_for_gold():
    result = gold_sentiment.score_gold_headlines([
        "Fed signals another rate hike as hawkish tone returns",
        "Stronger dollar pressures commodities",
        "Dolar menguat, aksi ambil untung menekan harga",
    ])
    assert result["score"] < 40
    assert result["label"] == "BEARISH"


def test_gold_lexicon_differs_from_stock_lexicon():
    """Bukti bahwa kamus emas memang perlu terpisah."""
    from services.sentiment_engine import score_headlines as stock_score

    headline = ["Recession fears deepen as crisis spreads"]
    gold_result = gold_sentiment.score_gold_headlines(headline)
    stock_result = stock_score(headline)
    assert gold_result["score"] > 50, "resesi mendorong emas naik"
    assert stock_result["score"] <= 50, "resesi menekan saham"


def test_empty_headlines_neutral():
    result = gold_sentiment.score_gold_headlines([])
    assert result["score"] == 50.0
    assert result["label"] == "NEUTRAL"


def test_phrases_weigh_more_than_single_words():
    with_phrase = gold_sentiment.score_gold_headlines(["Fed announces a rate cut this week"])
    assert with_phrase["details"][0]["bullish_hits"] >= 2


# ---------------------------------------------------------------------------
# Jam pasar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "moment,expected_open",
    [
        (datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc), False),  # Sabtu
        (datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc), False),  # Minggu siang
        (datetime(2026, 7, 26, 23, 0, tzinfo=timezone.utc), True),   # Minggu 19:00 ET
        (datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc), True),   # Rabu 11:00 ET
        (datetime(2026, 7, 22, 21, 30, tzinfo=timezone.utc), False),  # Rabu 17:30 ET (jeda)
        (datetime(2026, 7, 24, 22, 0, tzinfo=timezone.utc), False),  # Jumat 18:00 ET
    ],
)
def test_gold_market_open_state(moment, expected_open):
    assert market_hours.gold_market_status(moment)["is_open"] is expected_open


def test_market_status_reports_both_timezones():
    status = market_hours.gold_market_status(datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc))
    assert "WIB" in status["local_time_jakarta"]
    assert status["reason"]


def test_price_freshness_descriptions():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    fresh = market_hours.describe_price_freshness(datetime(2026, 7, 26, 11, 50, tzinfo=timezone.utc), now)
    assert fresh["is_intraday_fresh"] is True

    stale = market_hours.describe_price_freshness(datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc), now)
    assert stale["is_intraday_fresh"] is False
    assert "hari" in stale["description"]


# ---------------------------------------------------------------------------
# Ukuran posisi dalam troy ounce (pecahan diizinkan)
# ---------------------------------------------------------------------------

def test_gold_position_sizing_allows_fractional_ounces():
    result = risk_engine.calculate_position_size(
        total_capital=10_000,
        max_risk_pct=0.02,
        entry_price=4_000.0,
        atr_value=50.0,
        atr_multiplier=2.0,
        unit_size=1,
        allow_fractional=True,
        unit_name="troy ounce",
        currency="USD",
    )
    assert result["currency"] == "USD"
    assert result["unit_name"] == "troy ounce"
    assert isinstance(result["recommended_units"], float)
    assert 0 < result["recommended_units"] < 3
    assert result["stop_loss_price"] == 3_900.0
    # Risiko nyata tidak boleh melebihi batas yang diminta, sekecil apa pun
    assert result["max_potential_loss"] <= 10_000 * 0.02
    assert result["within_risk_budget"] is True
    assert result["actual_risk_pct"] <= 2.0


def test_fractional_units_never_round_up_past_the_risk_cap():
    """Pembulatan ke atas sekecil apa pun tetap melanggar batas risiko."""
    for entry, atr in [(4070.8, 78.13), (1234.56, 19.87), (999.99, 7.77)]:
        result = risk_engine.calculate_position_size(
            total_capital=10_000, max_risk_pct=0.02, entry_price=entry,
            atr_value=atr, unit_size=1, allow_fractional=True,
            unit_name="troy ounce", currency="USD",
        )
        assert result["within_risk_budget"] is True, f"gagal pada entry {entry}"
        assert result["max_potential_loss"] <= 10_000 * 0.02 + 1e-9


def test_stock_sizing_still_whole_lots_by_default():
    result = risk_engine.calculate_position_size(
        total_capital=100_000_000, max_risk_pct=0.02, entry_price=1000.0, atr_value=25.0
    )
    assert isinstance(result["recommended_units"], int)
    assert result["currency"] == "IDR"
    assert result["unit_name"] == "lot"
    # 400, bukan 432: Kelly tidak berjalan tanpa win rate terukur
    assert result["recommended_units"] == result["recommended_lots"] == 400
    assert result["within_risk_budget"] is True


def test_gold_allocation_capped_by_capital():
    result = risk_engine.calculate_position_size(
        total_capital=1_000,
        max_risk_pct=0.5,
        entry_price=4_000.0,
        atr_value=10.0,
        atr_multiplier=1.0,
        unit_size=1,
        allow_fractional=True,
        unit_name="troy ounce",
        currency="USD",
    )
    assert result["total_allocation"] <= 1_000
    assert result["portfolio_exposure_pct"] <= 100.0


# ---------------------------------------------------------------------------
# Skor makro — data diganti tiruan agar test berjalan tanpa jaringan
# ---------------------------------------------------------------------------

def _fake_indicator(key, value, change_3m=0.0, avg_50=None, available=True, stale=False):
    return {
        "key": key, "label": macro_engine.LABELS[key], "available": available,
        "value": value, "as_of": "2026-07-24", "age_days": 2, "stale": stale,
        "source": "FRED (uji)", "change_1m": change_3m / 3, "change_3m": change_3m,
        "avg_50": avg_50, "observations": 300, "error": None,
    }


def _patch_macro(monkeypatch, indicators):
    monkeypatch.setattr(macro_engine, "load_indicator", lambda k, use_cache=True: indicators[k])
    monkeypatch.setattr(
        macro_engine, "cpi_year_over_year",
        lambda use_cache=True: {**indicators["cpi"], "yoy_pct": 3.2},
    )


def test_negative_real_yield_scores_high(monkeypatch):
    _patch_macro(monkeypatch, {
        "real_yield_10y": _fake_indicator("real_yield_10y", -0.5, change_3m=-0.3),
        "dollar_index": _fake_indicator("dollar_index", 95.0, change_3m=-2.0, avg_50=100.0),
        "breakeven_10y": _fake_indicator("breakeven_10y", 2.7, change_3m=0.2),
        "nominal_yield_10y": _fake_indicator("nominal_yield_10y", 3.5, change_3m=-0.4),
        "fed_funds_rate": _fake_indicator("fed_funds_rate", 3.0),
        "cpi": _fake_indicator("cpi", 310.0),
    })
    result = macro_engine.macro_score(use_cache=False)
    assert result["score"] >= 90, "semua faktor mendukung emas"
    assert result["completeness_pct"] == 100.0
    assert result["notes"] == []


def test_high_rising_real_yield_scores_low(monkeypatch):
    _patch_macro(monkeypatch, {
        "real_yield_10y": _fake_indicator("real_yield_10y", 3.5, change_3m=0.4),
        "dollar_index": _fake_indicator("dollar_index", 110.0, change_3m=3.0, avg_50=105.0),
        "breakeven_10y": _fake_indicator("breakeven_10y", 1.4, change_3m=-0.2),
        "nominal_yield_10y": _fake_indicator("nominal_yield_10y", 5.0, change_3m=0.5),
        "fed_funds_rate": _fake_indicator("fed_funds_rate", 5.5),
        "cpi": _fake_indicator("cpi", 310.0),
    })
    result = macro_engine.macro_score(use_cache=False)
    assert result["score"] <= 15, "semua faktor menekan emas"


def test_missing_indicator_scores_neutral_and_lowers_completeness(monkeypatch):
    _patch_macro(monkeypatch, {
        "real_yield_10y": _fake_indicator("real_yield_10y", None, available=False),
        "dollar_index": _fake_indicator("dollar_index", 100.0, change_3m=-1.0, avg_50=102.0),
        "breakeven_10y": _fake_indicator("breakeven_10y", 2.3, change_3m=0.1),
        "nominal_yield_10y": _fake_indicator("nominal_yield_10y", 4.0, change_3m=-0.3),
        "fed_funds_rate": _fake_indicator("fed_funds_rate", 4.0),
        "cpi": _fake_indicator("cpi", 310.0),
    })
    result = macro_engine.macro_score(use_cache=False)

    assert result["completeness_pct"] == 75.0
    assert result["components_available"] == 3
    # Komponen hilang dinilai separuh, bukan ditebak
    assert result["breakdown"]["real_yield"]["points"] == 20.0
    assert result["breakdown"]["real_yield"]["available"] is False
    assert any("tidak tersedia" in n for n in result["notes"])


def test_stale_data_is_flagged(monkeypatch):
    _patch_macro(monkeypatch, {
        "real_yield_10y": _fake_indicator("real_yield_10y", 1.0, stale=True),
        "dollar_index": _fake_indicator("dollar_index", 100.0, avg_50=102.0),
        "breakeven_10y": _fake_indicator("breakeven_10y", 2.3),
        "nominal_yield_10y": _fake_indicator("nominal_yield_10y", 4.0),
        "fed_funds_rate": _fake_indicator("fed_funds_rate", 4.0),
        "cpi": _fake_indicator("cpi", 310.0),
    })
    result = macro_engine.macro_score(use_cache=False)
    assert any("lebih lama dari biasanya" in n for n in result["notes"])


def test_fred_csv_parser_skips_missing_values():
    csv_text = "observation_date,DFII10\n2026-07-20,2.10\n2026-07-21,.\n2026-07-22,2.15\n"
    rows = macro_engine._parse_fred_csv(csv_text)
    assert len(rows) == 2
    assert rows[-1][1] == 2.15


def test_fred_parser_rejects_garbage():
    with pytest.raises(ValueError):
        macro_engine._parse_fred_csv("bukan,csv,yang,benar\n")


# ---------------------------------------------------------------------------
# Pipeline emas menyeluruh
# ---------------------------------------------------------------------------

@pytest.fixture
def gold_pipeline(monkeypatch):
    monkeypatch.setattr(
        market_data, "fetch_ohlcv",
        lambda s, period="1y", interval="1d": make_ohlcv(trend=0.002, start_price=4000),
    )
    monkeypatch.setattr(
        macro_engine, "macro_score",
        lambda use_cache=True: {
            "score": 72.0, "breakdown": {}, "completeness_pct": 100.0,
            "components_available": 4, "components_total": 4, "notes": [],
            "context": {}, "computed_at": "2026-07-26T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        gold, "gold_sentiment",
        lambda extra_headlines=None: {
            "score": 60.0, "label": "BULLISH", "headline_count": 2, "details": [],
        },
    )


def test_analyze_gold_uses_macro_weighting(gold_pipeline):
    result = gold.analyze_gold(total_capital=10_000, use_cache=False)

    assert result["asset"] == "GOLD"
    assert result["currency"] == "USD"
    assert set(result["scores"]["weights"]) == {"macro", "technical", "sentiment"}
    assert result["scores"]["weights"]["macro"] == 0.5

    comps = result["scores"]["components"]
    expected = round(72.0 * 0.5 + comps["technical"] * 0.3 + 60.0 * 0.2, 2)
    assert result["total_score"] == pytest.approx(expected, abs=0.01)

    rp = result["risk_plan"]
    assert rp["unit_name"] == "troy ounce"
    assert rp["currency"] == "USD"
    assert rp["stop_loss_price"] < rp["entry_price"] < rp["take_profit_price"]


def test_analyze_gold_reports_price_source_and_market_state(gold_pipeline):
    result = gold.analyze_gold(use_cache=False)
    assert result["price_source"]["symbol"] == "GC=F"
    assert result["price_source"]["is_per_ounce"] is True
    assert "is_open" in result["market_status"]
    assert "description" in result["price_freshness"]


def test_gold_falls_back_when_primary_symbol_fails(monkeypatch, gold_pipeline):
    def only_gld(symbol, period="1y", interval="1d"):
        if symbol != "GLD":
            raise ValueError(f"Tidak ada data harga untuk simbol '{symbol}'.")
        return make_ohlcv(trend=0.001, start_price=190)

    monkeypatch.setattr(market_data, "fetch_ohlcv", only_gld)
    monkeypatch.setattr(market_data, "fetch_chart_api", lambda s, range_="1y", interval="1d": only_gld(s))

    result = gold.analyze_gold(use_cache=False)
    assert result["price_source"]["symbol"] == "GLD"
    assert result["price_source"]["is_per_ounce"] is False
    assert result["quote_unit"] == "unit ETF"
    # Pengguna harus diberi tahu bahwa angkanya bukan harga per ounce
    assert any("BUKAN harga per troy ounce" in w for w in result["warnings"])
    assert [a["symbol"] for a in result["price_source"]["failed_attempts"]] == ["GC=F"]


def test_gold_raises_when_all_sources_fail(monkeypatch, gold_pipeline):
    def always_fail(symbol, period="1y", interval="1d", range_="1y"):
        raise ValueError("tidak ada data")

    monkeypatch.setattr(market_data, "fetch_ohlcv", always_fail)
    monkeypatch.setattr(market_data, "fetch_chart_api", always_fail)
    with pytest.raises(ConnectionError, match="Semua sumber harga emas gagal"):
        gold.analyze_gold(use_cache=False)
