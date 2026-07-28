"""Regime Detector — mendeteksi saat hubungan makro-emas berhenti berlaku.

Macro Engine bertumpu pada satu asumsi: suku bunga riil naik menekan emas.
Asumsi itu terbukti benar **sebagian besar waktu**, tetapi tidak selalu.
Contoh paling nyata: sejak 2022 pembelian besar-besaran oleh bank sentral
mendorong emas naik bersamaan dengan naiknya suku bunga riil — kondisi yang
membuat skor makro memberi sinyal menekan padahal harga justru menguat.

Sistem yang jujur harus tahu kapan modelnya sendiri sedang tidak berlaku,
lalu mengatakannya. Modul ini mengukur korelasi bergulir antara perubahan
suku bunga riil dan imbal hasil emas, membandingkannya dengan pola jangka
panjang, dan **menurunkan bobot skor makro** bila hubungannya sedang putus.

Ambang di bawah ini bukan tebakan — diturunkan dari sebaran korelasi bergulir
6 bulan pada data 2016-2026 (lihat ``scripts/validate_macro_relationship.py``
untuk metode pengujian yang sama):

    korelasi < -0,20  : NORMAL  (88% dari waktu)
    -0,20 s/d 0       : MELEMAH (8%)
    >= 0              : PUTUS   (4%)

Rata-rata jangka panjang: -0,45; median -0,44.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import numpy as np

from services import cache, macro_engine

ROLLING_WINDOW = 126        # ~6 bulan perdagangan
CHANGE_SPAN = 5             # perubahan mingguan
REGIME_TTL_SECONDS = 3600

# Ambang empiris (lihat docstring modul)
THRESHOLD_NORMAL = -0.20
THRESHOLD_BROKEN = 0.0
LONG_RUN_BASELINE = -0.44

# Bobot skor emas menurut kesehatan hubungan makro. Ketika hubungan makro
# tidak berlaku, bertumpu pada makro sebesar 50% tidak lagi bisa dibenarkan;
# bobot dialihkan ke pergerakan harga yang tetap terukur apa adanya.
WEIGHTS_BY_STATUS = {
    "normal": {"macro": 0.50, "technical": 0.30, "sentiment": 0.20},
    "melemah": {"macro": 0.35, "technical": 0.40, "sentiment": 0.25},
    "putus": {"macro": 0.20, "technical": 0.50, "sentiment": 0.30},
    "tidak_diketahui": {"macro": 0.35, "technical": 0.40, "sentiment": 0.25},
}

STATUS_LABEL = {
    "normal": "Hubungan makro BERLAKU",
    "melemah": "Hubungan makro MELEMAH",
    "putus": "Hubungan makro PUTUS",
    "tidak_diketahui": "Kesehatan hubungan tidak dapat diukur",
}


def _classify(correlation: float) -> str:
    if correlation < THRESHOLD_NORMAL:
        return "normal"
    if correlation < THRESHOLD_BROKEN:
        return "melemah"
    return "putus"


def _paired_series(gold_prices: dict[date, float]) -> tuple[np.ndarray, np.ndarray]:
    """Sejajarkan suku bunga riil dan harga emas pada tanggal yang sama."""
    real_yield = dict(macro_engine.fetch_fred_series(macro_engine.SERIES["real_yield_10y"]))
    days = sorted(set(real_yield) & set(gold_prices))
    if len(days) < ROLLING_WINDOW + CHANGE_SPAN + 10:
        raise ValueError(
            f"Data beririsan terlalu pendek ({len(days)} hari) untuk mengukur "
            f"kesehatan hubungan; butuh minimal {ROLLING_WINDOW + CHANGE_SPAN + 10}."
        )
    return (
        np.array([real_yield[d] for d in days]),
        np.array([gold_prices[d] for d in days]),
    )


def relationship_health(
    gold_prices: dict[date, float],
    window: int = ROLLING_WINDOW,
    use_cache: bool = True,
) -> dict:
    """Ukur apakah hubungan suku bunga riil dengan emas sedang berlaku.

    Args:
        gold_prices: peta tanggal -> harga penutupan emas.
    """
    def _compute() -> dict:
        ry, gold = _paired_series(gold_prices)
        d_ry = ry[CHANGE_SPAN:] - ry[:-CHANGE_SPAN]
        returns = (gold[CHANGE_SPAN:] - gold[:-CHANGE_SPAN]) / gold[:-CHANGE_SPAN] * 100

        recent_ry, recent_ret = d_ry[-window:], returns[-window:]
        if len(recent_ry) < window // 2 or np.std(recent_ry) == 0 or np.std(recent_ret) == 0:
            raise ValueError("Ragam data terlalu kecil untuk menghitung korelasi.")
        current = float(np.corrcoef(recent_ry, recent_ret)[0, 1])

        # Sebaran korelasi historis, agar posisi saat ini punya konteks
        history = [
            float(np.corrcoef(d_ry[i - window:i], returns[i - window:i])[0, 1])
            for i in range(window, len(d_ry), 5)
        ]
        history = [h for h in history if np.isfinite(h)]
        percentile = (
            round(float((np.array(history) < current).mean() * 100), 1) if history else None
        )

        status = _classify(current)
        return {
            "status": status,
            "label": STATUS_LABEL[status],
            "correlation": round(current, 3),
            "baseline_correlation": LONG_RUN_BASELINE,
            "historical_median": round(float(np.median(history)), 3) if history else None,
            "percentile_vs_history": percentile,
            "window_days": window,
            "samples": len(history),
            "weights": WEIGHTS_BY_STATUS[status],
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        if use_cache:
            result = cache.get_or_compute("regime:gold_macro", REGIME_TTL_SECONDS, _compute)
        else:
            result = _compute()
    except Exception as exc:
        return {
            "status": "tidak_diketahui",
            "label": STATUS_LABEL["tidak_diketahui"],
            "correlation": None,
            "baseline_correlation": LONG_RUN_BASELINE,
            "error": str(exc),
            "weights": WEIGHTS_BY_STATUS["tidak_diketahui"],
            "explanation": (
                "Kesehatan hubungan makro tidak dapat diukur, sehingga bobot "
                "makro diturunkan ke tingkat hati-hati."
            ),
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }

    result["explanation"] = _explain(result)
    return result


def _explain(result: dict) -> str:
    """Penjelasan yang bisa dipahami tanpa latar belakang statistik."""
    corr = result["correlation"]
    status = result["status"]
    base = result["baseline_correlation"]

    if status == "normal":
        return (
            f"Enam bulan terakhir, suku bunga riil dan emas bergerak berlawanan "
            f"seperti biasanya (korelasi {corr:+.2f}, pola jangka panjang {base:+.2f}). "
            "Skor makro layak diberi bobot penuh."
        )
    if status == "melemah":
        return (
            f"Hubungan sedang melemah (korelasi {corr:+.2f}, biasanya {base:+.2f}). "
            "Emas mulai kurang mengikuti suku bunga riil, jadi bobot skor makro "
            "diturunkan dan pergerakan harga diberi peran lebih besar."
        )
    return (
        f"⚠️ Hubungan sedang PUTUS: korelasi {corr:+.2f}, padahal biasanya {base:+.2f}. "
        "Emas saat ini TIDAK mengikuti suku bunga riil — kondisi yang terjadi mis. "
        "ketika bank sentral memborong emas besar-besaran. Skor makro sedang "
        "kurang bisa diandalkan, sehingga bobotnya diturunkan tajam dan pergerakan "
        "harga dijadikan pegangan utama."
    )
