"""Test Risk Engine — formula Section 5 blueprint."""
import pytest

from services.risk_engine import calculate_position_size


def test_known_values_match_blueprint_formula():
    # Modal 100 juta, risiko 2%, entry 1000, ATR 25, k=2 -> SL = 950, risk/share = 50
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
        atr_multiplier=2.0,
        win_rate=0.55,
        reward_risk_ratio=2.0,
    )
    assert result["stop_loss_price"] == 950.0
    assert result["risk_per_share"] == 50.0
    assert result["max_risk_amount_idr"] == 2_000_000.0

    # Base shares = 2_000_000 / 50 = 40_000
    # Kelly f = (0.55*2 - 0.45)/2 = 0.325 -> fractional = 0.08125
    # adjusted = 40_000 * 1.08125 = 43_250 -> 432 lot
    assert result["kelly_fraction"] == pytest.approx(0.0813, abs=1e-4)
    assert result["recommended_lots"] == 432
    assert result["recommended_shares"] == 43_200
    assert result["total_allocation_idr"] == 43_200 * 1000
    assert result["max_potential_loss_idr"] == 43_200 * 50
    assert result["take_profit_price"] == 1100.0
    assert result["warnings"] == []


def test_negative_kelly_clamped_to_zero():
    # Win rate rendah + RR kecil -> Kelly negatif -> tidak menambah posisi
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
        win_rate=0.30,
        reward_risk_ratio=1.0,
    )
    assert result["kelly_fraction"] == 0.0
    assert result["recommended_lots"] == 400  # murni base sizing


def test_allocation_capped_at_total_capital():
    # Risiko besar + SL rapat -> sizing teoretis melebihi modal -> dibatasi
    result = calculate_position_size(
        total_capital=10_000_000,
        max_risk_pct=0.5,
        entry_price=1000.0,
        atr_value=5.0,
        atr_multiplier=1.0,
    )
    assert result["total_allocation_idr"] <= 10_000_000
    assert result["portfolio_exposure_pct"] <= 100.0
    assert any("modal" in w.lower() for w in result["warnings"])


def test_stop_loss_floored_when_atr_too_large():
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=100.0,
        atr_value=80.0,
        atr_multiplier=2.0,
    )
    assert result["stop_loss_price"] > 0
    assert any("stop loss" in w.lower() for w in result["warnings"])


def test_zero_lots_when_capital_too_small():
    result = calculate_position_size(
        total_capital=100_000,
        max_risk_pct=0.01,
        entry_price=10_000.0,
        atr_value=200.0,
    )
    assert result["recommended_lots"] == 0
    assert result["total_allocation_idr"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"total_capital": 0},
        {"max_risk_pct": 0},
        {"max_risk_pct": 1.5},
        {"entry_price": -10},
        {"atr_value": 0},
        {"atr_multiplier": 0},
        {"win_rate": 1.5},
        {"reward_risk_ratio": 0},
    ],
)
def test_invalid_inputs_raise(kwargs):
    base = dict(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        calculate_position_size(**base)
