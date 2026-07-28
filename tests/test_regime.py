"""Test Regime Detector — apakah sistem tahu saat modelnya sendiri tak berlaku."""
from datetime import date, timedelta

import numpy as np
import pytest

from services import macro_engine, regime


def _build_series(correlation_sign: int, days: int = 400, seed: int = 7):
    """Bangun deret suku bunga riil & harga emas dengan arah hubungan tertentu.

    ``correlation_sign`` -1 meniru pasar normal (bunga riil naik -> emas turun),
    +1 meniru rezim putus (keduanya bergerak searah).
    """
    rng = np.random.default_rng(seed)
    start = date(2024, 1, 1)
    dates = []
    d = start
    while len(dates) < days:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)

    yield_changes = rng.normal(0, 0.03, days)
    real_yield = 2.0 + np.cumsum(yield_changes)
    noise = rng.normal(0, 0.3, days)
    gold_returns = correlation_sign * yield_changes * 30 + noise
    gold = 2000 * np.exp(np.cumsum(gold_returns / 100))

    return (
        [(dt, float(v)) for dt, v in zip(dates, real_yield)],
        {dt: float(v) for dt, v in zip(dates, gold)},
    )


@pytest.fixture
def patch_fred(monkeypatch):
    def _apply(series):
        monkeypatch.setattr(
            macro_engine, "fetch_fred_series", lambda sid, use_cache=True: series
        )
    return _apply


def test_normal_regime_keeps_full_macro_weight(patch_fred):
    ry, gold = _build_series(correlation_sign=-1)
    patch_fred(ry)

    health = regime.relationship_health(gold, use_cache=False)
    assert health["status"] == "normal"
    assert health["correlation"] < regime.THRESHOLD_NORMAL
    assert health["weights"]["macro"] == 0.50
    assert "seperti biasanya" in health["explanation"]


def test_broken_regime_cuts_macro_weight(patch_fred):
    """Emas bergerak searah suku bunga riil = model makro sedang tidak berlaku."""
    ry, gold = _build_series(correlation_sign=+1)
    patch_fred(ry)

    health = regime.relationship_health(gold, use_cache=False)
    assert health["status"] == "putus"
    assert health["correlation"] > 0
    assert health["weights"]["macro"] == 0.20
    assert health["weights"]["technical"] == 0.50, "pergelaran beralih ke harga"
    assert "PUTUS" in health["explanation"]


def test_weights_always_sum_to_one():
    for status, weights in regime.WEIGHTS_BY_STATUS.items():
        assert sum(weights.values()) == pytest.approx(1.0), status
        assert set(weights) == {"macro", "technical", "sentiment"}


def test_broken_regime_relies_less_on_macro_than_normal():
    normal = regime.WEIGHTS_BY_STATUS["normal"]["macro"]
    weak = regime.WEIGHTS_BY_STATUS["melemah"]["macro"]
    broken = regime.WEIGHTS_BY_STATUS["putus"]["macro"]
    assert normal > weak > broken


@pytest.mark.parametrize(
    "correlation,expected",
    [(-0.60, "normal"), (-0.25, "normal"), (-0.21, "normal"),
     (-0.19, "melemah"), (-0.01, "melemah"),
     (0.0, "putus"), (0.35, "putus")],
)
def test_classification_thresholds(correlation, expected):
    assert regime._classify(correlation) == expected


def test_unmeasurable_regime_is_cautious_not_confident(patch_fred):
    """Gagal mengukur harus menurunkan keyakinan, bukan diam-diam memakai bobot penuh."""
    ry, gold = _build_series(correlation_sign=-1, days=40)
    patch_fred(ry)

    health = regime.relationship_health(gold, use_cache=False)
    assert health["status"] == "tidak_diketahui"
    assert health["weights"]["macro"] == 0.35
    assert health["weights"]["macro"] < regime.WEIGHTS_BY_STATUS["normal"]["macro"]
    assert health["error"]


def test_history_context_is_reported(patch_fred):
    ry, gold = _build_series(correlation_sign=-1)
    patch_fred(ry)

    health = regime.relationship_health(gold, use_cache=False)
    assert health["samples"] > 0
    assert health["historical_median"] is not None
    assert 0 <= health["percentile_vs_history"] <= 100


def test_thresholds_match_documented_empirical_values():
    """Ambang harus tetap sesuai sebaran yang didokumentasikan (2016-2026)."""
    assert regime.THRESHOLD_NORMAL == -0.20
    assert regime.THRESHOLD_BROKEN == 0.0
    assert regime.LONG_RUN_BASELINE == pytest.approx(-0.44, abs=0.01)
