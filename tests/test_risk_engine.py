"""Test Risk Engine — formula Section 5 blueprint."""
import pytest

from services.risk_engine import calculate_position_size


def test_blueprint_formula_exceeds_stated_max_risk():
    """Rumus blueprint asli melampaui batas risiko yang diminta pengguna.

    Ini didokumentasikan sebagai perilaku yang dipilih secara sadar
    (``cap_at_max_risk=False``), bukan perilaku bawaan.
    """
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
        atr_multiplier=2.0,
        win_rate=0.55,
        reward_risk_ratio=2.0,
        cap_at_max_risk=False,
    )
    assert result["stop_loss_price"] == 950.0
    assert result["risk_per_share"] == 50.0
    assert result["max_risk_amount"] == 2_000_000.0

    # Base shares = 2_000_000 / 50 = 40_000
    # Kelly f = (0.55*2 - 0.45)/2 = 0.325 -> fractional = 0.08125
    # adjusted = 40_000 * 1.08125 = 43_250 -> 432 lot
    assert result["kelly_fraction"] == pytest.approx(0.0813, abs=1e-4)
    assert result["recommended_lots"] == 432
    assert result["recommended_shares"] == 43_200
    assert result["total_allocation"] == 43_200 * 1000
    assert result["max_potential_loss"] == 43_200 * 50
    assert result["take_profit_price"] == 1100.0

    # Pengguna meminta 2%, kenyataannya 2,16% -> harus dinyatakan, bukan disembunyikan
    assert result["actual_risk_pct"] == pytest.approx(2.16, abs=0.01)
    assert result["within_risk_budget"] is False
    assert any("MELAMPAUI batas" in w for w in result["warnings"])


def test_default_caps_position_at_stated_max_risk():
    """Bawaan: parameter bernama 'risiko maksimal' benar-benar menjadi batas."""
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
        atr_multiplier=2.0,
        win_rate=0.55,
        reward_risk_ratio=2.0,
    )
    assert result["recommended_lots"] == 400  # bukan 432
    assert result["max_potential_loss"] == 2_000_000.0
    assert result["actual_risk_pct"] == pytest.approx(2.0, abs=0.001)
    assert result["within_risk_budget"] is True
    assert any("ditahan pada batas" in w for w in result["warnings"])


def test_kelly_not_applied_without_measured_win_rate():
    """Tanpa win rate terukur, posisi tidak boleh diperbesar berdasarkan tebakan."""
    result = calculate_position_size(
        total_capital=100_000_000,
        max_risk_pct=0.02,
        entry_price=1000.0,
        atr_value=25.0,
    )
    assert result["win_rate_used"] is None
    assert result["kelly_applied"] is False
    assert result["kelly_fraction"] == 0.0
    assert result["recommended_lots"] == 400
    assert result["actual_risk_pct"] == pytest.approx(2.0, abs=0.001)
    assert any("belum diukur" in w for w in result["warnings"])


def test_measured_win_rate_is_recorded():
    result = calculate_position_size(
        total_capital=100_000_000, max_risk_pct=0.02, entry_price=1000.0,
        atr_value=25.0, win_rate=0.44, reward_risk_ratio=2.0,
    )
    assert result["win_rate_used"] == 0.44
    assert result["within_risk_budget"] is True


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
    assert result["total_allocation"] <= 10_000_000
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
    assert result["total_allocation"] == 0


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
