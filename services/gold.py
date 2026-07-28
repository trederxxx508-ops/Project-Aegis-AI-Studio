"""Pipeline analisis emas (XAU, harga dalam USD per troy ounce).

Perbedaan mendasar dari analisis saham: emas tidak punya laporan keuangan,
laba, atau utang — sehingga mesin fundamental tidak berlaku. Penggantinya
adalah **Skor Makro**, karena harga emas digerakkan oleh suku bunga riil,
kekuatan dolar, dan ekspektasi inflasi.

    Saham : Fundamental x0,5 + Teknikal x0,3 + Sentimen x0,2
    Emas  : Makro       x0,5 + Teknikal x0,3 + Sentimen x0,2

Catatan kejujuran soal sumber harga: spot XAU/USD tidak tersedia gratis pada
penyedia data publik, sehingga yang dipakai adalah kontrak berjangka emas
COMEX (``GC=F``) yang bergerak sangat dekat dengan spot. Sumber yang benar-
benar terpakai selalu dicantumkan pada hasil, tidak diklaim sebagai spot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from services import (
    cache, macro_engine, market_data, market_hours, regime, risk_engine, scoring_engine,
)
from services.gold_sentiment import gold_sentiment

# Urutan sumber harga; yang pertama berhasil dipakai.
PRICE_SOURCES = (
    {
        "symbol": "GC=F",
        "label": "Emas berjangka COMEX (GC=F)",
        "is_per_ounce": True,
        "note": "Kontrak berjangka; bergerak sangat dekat dengan harga spot.",
    },
    {
        "symbol": "GLD",
        "label": "ETF SPDR Gold Shares (GLD)",
        "is_per_ounce": False,
        "note": "Harga ETF per unit, BUKAN harga per troy ounce. Dipakai untuk arah tren.",
    },
    {
        "symbol": "IAU",
        "label": "ETF iShares Gold Trust (IAU)",
        "is_per_ounce": False,
        "note": "Harga ETF per unit, BUKAN harga per troy ounce. Dipakai untuk arah tren.",
    },
)

OHLCV_TTL_SECONDS = 600
WEIGHTS = {"macro": 0.5, "technical": 0.3, "sentiment": 0.2}


def fetch_gold_prices(period: str = "1y", use_cache: bool = True) -> tuple[pd.DataFrame, dict]:
    """Ambil riwayat harga emas, mencoba tiap sumber sampai ada yang berhasil.

    Returns:
        (DataFrame OHLCV, metadata sumber termasuk daftar percobaan yang gagal)
    """
    attempts: list[dict] = []

    for source in PRICE_SOURCES:
        symbol = source["symbol"]

        def _download(sym: str = symbol) -> pd.DataFrame:
            # yfinance dulu; bila klien HTTP-nya bermasalah, pakai jalur
            # chart API mandiri yang memakai requests biasa.
            try:
                return market_data.fetch_ohlcv(sym, period=period)
            except market_data.RateLimitedError:
                raise
            except Exception:
                return market_data.fetch_chart_api(sym, range_=period)

        try:
            if use_cache:
                df = cache.get_or_compute(f"gold:{symbol}:{period}", OHLCV_TTL_SECONDS, _download)
            else:
                df = _download()
            if df is None or df.empty:
                raise ValueError("data kosong")
            return df, {**source, "failed_attempts": attempts}
        except Exception as exc:
            attempts.append({"symbol": symbol, "error": str(exc)})
            continue

    raise ConnectionError(
        "Semua sumber harga emas gagal dihubungi. Periksa koneksi internet. "
        f"Rincian: {attempts}"
    )


def _last_price_time(df: pd.DataFrame) -> tuple[Optional[datetime], str]:
    """Waktu harga terakhir, seakurat mungkin.

    Indeks bar harian menandai **awal sesi**, bukan transaksi terakhir. Saat
    pasar sedang berjalan, memakai indeks bar akan melaporkan harga "berumur
    8 jam" padahal harganya baru saja bergerak. Bila penyedia data menyertakan
    ``regularMarketTime`` (waktu transaksi terakhir), angka itulah yang dipakai.
    """
    meta = df.attrs.get("meta") or {}
    market_time = meta.get("regularMarketTime")
    if market_time:
        try:
            return (
                datetime.fromtimestamp(int(market_time), tz=timezone.utc),
                "waktu transaksi terakhir dari penyedia data",
            )
        except (ValueError, OSError, TypeError):
            pass
    try:
        stamp = df.index[-1]
        if isinstance(stamp, pd.Timestamp):
            return stamp.to_pydatetime(), "awal sesi bar terakhir (perkiraan)"
    except Exception:
        pass
    return None, "tidak diketahui"


def analyze_gold(
    total_capital: float = 10_000.0,
    max_risk_pct: float = 0.02,
    atr_multiplier: float = 2.0,
    win_rate: Optional[float] = None,
    reward_risk_ratio: float = 2.0,
    period: str = "1y",
    extra_headlines: list[str] | None = None,
    use_cache: bool = True,
) -> dict:
    """Analisis emas menyeluruh: makro + teknikal + sentimen + rencana risiko.

    ``total_capital`` dalam USD, karena harga emas dihitung dalam USD.
    """
    # 1. Harga & indikator teknikal
    df, source = fetch_gold_prices(period=period, use_cache=use_cache)
    indicators = market_data.compute_indicators(df)
    technical = market_data.technical_score(indicators)

    # 2. Kesegaran harga & status pasar
    market_status = market_hours.gold_market_status()
    last_price_time, time_basis = _last_price_time(df)
    if last_price_time:
        freshness = {
            **market_hours.describe_price_freshness(last_price_time),
            "basis": time_basis,
        }
    else:
        freshness = {
            "description": "Waktu harga terakhir tidak diketahui.",
            "age_minutes": None,
            "is_intraday_fresh": False,
            "basis": time_basis,
        }

    # 3. Skor makro (pengganti fundamental)
    macro = macro_engine.macro_score(use_cache=use_cache)

    # 4. Sentimen khusus emas
    sentiment = gold_sentiment(extra_headlines=extra_headlines)

    # 5. Kesehatan hubungan makro — bobot menyesuaikan.
    # Bila emas sedang tidak mengikuti suku bunga riil, bertumpu 50% pada skor
    # makro tidak bisa dibenarkan; perannya dialihkan ke pergerakan harga.
    gold_closes = {idx.date(): float(val) for idx, val in df["Close"].dropna().items()}
    health = regime.relationship_health(gold_closes, use_cache=use_cache)
    weights = health["weights"]

    components = {
        "macro": max(0.0, min(100.0, macro["score"])),
        "technical": max(0.0, min(100.0, technical["score"])),
        "sentiment": max(0.0, min(100.0, sentiment["score"])),
    }
    total_score = round(sum(components[k] * weights[k] for k in weights), 2)
    signal = scoring_engine.classify_signal(total_score)

    # 6. Rencana risiko dalam troy ounce (boleh pecahan)
    risk_plan = risk_engine.calculate_position_size(
        total_capital=total_capital,
        max_risk_pct=max_risk_pct,
        entry_price=indicators["last_price"],
        atr_value=indicators["atr_14"],
        atr_multiplier=atr_multiplier,
        win_rate=win_rate,
        reward_risk_ratio=reward_risk_ratio,
        unit_size=1,
        allow_fractional=True,
        unit_name="troy ounce" if source["is_per_ounce"] else "unit ETF",
        currency="USD",
    )

    # 7. Peringatan gabungan agar keterbatasan tidak tersembunyi
    warnings: list[str] = []
    if not source["is_per_ounce"]:
        warnings.append(
            f"Sumber harga yang terpakai adalah {source['label']} — angkanya "
            "BUKAN harga per troy ounce. Ukuran posisi dihitung terhadap harga "
            "unit ETF tersebut, bukan terhadap ounce emas."
        )
    if not market_status["is_open"]:
        warnings.append(f"Pasar emas sedang tutup. {market_status['reason']}")
    if health["status"] == "putus":
        warnings.append(
            "Emas sedang TIDAK mengikuti suku bunga riil (hubungan makro putus). "
            f"Bobot skor makro diturunkan ke {weights['macro']:.0%}. {health['explanation']}"
        )
    elif health["status"] == "melemah":
        warnings.append(
            f"Hubungan makro melemah — bobot skor makro diturunkan ke {weights['macro']:.0%}."
        )
    elif health["status"] == "tidak_diketahui":
        warnings.append(health["explanation"])
    if macro["completeness_pct"] < 100:
        warnings.append(
            f"Skor makro parsial — hanya {macro['components_available']} dari "
            f"{macro['components_total']} komponen tersedia "
            f"({macro['completeness_pct']}%)."
        )
    warnings.extend(macro["notes"])
    warnings.extend(technical.get("notes", []))

    return {
        "asset": "GOLD",
        "currency": "USD",
        "quote_unit": "troy ounce" if source["is_per_ounce"] else "unit ETF",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "signal": signal,
        "total_score": total_score,
        "scores": {"components": components, "weights": weights},
        "macro_relationship": health,
        "price_source": {
            "symbol": source["symbol"],
            "label": source["label"],
            "note": source["note"],
            "is_per_ounce": source["is_per_ounce"],
            "failed_attempts": source["failed_attempts"],
        },
        "market_status": market_status,
        "price_freshness": freshness,
        "technical": {"indicators": indicators, **technical},
        "macro": macro,
        "sentiment": sentiment,
        "risk_plan": risk_plan,
        "warnings": warnings,
    }
