"""Pipeline analisis satu ticker — dipakai bersama oleh endpoint dan scanner.

Menggabungkan kelima engine menjadi satu pemanggilan:
data pasar -> teknikal -> sentimen -> fundamental -> master score -> risk plan.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services import cache, fundamental_engine, market_data, risk_engine, scoring_engine, sentiment_engine
from services.rag_engine import rag_engine

# Data harga harian tidak berubah tiap detik — cache 10 menit sudah cukup
OHLCV_TTL_SECONDS = 600
SENTIMENT_TTL_SECONDS = 900
FUNDAMENTAL_TTL_SECONDS = 3600


def analyze_ticker(
    ticker: str,
    total_capital: float = 100_000_000,
    max_risk_pct: float = 0.02,
    atr_multiplier: float = 2.0,
    win_rate: float = 0.55,
    reward_risk_ratio: float = 2.0,
    period: str = "1y",
    use_rag: bool = True,
    use_cache: bool = True,
) -> dict:
    """Jalankan analisis lengkap untuk satu ticker.

    Raises:
        ValueError: ticker tidak punya data / data kurang dari 30 bar.
    """
    ticker = ticker.strip().upper()

    # 1. Technical Engine
    if use_cache:
        df = cache.get_or_compute(
            f"ohlcv:{ticker}:{period}",
            OHLCV_TTL_SECONDS,
            lambda: market_data.fetch_ohlcv(ticker, period=period),
        )
    else:
        df = market_data.fetch_ohlcv(ticker, period=period)

    indicators = market_data.compute_indicators(df)
    technical = market_data.technical_score(indicators)

    # 2. Sentiment Engine (punya fallback netral sendiri)
    if use_cache:
        sentiment = cache.get_or_compute(
            f"sentiment:{ticker}",
            SENTIMENT_TTL_SECONDS,
            lambda: sentiment_engine.sentiment_score(ticker),
        )
    else:
        sentiment = sentiment_engine.sentiment_score(ticker)

    # 3. Fundamental Engine (RAG -> rasio yfinance -> netral)
    # Hasil RAG tidak di-cache: pengguna bisa meng-upload laporan baru kapan
    # saja dan harus langsung terlihat. Skor dari rasio publik aman di-cache.
    rag_active = use_rag and rag_engine.is_ready
    if use_cache and not rag_active:
        fundamental = cache.get_or_compute(
            f"fundamental:{ticker}",
            FUNDAMENTAL_TTL_SECONDS,
            lambda: fundamental_engine.score_fundamental(ticker, use_rag=False),
        )
    else:
        fundamental = fundamental_engine.score_fundamental(ticker, use_rag=use_rag)

    # 4. Master Scoring Engine
    verdict = scoring_engine.master_score(
        fundamental=fundamental["score"],
        technical=technical["score"],
        sentiment=sentiment["score"],
    )

    # 5. Risk Engine
    risk_plan = risk_engine.calculate_position_size(
        total_capital=total_capital,
        max_risk_pct=max_risk_pct,
        entry_price=indicators["last_price"],
        atr_value=indicators["atr_14"],
        atr_multiplier=atr_multiplier,
        win_rate=win_rate,
        reward_risk_ratio=reward_risk_ratio,
    )

    return {
        "ticker": ticker,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "signal": verdict["signal"],
        "total_score": verdict["total_score"],
        "scores": {"components": verdict["components"], "weights": verdict["weights"]},
        "technical": {"indicators": indicators, **technical},
        "sentiment": sentiment,
        "fundamental": fundamental,
        "risk_plan": risk_plan,
    }
