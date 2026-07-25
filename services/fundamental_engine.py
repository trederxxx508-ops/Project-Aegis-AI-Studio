"""Fundamental Engine — skor fundamental 0-100 dengan fallback bertingkat.

Prioritas sumber:
1. RAG atas laporan keuangan PDF yang sudah di-upload (LLM menilai).
2. Heuristik rasio keuangan dari yfinance (ROE, margin, growth, DER, PER).
3. Netral 50 jika keduanya tidak tersedia.
"""
from __future__ import annotations

from typing import Optional

from services.rag_engine import rag_engine


def _score_ratio_heuristic(info: dict) -> Optional[dict]:
    """Skor 0-100 dari rasio yfinance. None jika data terlalu sedikit."""
    components: dict[str, float] = {}
    max_points = 0.0

    roe = info.get("returnOnEquity")
    if roe is not None:
        max_points += 25
        components["roe"] = 25 if roe > 0.20 else 18 if roe > 0.10 else 10 if roe > 0.05 else 5 if roe > 0 else 0

    margin = info.get("profitMargins")
    if margin is not None:
        max_points += 20
        components["profit_margin"] = 20 if margin > 0.20 else 14 if margin > 0.10 else 8 if margin > 0.05 else 4 if margin > 0 else 0

    growth = info.get("revenueGrowth")
    if growth is not None:
        max_points += 15
        components["revenue_growth"] = 15 if growth > 0.15 else 10 if growth > 0.05 else 6 if growth > 0 else 0

    der = info.get("debtToEquity")  # yfinance melaporkan dalam persen
    if der is not None:
        max_points += 20
        components["debt_to_equity"] = 20 if der < 50 else 14 if der < 100 else 7 if der < 200 else 2

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        max_points += 20
        components["valuation_pe"] = 20 if pe < 10 else 16 if pe < 15 else 10 if pe < 25 else 5 if pe < 40 else 2

    if len(components) < 2:
        return None

    score = round(sum(components.values()) / max_points * 100, 2)
    return {
        "score": score,
        "components": components,
        "source": "yfinance_ratios",
    }


def _fetch_info(ticker: str) -> Optional[dict]:
    try:
        import yfinance as yf  # lazy import

        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else None
    except Exception:
        return None


def score_fundamental(ticker: str, use_rag: bool = True) -> dict:
    """Kembalikan {"score", "source", ...} dengan fallback bertingkat."""
    if use_rag:
        rag_result = rag_engine.fundamental_score(ticker)
        if rag_result is not None:
            return rag_result

    info = _fetch_info(ticker)
    if info:
        heuristic = _score_ratio_heuristic(info)
        if heuristic is not None:
            return heuristic

    return {
        "score": 50.0,
        "source": "neutral_fallback",
        "note": (
            "Tidak ada laporan keuangan ter-ingest dan rasio yfinance tidak "
            "tersedia — skor netral 50 dipakai."
        ),
    }
