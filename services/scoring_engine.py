"""Master Scoring Engine.

Total Score = (Fundamental * 0.5) + (Technical * 0.3) + (Sentiment * 0.2)

Sinyal:
    >= 70  STRONG BUY
    >= 55  BUY
    >= 40  HOLD
    >= 25  SELL
    <  25  STRONG SELL
"""
from __future__ import annotations

WEIGHTS = {
    "fundamental": 0.5,
    "technical": 0.3,
    "sentiment": 0.2,
}

SIGNAL_THRESHOLDS = [
    (70.0, "STRONG BUY"),
    (55.0, "BUY"),
    (40.0, "HOLD"),
    (25.0, "SELL"),
]


def classify_signal(total_score: float) -> str:
    for threshold, label in SIGNAL_THRESHOLDS:
        if total_score >= threshold:
            return label
    return "STRONG SELL"


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def master_score(fundamental: float, technical: float, sentiment: float) -> dict:
    """Gabungkan skor tiap engine (masing-masing 0-100) menjadi skor akhir."""
    components = {
        "fundamental": _clamp(fundamental),
        "technical": _clamp(technical),
        "sentiment": _clamp(sentiment),
    }
    total = round(sum(components[name] * WEIGHTS[name] for name in WEIGHTS), 2)
    return {
        "total_score": total,
        "signal": classify_signal(total),
        "components": components,
        "weights": WEIGHTS,
    }
