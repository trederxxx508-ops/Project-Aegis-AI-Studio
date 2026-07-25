"""Test Master Scoring Engine & Sentiment Engine."""
import pytest

from services import scoring_engine
from services.sentiment_engine import score_headlines


def test_weights_sum_to_one():
    assert sum(scoring_engine.WEIGHTS.values()) == pytest.approx(1.0)


def test_master_score_formula():
    result = scoring_engine.master_score(fundamental=80, technical=60, sentiment=50)
    # 80*0.5 + 60*0.3 + 50*0.2 = 68
    assert result["total_score"] == 68.0
    assert result["signal"] == "BUY"


@pytest.mark.parametrize(
    "total,expected",
    [
        (85, "STRONG BUY"),
        (70, "STRONG BUY"),
        (60, "BUY"),
        (45, "HOLD"),
        (30, "SELL"),
        (10, "STRONG SELL"),
    ],
)
def test_signal_thresholds(total, expected):
    assert scoring_engine.classify_signal(total) == expected


def test_component_scores_clamped():
    result = scoring_engine.master_score(fundamental=150, technical=-20, sentiment=50)
    assert result["components"]["fundamental"] == 100.0
    assert result["components"]["technical"] == 0.0


def test_sentiment_positive_headlines():
    result = score_headlines([
        "Company profit surges to record high",
        "Analysts upgrade stock, strong growth ahead",
        "Laba bersih naik, dividen jumbo dibagikan",
    ])
    assert result["score"] > 60
    assert result["label"] == "POSITIVE"
    assert result["headline_count"] == 3


def test_sentiment_negative_headlines():
    result = score_headlines([
        "Shares plunge after earnings miss",
        "Regulator opens fraud investigation",
        "Saham anjlok, kerugian membengkak",
    ])
    assert result["score"] < 40
    assert result["label"] == "NEGATIVE"


def test_sentiment_empty_is_neutral():
    result = score_headlines([])
    assert result["score"] == 50.0
    assert result["label"] == "NEUTRAL"
