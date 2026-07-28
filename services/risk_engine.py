"""Risk Engine — Dynamic Position Sizing (Section 5 blueprint).

Formula:
1. Stop loss berbasis volatilitas : SL = Entry - (k * ATR)
2. Risk-based sizing              : Lembar = (Modal * Risiko%) / (Entry - SL)
3. Fractional Kelly (c = 0.25)    : f* = c * ((W*R - (1-W)) / R)

Konvensi pasar Indonesia: 1 lot = 100 lembar saham.

Dua keputusan penting yang menyimpang dari rumus mentah blueprint, keduanya
demi kejujuran terhadap apa yang dijanjikan parameter kepada pengguna:

**Batas risiko benar-benar menjadi batas.** Rumus blueprint mengalikan ukuran
posisi dengan ``(1 + f*)`` SETELAH batas risiko dihitung, sehingga risiko
sebenarnya melampaui angka yang diminta pengguna (mis. meminta 2% tetapi
menanggung 2,16%). Parameter bernama "risiko maksimal" tidak boleh dilampaui,
jadi ``cap_at_max_risk=True`` menjadi perilaku bawaan. Perilaku blueprint asli
tetap tersedia lewat ``cap_at_max_risk=False``, dan berapa pun hasilnya,
``actual_risk_pct`` selalu dilaporkan sehingga tidak pernah tersembunyi.

**Kelly tidak berjalan di atas tebakan.** ``win_rate`` bawaannya ``None``,
yang berarti Kelly tidak diterapkan sama sekali. Membesarkan posisi hanya sah
bila keunggulan sudah diukur — dan uji mundur menunjukkan keunggulan pemilihan
waktu masuk belum terbukti. Isi ``win_rate`` hanya dengan angka hasil
pengukuran (lihat ``services.backtest.calibrated_risk_inputs``).
"""
from __future__ import annotations

import math
from typing import Optional

SHARES_PER_LOT = 100
KELLY_SAFETY_FACTOR = 0.25  # max 25% Kelly


def calculate_position_size(
    total_capital: float,
    max_risk_pct: float,
    entry_price: float,
    atr_value: float,
    atr_multiplier: float = 2.0,
    win_rate: Optional[float] = None,
    reward_risk_ratio: float = 2.0,
    cap_at_max_risk: bool = True,
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
    if win_rate is not None and not 0 <= win_rate <= 1:
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

    # 4. Penyesuaian Fractional Kelly (safety factor 25%).
    # Tanpa win_rate terukur, Kelly tidak diterapkan sama sekali — membesarkan
    # posisi berdasarkan tebakan justru menambah risiko tanpa dasar.
    if win_rate is None:
        fractional_kelly = 0.0
        kelly_applied = False
        warnings.append(
            "Kelly tidak diterapkan karena win rate belum diukur. Jalankan Uji "
            "Mundur untuk memperoleh angka terukur, lalu isikan hasilnya."
        )
    else:
        kelly_f = (win_rate * reward_risk_ratio - (1 - win_rate)) / reward_risk_ratio
        fractional_kelly = max(0.0, kelly_f * KELLY_SAFETY_FACTOR)
        kelly_applied = fractional_kelly > 0
    adjusted_shares = shares_to_buy * (1 + fractional_kelly)

    # Kelly mengalikan ukuran posisi SETELAH batas risiko dihitung, sehingga
    # risiko nyata bisa melampaui batas yang diminta. Parameter bernama
    # "risiko maksimal" tidak boleh dilampaui, jadi hasilnya dikembalikan
    # ke dalam batas kecuali pengguna memilih perilaku blueprint asli.
    if cap_at_max_risk and adjusted_shares > shares_to_buy:
        adjusted_shares = shares_to_buy
        if fractional_kelly > 0:
            warnings.append(
                f"Kelly ingin memperbesar posisi {fractional_kelly*100:.1f}%, tetapi itu "
                f"akan membuat risiko melampaui batas {max_risk_pct*100:.2f}% yang Anda "
                "tetapkan. Posisi ditahan pada batas tersebut."
            )

    # Konversi ke satuan perdagangan pasar terkait. Pembulatan selalu KE BAWAH:
    # membulatkan ke atas, sekecil apa pun, membuat risiko melampaui batas yang
    # justru sedang ditegakkan.
    def _to_units(value: float) -> float | int:
        if not allow_fractional:
            return int(value)
        return math.floor(value * 10_000) / 10_000

    raw_units = adjusted_shares / unit_size
    lots_to_buy = _to_units(raw_units)

    # Guard: alokasi tidak boleh melebihi total modal
    max_affordable_lots = _to_units(total_capital / (unit_size * entry_price))
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
    actual_loss = shares_final * risk_per_share
    actual_risk_pct = actual_loss / total_capital * 100

    # Risiko nyata selalu dilaporkan, dan bila melampaui permintaan pengguna
    # hal itu dinyatakan terang-terangan alih-alih dibiarkan tersembunyi.
    if actual_risk_pct > max_risk_pct * 100 + 1e-9:
        warnings.append(
            f"Risiko nyata {actual_risk_pct:.2f}% MELAMPAUI batas "
            f"{max_risk_pct*100:.2f}% yang Anda tetapkan "
            "(perilaku rumus blueprint asli; aktifkan cap_at_max_risk untuk menahannya)."
        )

    # Nama field sengaja netral mata uang: modul emas memakai USD, saham IDR.
    # Mata uang sebenarnya dinyatakan eksplisit lewat field ``currency``.
    return {
        "entry_price": entry_price,
        "stop_loss_price": round(stop_loss, 2),
        "risk_per_share": round(risk_per_share, 2),
        "max_risk_amount": round(max_risk_amount, 2),
        "risk_budget_pct": round(max_risk_pct * 100, 4),
        "actual_risk_pct": round(actual_risk_pct, 4),
        "within_risk_budget": bool(actual_risk_pct <= max_risk_pct * 100 + 1e-9),
        "kelly_fraction": round(fractional_kelly, 4),
        "kelly_applied": kelly_applied,
        "win_rate_used": win_rate,
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
