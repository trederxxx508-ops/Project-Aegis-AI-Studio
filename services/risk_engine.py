"""Risk Engine — Dynamic Position Sizing (Section 5 blueprint).

Formula:
1. Stop loss berbasis volatilitas : SL = Entry - (k * ATR)
2. Risk-based sizing              : Lembar = (Modal * Risiko%) / (Entry - SL)
3. Fractional Kelly (c = 0.25)    : f* = c * ((W*R - (1-W)) / R)

Konvensi pasar Indonesia: 1 lot = 100 lembar saham.
"""
from __future__ import annotations

SHARES_PER_LOT = 100
KELLY_SAFETY_FACTOR = 0.25  # max 25% Kelly


def calculate_position_size(
    total_capital: float,
    max_risk_pct: float,
    entry_price: float,
    atr_value: float,
    atr_multiplier: float = 2.0,
    win_rate: float = 0.55,
    reward_risk_ratio: float = 2.0,
    unit_size: int = SHARES_PER_LOT,
    allow_fractional: bool = False,
    unit_name: str = "lot",
    currency: str = "IDR",
) -> dict:
    """Hitung stop loss ATR, ukuran posisi aman, dan eksposur portofolio.

    Satuan posisi dapat disesuaikan per pasar:

    - Saham Indonesia : ``unit_size=100`` (1 lot = 100 lembar), bulat
    - Emas / komoditas: ``unit_size=1``, ``allow_fractional=True``
      (troy ounce boleh pecahan, mis. 2,15 oz)

    Raises:
        ValueError: jika input di luar rentang valid.
    """
    if total_capital <= 0:
        raise ValueError("total_capital harus > 0")
    if not 0 < max_risk_pct < 1:
        raise ValueError("max_risk_pct harus di antara 0 dan 1 (mis. 0.02 = 2%)")
    if entry_price <= 0:
        raise ValueError("entry_price harus > 0")
    if atr_value <= 0:
        raise ValueError("atr_value harus > 0")
    if atr_multiplier <= 0:
        raise ValueError("atr_multiplier harus > 0")
    if not 0 <= win_rate <= 1:
        raise ValueError("win_rate harus di antara 0 dan 1")
    if reward_risk_ratio <= 0:
        raise ValueError("reward_risk_ratio harus > 0")
    if unit_size <= 0:
        raise ValueError("unit_size harus > 0")

    warnings: list[str] = []

    # 1. Stop Loss berbasis ATR
    stop_loss = entry_price - (atr_multiplier * atr_value)
    if stop_loss <= 0:
        # ATR terlalu besar relatif terhadap harga — batasi agar SL tetap valid
        stop_loss = entry_price * 0.10
        warnings.append(
            "Stop loss ATR jatuh <= 0; dibatasi ke 10% dari harga entry. "
            "Pertimbangkan menurunkan atr_multiplier."
        )
    risk_per_share = entry_price - stop_loss

    # 2. Modal berisiko maksimum
    max_risk_amount = total_capital * max_risk_pct

    # 3. Base position sizing
    shares_to_buy = max_risk_amount / risk_per_share

    # 4. Penyesuaian Fractional Kelly (safety factor 25%)
    kelly_f = (win_rate * reward_risk_ratio - (1 - win_rate)) / reward_risk_ratio
    fractional_kelly = max(0.0, kelly_f * KELLY_SAFETY_FACTOR)
    adjusted_shares = shares_to_buy * (1 + fractional_kelly)

    # Konversi ke satuan perdagangan pasar terkait
    raw_units = adjusted_shares / unit_size
    lots_to_buy = round(raw_units, 4) if allow_fractional else int(raw_units)

    # Guard: alokasi tidak boleh melebihi total modal
    max_affordable = total_capital / (unit_size * entry_price)
    max_affordable_lots = round(max_affordable, 4) if allow_fractional else int(max_affordable)
    if lots_to_buy > max_affordable_lots:
        lots_to_buy = max_affordable_lots
        warnings.append(
            "Ukuran posisi dibatasi oleh total modal yang tersedia "
            "(alokasi tidak boleh > 100% portofolio)."
        )
    if lots_to_buy <= 0:
        warnings.append(
            f"Modal/toleransi risiko terlalu kecil untuk membeli 1 {unit_name} pada "
            "harga dan volatilitas saat ini."
        )
        lots_to_buy = 0

    shares_final = round(lots_to_buy * unit_size, 4)
    total_allocation = shares_final * entry_price

    # Nama field sengaja netral mata uang: modul emas memakai USD, saham IDR.
    # Mata uang sebenarnya dinyatakan eksplisit lewat field ``currency``.
    return {
        "entry_price": entry_price,
        "stop_loss_price": round(stop_loss, 2),
        "risk_per_share": round(risk_per_share, 2),
        "max_risk_amount": round(max_risk_amount, 2),
        "kelly_fraction": round(fractional_kelly, 4),
        "recommended_units": lots_to_buy,
        "recommended_lots": lots_to_buy,  # nama lama, dipertahankan untuk saham
        "recommended_shares": shares_final,
        "total_allocation": round(total_allocation, 2),
        "max_potential_loss": round(shares_final * risk_per_share, 2),
        "portfolio_exposure_pct": round((total_allocation / total_capital) * 100, 2),
        "take_profit_price": round(entry_price + reward_risk_ratio * risk_per_share, 2),
        "unit_name": unit_name,
        "unit_size": unit_size,
        "currency": currency,
        "warnings": warnings,
    }
